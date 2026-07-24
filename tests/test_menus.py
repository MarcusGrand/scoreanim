"""Static chrome (M1.5), offscreen: the five menus in order, the slim
toolbar (Open Score off it), shared Play/Follow QActions in the
Playback menu, dock toggles in View, and window-level shortcut
registration — the structural half of the brief's click-through/
shortcut-sweep verify (the interactive half is run by hand).

Menus are read via the refs MainMenus holds, never `QAction.menu()` —
re-wrapping a menu and letting the wrapper be garbage-collected can
delete the C++ menu (the PySide6 quirk that made MainMenus keep them).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


def test_five_menus_in_roadmap_order(window) -> None:
    menus = window.menus
    assert [a.text() for a in window.menuBar().actions()] \
        == ["&File", "&Edit", "&View", "&Score", "&Playback"]
    assert [m.title() for m in (menus.file_menu, menus.edit_menu,
                                menus.view_menu, menus.score_menu,
                                menus.playback_menu)] \
        == ["&File", "&Edit", "&View", "&Score", "&Playback"]


def test_file_and_edit_contents(window) -> None:
    assert _texts(window.menus.file_menu) \
        == ["Open Score…", "Open Project…", "Save Project",
            "Save Project As…", "Export Video…"]
    assert _texts(window.menus.edit_menu) == ["Undo", "Redo", "Texts…"]
    assert not window.menus.export_action.isEnabled()   # needs a score
    assert not window.menus.texts_action.isEnabled()


def test_view_menu_holds_dock_toggles(window) -> None:
    actions = window.menus.view_menu.actions()
    assert window.inspector.toggleViewAction() in actions
    assert window.lower_zone.toggleViewAction() in actions
    assert _texts(window.menus.view_menu) \
        == ["Fit", "◀", "▶", "Inspector", "Lower Zone"]


def test_playback_menu_shares_the_component_actions(window) -> None:
    """Menu, strip button, and shortcut are ONE QAction for Play; menu
    and inspector toggle likewise for Follow (brief flag 3)."""
    actions = window.menus.playback_menu.actions()
    assert actions[0] is window.lower_zone.strip.play_action
    assert actions[1] is window.inspector.follow_action
    assert _texts(window.menus.playback_menu) \
        == ["▶ Play", "Follow", "Open Audio…", "Import Tempo…",
            "Reload Tempo"]


def test_toolbar_is_slim(window) -> None:
    toolbar = window.findChild(QToolBar, "MainToolbar")
    texts = [a.text() for a in toolbar.actions() if not a.isSeparator()]
    assert "Open Score…" not in texts                   # dropped (M1.5)
    assert texts[0] == "◀" and "▶" in texts and "Fit" in texts


def test_window_level_shortcut_registration(window) -> None:
    """Every §1a window-level action is registered on the window so its
    shortcut fires regardless of focus."""
    strip = window.lower_zone.strip
    registered = window.actions()
    for action in (window.menus.undo_action, window.menus.redo_action,
                   strip.play_action, strip.arm_taps_action,
                   strip.tap_action):
        assert action in registered
    shortcuts = [a.shortcut() for a in registered]
    for expected in (QKeySequence(QKeySequence.StandardKey.Undo),
                     QKeySequence(QKeySequence.StandardKey.Redo),
                     QKeySequence(QKeySequence.StandardKey.Save),
                     QKeySequence("Space"), QKeySequence("T"),
                     QKeySequence("Shift+T"), QKeySequence("F5")):
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
    assert shortcuts["◀"] \
        == QKeySequence(QKeySequence.StandardKey.MoveToPreviousPage)
    assert shortcuts["▶"] \
        == QKeySequence(QKeySequence.StandardKey.MoveToNextPage)
    assert shortcuts["Reload Tempo"] == QKeySequence("F5")


def test_score_menu_is_the_parts_menu_home(window) -> None:
    """Empty until a load; PartsMenu.rebuild repopulates it (M1.6 —
    the menu itself lives in the chrome, its content in ui/parts_menu)."""
    assert window.menuBar().actions()[3].text() == "&Score"
    assert not window.menus.score_menu.actions()
