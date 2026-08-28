"""Static chrome (M1.5), offscreen: the five menus in order, the
toolbar (the three openers, then the page steps and Fit), shared
Play/Follow QActions in the Playback menu, dock toggles in View, and
window-level shortcut registration — the structural half of the brief's
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


def test_five_menus_in_roadmap_order(window) -> None:
    menus = window.menus
    assert [a.text() for a in window.menuBar().actions()] \
        == ["&File", "&Edit", "&View", "&Score", "&Playback"]
    assert [m.title() for m in (menus.file_menu, menus.edit_menu,
                                menus.view_menu, menus.score_menu,
                                menus.playback_menu)] \
        == ["&File", "&Edit", "&View", "&Score", "&Playback"]


def test_file_and_edit_contents(window) -> None:
    # Open Score… is on the toolbar, not in here (ruling 2026-07-30)
    assert _texts(window.menus.file_menu) \
        == ["Open Project…", "Save Project", "Save Project As…",
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
    """Menu, strip button, and shortcut are ONE QAction for Play; menu
    and inspector toggle likewise for Follow (brief flag 3)."""
    actions = window.menus.playback_menu.actions()
    assert actions[0] is window.lower_zone.strip.play_action
    assert actions[1] is window.inspector.follow_action
    # the two openers moved to the toolbar; Reload Tempo stayed
    assert _texts(window.menus.playback_menu) \
        == ["Play", "Follow", "Reload Tempo"]


def test_toolbar_holds_the_openers(window) -> None:
    """The three things you do first are in the window, not up in the
    OS menu bar (ruling 2026-07-30)."""
    # the page readout is a widget action, so it carries no text
    texts = [a.text() for a in _toolbar(window).actions() if a.text()]
    assert texts == ["Open Score…", "Open Audio…", "Import Tempo…",
                     "Previous", "Next", "Fit"]


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
                   strip.play_action):
        assert action in registered
    shortcuts = [a.shortcut() for a in registered]
    for expected in (QKeySequence(QKeySequence.StandardKey.Undo),
                     QKeySequence(QKeySequence.StandardKey.Redo),
                     QKeySequence(QKeySequence.StandardKey.Save),
                     QKeySequence(QKeySequence.StandardKey.Open),
                     QKeySequence("Space"), QKeySequence("F5")):
        assert expected in shortcuts


def test_shortcut_sweep_assignments(window) -> None:
    """The full §1a shortcut table, on the actions that own them."""
    menus = window.menus
    shortcuts = {a.text(): a.shortcut()
                 for menu in (menus.file_menu, menus.edit_menu,
                              menus.view_menu, menus.playback_menu)
                 for a in menu.actions() if not a.isSeparator()}
    shortcuts.update({a.text(): a.shortcut()
                      for a in _toolbar(window).actions() if a.text()})
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


def test_score_menu_is_the_parts_menu_home(window) -> None:
    """Empty until a load; PartsMenu.rebuild repopulates it (M1.6 —
    the menu itself lives in the chrome, its content in ui/parts_menu)."""
    assert window.menuBar().actions()[3].text() == "&Score"
    assert not window.menus.score_menu.actions()
