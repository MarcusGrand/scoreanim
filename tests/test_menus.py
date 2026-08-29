"""Static chrome (M1.5, B1, B2, B3), offscreen: the six menus in order,
every opener in File, the toolbar (the same three openers, the page
steps, and Export on the right edge), shared Play/Follow QActions in
the Playback menu, dock toggles in View, and window-level shortcut
registration — the structural half of the brief's
click-through/shortcut-sweep verify (the interactive half is run by
hand).

Menus are read via the refs MainMenus holds, never `QAction.menu()` —
re-wrapping a menu and letting the wrapper be garbage-collected can
delete the C++ menu (the PySide6 quirk that made MainMenus keep them).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolBar  # noqa: E402

from scoreanim.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(qapp):
    return MainWindow()


def _texts(menu) -> list[str]:
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def _toolbar(window):
    return window.findChild(QToolBar, "MainToolbar")


def test_six_menus_in_roadmap_order(window) -> None:
    """Help joined the five in B3, last, as it is everywhere else."""
    menus = window.menus
    order = ["&File", "&Edit", "&View", "&Score", "&Playback", "&Help"]
    assert [a.text() for a in window.menuBar().actions()] == order
    assert [m.title() for m in (menus.file_menu, menus.edit_menu,
                                menus.view_menu, menus.score_menu,
                                menus.playback_menu, menus.help_menu)] \
        == order
    assert [m.title() for m in menus.all_menus] == order


def test_file_and_edit_contents(window) -> None:
    # every way of getting a file in lives here (B1); Open Recent is a
    # submenu, so it shows up as its own title
    assert _texts(window.menus.file_menu) \
        == ["Open Score…", "Open Project…", "Open Recent", "Open Audio…",
            "Import Tempo…", "Save Project", "Save Project As…",
            "Export Video…"]
    assert _texts(window.menus.edit_menu) == ["Undo", "Redo", "Delete",
                                              "Flip Stem", "Texts…"]
    assert not window.menus.export_action.isEnabled()   # needs a score
    assert not window.menus.texts_action.isEnabled()


def test_view_menu_holds_dock_toggles(window) -> None:
    actions = window.menus.view_menu.actions()
    for dock in (window.layout_zone, window.inspector, window.lower_zone):
        assert dock.toggleViewAction() in actions
    # left to right across the window, which is how the docks sit (M6.6)
    assert _texts(window.menus.view_menu) \
        == ["Fit", "Previous", "Next", "Layout Zone", "Inspector",
            "Lower Zone"]


def test_playback_menu_shares_the_component_actions(window) -> None:
    """Menu, strip button, and shortcut are ONE QAction for Play and
    for Go to Start (brief flag 3), and the four arrow seeks are here
    because a menu is the only place the shortcut sheet looks."""
    strip = window.lower_zone.strip
    actions = window.menus.playback_menu.actions()
    assert actions[0] is strip.play_action
    assert actions[1] is strip.to_start_action
    assert actions[2:6] == list(window.seek_keys.actions)
    # the two openers moved to File (B1) and Follow is not an option any
    # more (ruling 2026-08-29); Reload Tempo stayed
    assert _texts(window.menus.playback_menu) \
        == ["Play", "Go to Start", "Back 1 Second", "Forward 1 Second",
            "Back 5 Seconds", "Forward 5 Seconds", "Reload Tempo"]


def test_toolbar_shares_the_openers_with_the_file_menu(window) -> None:
    """The three things you do first are in the window as well as in
    the menu — and as ONE action each, so their state cannot diverge."""
    in_file = {a.text(): a for a in window.menus.file_menu.actions()
               if a.text()}
    shared = [a for a in _toolbar(window).actions() if a.text() in in_file]
    assert [a.text() for a in shared] == ["Open Score…", "Open Audio…",
                                          "Import Tempo…"]
    for action in shared:
        assert action is in_file[action.text()], action.text()


def test_toolbar_holds_the_openers(window) -> None:
    """The three things you do first are in the window, not only up in
    the OS menu bar (ruling 2026-07-30). Fit left the toolbar in B2."""
    # the page readout, the spring and Export are widget actions, so
    # they carry no text
    texts = [a.text() for a in _toolbar(window).actions() if a.text()]
    assert texts == ["Open Score…", "Open Audio…", "Import Tempo…",
                     "Previous", "Next"]
    assert "Fit" in _texts(window.menus.view_menu)      # still in View


def test_export_button_is_the_file_menu_action(window) -> None:
    """One QAction behind the menu item, Ctrl+E and the button — so the
    button is dead until a score loads, and lives after (B2)."""
    button = window.menus.export_button
    assert button.defaultAction() is window.menus.export_action
    assert button.objectName() == "ExportButton"        # the accent hook
    assert not button.isEnabled()                       # needs a score
    window.menus.export_action.setEnabled(True)
    assert button.isEnabled()
    window.menus.export_action.setEnabled(False)


def test_export_sits_on_the_right_edge(window) -> None:
    """A spring between the pager and Export, so Export is right-aligned
    at any width — and still visible at a narrow one."""
    toolbar = _toolbar(window)
    window.resize(760, 600)
    window.show()
    QApplication.processEvents()
    button = window.menus.export_button
    assert button.isVisible()
    # the spring did its job: Export ends within a hair of the right edge
    assert toolbar.width() - button.geometry().right() < 12
    # and it is to the right of everything else on the bar
    pager = toolbar.widgetForAction(window.menus.next_action)
    assert button.geometry().left() > pager.geometry().right()
    window.hide()


def test_toolbar_is_icons_with_labels_only_on_the_openers(window) -> None:
    """Icon + label on the three openers, icon-only on the rest — the
    tooltip carries the name there, so nothing is nameless (A2)."""
    toolbar = _toolbar(window)
    labelled = {"Open Score…", "Open Audio…", "Import Tempo…"}
    for action in toolbar.actions():
        if not action.text():
            continue                             # the page readout widget
        assert not action.icon().isNull(), action.text()
        assert action.toolTip(), action.text()
        button = toolbar.widgetForAction(action)
        expected = (Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                    if action.text() in labelled
                    else Qt.ToolButtonStyle.ToolButtonIconOnly)
        assert button.toolButtonStyle() == expected, action.text()


def test_undo_and_redo_carry_icons(window) -> None:
    assert not window.menus.undo_action.icon().isNull()
    assert not window.menus.redo_action.icon().isNull()


def test_window_level_shortcut_registration(window) -> None:
    """Every §1a window-level action is registered on the window so its
    shortcut fires regardless of focus."""
    strip = window.lower_zone.strip
    registered = window.actions()
    for action in (window.menus.undo_action, window.menus.redo_action,
                   strip.play_action, strip.to_start_action,
                   *window.seek_keys.actions):
        assert action in registered
    shortcuts = [a.shortcut() for a in registered]
    for expected in (QKeySequence(QKeySequence.StandardKey.Undo),
                     QKeySequence(QKeySequence.StandardKey.Redo),
                     QKeySequence(QKeySequence.StandardKey.Save),
                     QKeySequence(QKeySequence.StandardKey.Open),
                     QKeySequence("Space"), QKeySequence("F5"),
                     QKeySequence("Home"), QKeySequence("Left"),
                     QKeySequence("Right"), QKeySequence("Shift+Left"),
                     QKeySequence("Shift+Right")):
        assert expected in shortcuts


def test_shortcut_sweep_assignments(window) -> None:
    """The full §1a shortcut table, on the actions that own them."""
    menus = window.menus
    shortcuts = {a.text(): a.shortcut()
                 for menu in (menus.file_menu, menus.edit_menu,
                              menus.view_menu, menus.playback_menu)
                 for a in menu.actions() if not a.isSeparator()}
    assert shortcuts["Open Score…"] \
        == QKeySequence(QKeySequence.StandardKey.Open)
    assert shortcuts["Open Project…"] == QKeySequence("Ctrl+Shift+O")
    assert shortcuts["Export Video…"] == QKeySequence("Ctrl+E")
    assert shortcuts["Fit"] == QKeySequence("Ctrl+0")
    assert shortcuts["Previous"] \
        == QKeySequence(QKeySequence.StandardKey.MoveToPreviousPage)
    assert shortcuts["Next"] \
        == QKeySequence(QKeySequence.StandardKey.MoveToNextPage)
    assert shortcuts["Reload Tempo"] == QKeySequence("F5")
    assert shortcuts["Go to Start"] == QKeySequence("Home")
    assert shortcuts["Back 1 Second"] == QKeySequence("Left")
    assert shortcuts["Forward 5 Seconds"] == QKeySequence("Shift+Right")


def test_score_menu_is_the_parts_menu_home(window) -> None:
    """Empty until a load; PartsMenu.rebuild repopulates it (M1.6 —
    the menu itself lives in the chrome, its content in ui/parts_menu)."""
    assert window.menuBar().actions()[3].text() == "&Score"
    assert not window.menus.score_menu.actions()
