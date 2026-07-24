"""Static window chrome: the five menus, the slim toolbar, and the
window-level shortcut registration (M1.5).

Menus are pure wiring — every handler lives on the window or on a
component it owns; this module declares the chrome and holds the action
refs the window mutates afterwards (enable-on-load, dynamic undo/redo
text, the page/system readout). Play and Follow are NOT built here: the
transport strip owns Play and the inspector owns Follow, and the
Playback menu adds those same QActions, so button, menu item, and
shortcut state cannot diverge (brief flag 3).

The Score menu (renamed Parts — brief §1b, content preserved) is
created empty here and repopulated per load by the window's dynamic
builder (ui/parts_menu.py from M1.6).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QLabel, QMenu

if TYPE_CHECKING:
    from scoreanim.ui.main_window import MainWindow


class MainMenus:
    """Menubar + slim toolbar for the main window.

    Exposes what the window updates after construction: `export_action`
    and `texts_action` (enabled once a score loads), `undo_action` and
    `redo_action` (text + enabled per document change), `prev_action`,
    `next_action`, and `page_label` (the page/system readout — stays
    window-owned, next to the stage it describes), and `score_menu`
    (repopulated per load).

    All five menus are kept as attributes on purpose: a QMenu whose
    last Python wrapper is garbage-collected can take its C++ object
    with it (PySide6 ownership quirk around `QMenuBar.addMenu` /
    `QAction.menu()`), so the chrome holds strong references for the
    window's lifetime.
    """

    def __init__(self, window: MainWindow) -> None:
        # -- File ------------------------------------------------------------
        open_score = QAction("Open Score…", window)
        open_score.setShortcut(QKeySequence.StandardKey.Open)
        open_score.triggered.connect(window.open_score_dialog)

        open_project = QAction("Open Project…", window)
        open_project.setShortcut("Ctrl+Shift+O")
        open_project.triggered.connect(window.open_project_dialog)

        save = QAction("Save Project", window)
        save.setShortcut(QKeySequence.StandardKey.Save)
        save.triggered.connect(window.save_project)

        save_as = QAction("Save Project As…", window)
        save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as.triggered.connect(window.save_project_as)

        self.export_action = QAction("Export Video…", window)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.setEnabled(False)         # needs a loaded score
        self.export_action.triggered.connect(window.open_export_dialog)

        # -- Edit ------------------------------------------------------------
        self.undo_action = QAction("Undo", window)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(window.app_state.undo)

        self.redo_action = QAction("Redo", window)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(window.app_state.redo)

        self.texts_action = QAction("Texts…", window)
        self.texts_action.setEnabled(False)          # needs a loaded score
        self.texts_action.triggered.connect(window.open_texts_dialog)

        # -- View ------------------------------------------------------------
        fit = QAction("Fit", window)
        fit.setShortcut("Ctrl+0")
        fit.triggered.connect(window.view.fit)

        # prev/next step the presentation unit: pages in paged mode,
        # systems in system mode
        self.prev_action = QAction("◀", window)
        self.prev_action.setShortcut(
            QKeySequence.StandardKey.MoveToPreviousPage)
        self.prev_action.triggered.connect(lambda: window.step(-1))
        self.next_action = QAction("▶", window)
        self.next_action.setShortcut(QKeySequence.StandardKey.MoveToNextPage)
        self.next_action.triggered.connect(lambda: window.step(+1))
        self.page_label = QLabel("–/–")

        # -- Playback --------------------------------------------------------
        open_audio = QAction("Open Audio…", window)
        open_audio.triggered.connect(window.open_audio_dialog)
        open_tempo = QAction("Import Tempo…", window)
        open_tempo.triggered.connect(window.open_tempo_dialog)
        reload_tempo = QAction("Reload Tempo", window)
        reload_tempo.setShortcut("F5")
        reload_tempo.triggered.connect(window.reload_tempo)

        # -- menubar ---------------------------------------------------------
        strip = window.lower_zone.strip
        menubar = window.menuBar()

        self.file_menu = menubar.addMenu("&File")
        self.file_menu.addAction(open_score)         # off the toolbar (M1.5)
        self.file_menu.addAction(open_project)
        self.file_menu.addSeparator()
        self.file_menu.addAction(save)
        self.file_menu.addAction(save_as)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.export_action)

        self.edit_menu = menubar.addMenu("&Edit")
        self.edit_menu.addAction(self.undo_action)
        self.edit_menu.addAction(self.redo_action)
        self.edit_menu.addSeparator()
        self.edit_menu.addAction(self.texts_action)

        self.view_menu = menubar.addMenu("&View")
        self.view_menu.addAction(fit)
        self.view_menu.addAction(self.prev_action)
        self.view_menu.addAction(self.next_action)
        self.view_menu.addSeparator()
        self.view_menu.addAction(window.inspector.toggleViewAction())
        self.view_menu.addAction(window.lower_zone.toggleViewAction())

        self.score_menu = QMenu("&Score", window)
        menubar.addMenu(self.score_menu)

        self.playback_menu = menubar.addMenu("&Playback")
        self.playback_menu.addAction(strip.play_action)
        self.playback_menu.addAction(window.inspector.follow_action)
        self.playback_menu.addSeparator()
        self.playback_menu.addAction(open_audio)
        self.playback_menu.addAction(open_tempo)
        self.playback_menu.addAction(reload_tempo)

        # -- slim toolbar (ruling 2026-07-24): ◀ page-label ▶ · Fit ----------
        toolbar = window.addToolBar("Main")
        toolbar.setObjectName("MainToolbar")   # saveState identity (M1.8)
        toolbar.setMovable(False)
        toolbar.addAction(self.prev_action)
        toolbar.addWidget(self.page_label)
        toolbar.addAction(self.next_action)
        toolbar.addSeparator()
        toolbar.addAction(fit)

        # window-level so these shortcuts fire regardless of focus
        for action in (self.undo_action, self.redo_action, save,
                       strip.play_action, strip.arm_taps_action,
                       strip.tap_action, reload_tempo):
            window.addAction(action)
