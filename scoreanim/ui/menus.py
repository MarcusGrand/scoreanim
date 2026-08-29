"""Static window chrome: the six menus, the toolbar, and the
window-level shortcut registration (M1.5).

Every way of getting a file in is in the File menu (B1) — Open Score,
Open Project, Open Recent, Open Audio, Import Tempo — because that is
where people look for them. The three openers are ALSO on the in-window
toolbar, as the same QAction objects, since they are what you reach for
first (ruling 2026-07-30).

Menus are pure wiring — every handler lives on the window or on a
component it owns; this module declares the chrome and holds the action
refs the window mutates afterwards (enable-on-load, dynamic undo/redo
text, the page/system readout). Play and Go to Start are NOT built
here: the transport strip owns them and the Playback menu adds those
same QActions, so button, menu item, and shortcut state cannot diverge
(brief flag 3). The four arrow seeks come the same way, from
`ui/seek_keys.py`.

The Score menu (renamed Parts — brief §1b, content preserved) is
created empty here and repopulated per load by the window's dynamic
builder (ui/parts_menu.py from M1.6).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QLabel, QMenu, QSizePolicy, QToolButton,
                               QWidget)

from scoreanim.ui import about_dialog, shortcuts_dialog
from scoreanim.ui.recents import RecentsMenu
from scoreanim.ui.theme import icons

if TYPE_CHECKING:
    from scoreanim.ui.main_window import MainWindow


class MainMenus:
    """Menubar + slim toolbar for the main window.

    Exposes what the window updates after construction: `export_action`
    and `texts_action` (enabled once a score loads — `export_button` is
    the toolbar's face for that same action), `undo_action` and
    `redo_action` (text + enabled per document change), `prev_action`,
    `next_action`, and `page_label` (the page/system readout — stays
    window-owned, next to the stage it describes), `score_menu`
    (repopulated per load), and `recents_menu` (refilled on open).

    All six menus are kept as attributes on purpose: a QMenu whose
    last Python wrapper is garbage-collected can take its C++ object
    with it (PySide6 ownership quirk around `QMenuBar.addMenu` /
    `QAction.menu()`), so the chrome holds strong references for the
    window's lifetime.
    """

    def __init__(self, window: MainWindow) -> None:
        # -- File ------------------------------------------------------------
        open_score = QAction(icons.icon("file-music"), "Open Score…", window)
        open_score.setShortcut(QKeySequence.StandardKey.Open)
        open_score.triggered.connect(window.files.open_score_dialog)

        open_project = QAction("Open Project…", window)
        open_project.setShortcut("Ctrl+Shift+O")
        open_project.triggered.connect(window.files.open_project_dialog)

        open_audio = QAction(icons.icon("audio-lines"), "Open Audio…",
                             window)
        open_audio.triggered.connect(window.files.open_audio_dialog)
        open_tempo = QAction(icons.icon("timer"), "Import Tempo…", window)
        open_tempo.triggered.connect(window.files.open_tempo_dialog)

        # last 8 scores and projects; the submenu refills itself from
        # the store each time it opens, so an open in this session shows
        # up without anyone telling the menu
        self.recents_menu = RecentsMenu(window.files.recents,
                                        window.files.open_recent, window)

        save = QAction("Save Project", window)
        save.setShortcut(QKeySequence.StandardKey.Save)
        save.triggered.connect(window.files.save_project)

        save_as = QAction("Save Project As…", window)
        save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as.triggered.connect(window.files.save_project_as)

        self.export_action = QAction("Export Video…", window)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.setEnabled(False)         # needs a loaded score
        self.export_action.triggered.connect(window.files.open_export_dialog)

        # -- Edit ------------------------------------------------------------
        self.undo_action = QAction(icons.icon("undo-2"), "Undo", window)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(window.app_state.undo)
        # both rename themselves per document change ("Undo Nudge"), so
        # the shortcut sheet is told what to call them
        shortcuts_dialog.set_sheet_name(self.undo_action, "Undo")

        self.redo_action = QAction(icons.icon("redo-2"), "Redo", window)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(window.app_state.redo)
        shortcuts_dialog.set_sheet_name(self.redo_action, "Redo")

        self.texts_action = QAction("Texts…", window)
        self.texts_action.setEnabled(False)          # needs a loaded score
        self.texts_action.triggered.connect(window.text_edit.open_texts_dialog)

        # -- View ------------------------------------------------------------
        fit = QAction(icons.icon("maximize"), "Fit", window)
        fit.setShortcut("Ctrl+0")
        fit.triggered.connect(window.view.fit)

        # prev/next step the presentation unit: pages in paged mode,
        # systems in system mode — hence the plain name, and a tooltip
        # that says both rather than promising pages
        self.prev_action = QAction(icons.icon("chevron-left"), "Previous",
                                   window)
        self.prev_action.setToolTip("Previous page or system")
        self.prev_action.setShortcut(
            QKeySequence.StandardKey.MoveToPreviousPage)
        self.prev_action.triggered.connect(lambda: window.router.step(-1))
        self.next_action = QAction(icons.icon("chevron-right"), "Next", window)
        self.next_action.setToolTip("Next page or system")
        self.next_action.setShortcut(QKeySequence.StandardKey.MoveToNextPage)
        self.next_action.triggered.connect(lambda: window.router.step(+1))
        self.page_label = QLabel("–/–")

        # -- Playback --------------------------------------------------------
        reload_tempo = QAction("Reload Tempo", window)
        reload_tempo.setShortcut("F5")
        reload_tempo.triggered.connect(window.files.reload_tempo)

        # -- Help ------------------------------------------------------------
        # No shortcut on either: the shortcut sheet is the one thing you
        # go looking for with the mouse, and a key of its own would have
        # to be listed in itself.
        shortcuts = QAction(f"{shortcuts_dialog.TITLE}…", window)
        shortcuts.triggered.connect(
            lambda: shortcuts_dialog.ShortcutsDialog(
                self.all_menus, window).exec())

        about = QAction(about_dialog.TITLE, window)
        about.triggered.connect(
            lambda: about_dialog.show_about(window))

        # -- menubar ---------------------------------------------------------
        strip = window.lower_zone.strip
        menubar = window.menuBar()

        self.file_menu = menubar.addMenu("&File")
        self.file_menu.addAction(open_score)
        self.file_menu.addAction(open_project)
        self.file_menu.addMenu(self.recents_menu)
        self.file_menu.addSeparator()
        self.file_menu.addAction(open_audio)
        self.file_menu.addAction(open_tempo)
        self.file_menu.addSeparator()
        self.file_menu.addAction(save)
        self.file_menu.addAction(save_as)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.export_action)

        self.edit_menu = menubar.addMenu("&Edit")
        self.edit_menu.addAction(self.undo_action)
        self.edit_menu.addAction(self.redo_action)
        self.edit_menu.addSeparator()
        # the SAME action object the stage view holds, so the menu and
        # the key cannot disagree about when it may fire (the shared
        # QAction idiom)
        self.edit_menu.addAction(window.delete_action.action)
        self.edit_menu.addAction(window.stem_flip_action.action)
        self.edit_menu.addSeparator()
        self.edit_menu.addAction(self.texts_action)

        self.view_menu = menubar.addMenu("&View")
        self.view_menu.addAction(fit)
        self.view_menu.addAction(self.prev_action)
        self.view_menu.addAction(self.next_action)
        self.view_menu.addSeparator()
        self.view_menu.addAction(window.layout_zone.toggleViewAction())
        self.view_menu.addAction(window.inspector.toggleViewAction())
        self.view_menu.addAction(window.lower_zone.toggleViewAction())

        self.score_menu = QMenu("&Score", window)
        menubar.addMenu(self.score_menu)

        # Open Audio and Import Tempo moved to File (B1), and Follow is
        # not an option any more (ruling 2026-08-29), so Playback is
        # Play and Reload Tempo
        self.playback_menu = menubar.addMenu("&Playback")
        self.playback_menu.addAction(strip.play_action)
        # the same action objects the strip button and the arrow keys
        # drive; they are in a menu so the shortcut sheet can find them,
        # which is the only place a key that belongs to no button is
        # written down
        self.playback_menu.addAction(strip.to_start_action)
        for action in window.seek_keys.actions:
            self.playback_menu.addAction(action)
        self.playback_menu.addSeparator()
        self.playback_menu.addAction(reload_tempo)

        # Last, where every platform puts it. On macOS Qt lifts "About
        # ScoreAnim" out of here into the application menu by itself,
        # which is where a Mac user looks for it — the menu object below
        # still holds both actions either way.
        self.help_menu = menubar.addMenu("&Help")
        self.help_menu.addAction(shortcuts)
        self.help_menu.addAction(about)

        # -- toolbar: the openers · the pager · Export ----------------------
        # Left to right: what you do at the start of a session, then
        # where you are in the score, then — pushed to the far right by
        # a spring — what the whole session is aimed at (B2). Fit left
        # the toolbar; it lives in the View menu until the stage takes
        # it over.
        #
        # Every button here drives the same QAction object the menu
        # holds, so a toolbar button and its menu item can never
        # disagree about their state.
        toolbar = window.addToolBar("Main")
        toolbar.setObjectName("MainToolbar")   # saveState identity (M1.8)
        toolbar.setMovable(False)
        # the openers keep their labels; the pager is icon-only, set
        # per button below
        toolbar.setIconSize(icons.TOOLBAR_SIZE)
        toolbar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addAction(open_score)
        toolbar.addAction(open_audio)
        toolbar.addAction(open_tempo)
        toolbar.addSeparator()
        toolbar.addAction(self.prev_action)
        toolbar.addWidget(self.page_label)
        toolbar.addAction(self.next_action)
        for action in (self.prev_action, self.next_action):
            button = toolbar.widgetForAction(action)
            if button is not None:
                button.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonIconOnly)

        # the spring: it takes every spare pixel, so Export sits on the
        # right edge however wide the window is, and it is the first
        # thing to give way when the window gets narrow
        spring = QWidget(toolbar)
        spring.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spring)

        # Export is a widget, not a plain toolbar action, because it is
        # the one filled button in the app and the stylesheet needs a
        # name to aim the accent at. It still drives the File menu's
        # QAction, so it is disabled until a score loads and its Ctrl+E
        # keeps working.
        self.export_button = QToolButton(toolbar)
        self.export_button.setObjectName("ExportButton")
        self.export_button.setDefaultAction(self.export_action)
        self.export_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addWidget(self.export_button)

        # window-level so these shortcuts fire regardless of focus. The
        # arrow seeks are here too: Qt still lets a text field or the
        # stage claim an arrow ahead of them (ui/seek_keys.py says how).
        for action in (self.undo_action, self.redo_action, save,
                       open_score, strip.play_action, strip.to_start_action,
                       reload_tempo, *window.seek_keys.actions):
            window.addAction(action)

    @property
    def all_menus(self) -> tuple[QMenu, ...]:
        """The six menus in bar order — the refs, never re-fetched from
        the bar with `QAction.menu()` (see the class docstring). The
        shortcut sheet reads these."""
        return (self.file_menu, self.edit_menu, self.view_menu,
                self.score_menu, self.playback_menu, self.help_menu)

    def set_position(self, text: str, can_prev: bool, can_next: bool) -> None:
        """The page/system readout and the step actions' enabled state,
        driven by `ui/view_router.py`. The three widgets live here, so
        the update does too — the router never reaches for them."""
        self.page_label.setText(text)
        self.prev_action.setEnabled(can_prev)
        self.next_action.setEnabled(can_next)
