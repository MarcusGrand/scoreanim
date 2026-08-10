"""The stage's right-click Staves menu (2026-08-09), offscreen: the
menu lists the FULL roster (hidden parts included) with check state
read off the document at build time, a trigger executes SetPartHidden
(undo restores), the last visible part is grayed, and the view's
contextMenuEvent reports position without deciding anything.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QContextMenuEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from scoreanim.core.project import SetPartHidden  # noqa: E402
from scoreanim.core.score.identity import PartId  # noqa: E402
from scoreanim.core.score.musicxml_prep import PartInfo  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.stage_menu import StageMenu  # noqa: E402
from scoreanim.ui.stage_view import StageView  # noqa: E402

PARTS = (PartInfo(0, PartId("P1"), "Flute", 1, 1),
         PartInfo(1, PartId("P2"), "Viola", 1, 2),
         PartInfo(2, PartId("P3"), "Cello", 1, 3))
P1, P2, P3 = PartId("P1"), PartId("P2"), PartId("P3")


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bound(qapp):
    state = AppState()
    view = StageView()
    stage_menu = StageMenu(state, view, None)
    stage_menu.bind(PARTS)
    return stage_menu, state, view


def _staves_actions(menu):
    staves = next(a.menu() for a in menu.actions()
                  if a.text() == "Staves")
    return staves.actions()


def test_build_lists_every_part_checked(bound) -> None:
    stage_menu, _, _ = bound
    menu = stage_menu.build()
    actions = _staves_actions(menu)
    assert [a.text() for a in actions] == ["Flute", "Viola", "Cello"]
    assert all(a.isCheckable() and a.isChecked() for a in actions)


def test_a_hidden_part_is_listed_unchecked(bound) -> None:
    """The whole point of the full roster: the hidden part stays in the
    menu, unchecked, so it can be shown again."""
    stage_menu, state, _ = bound
    state.execute(SetPartHidden(P2, True, (P1, P2, P3)))
    menu = stage_menu.build()
    actions = _staves_actions(menu)
    assert [a.isChecked() for a in actions] == [True, False, True]


def test_triggering_hides_and_undo_restores(bound) -> None:
    stage_menu, state, _ = bound
    menu = stage_menu.build()
    actions = _staves_actions(menu)
    actions[1].trigger()                 # toggles the check, then fires
    assert state.doc.hidden_parts == frozenset({P2})
    assert state.undo_text() == "hide part"
    state.undo()
    assert state.doc.hidden_parts == frozenset()
    # a fresh build reads the restored document
    menu2 = stage_menu.build()
    assert all(a.isChecked() for a in _staves_actions(menu2))


def test_showing_a_hidden_part_again(bound) -> None:
    stage_menu, state, _ = bound
    state.execute(SetPartHidden(P3, True, (P1, P2, P3)))
    menu = stage_menu.build()
    actions = _staves_actions(menu)
    actions[2].trigger()
    assert state.doc.hidden_parts == frozenset()


def test_the_last_visible_part_is_grayed(bound) -> None:
    stage_menu, state, _ = bound
    state.execute(SetPartHidden(P1, True, (P1, P2, P3)))
    state.execute(SetPartHidden(P3, True, (P1, P2, P3)))
    menu = stage_menu.build()
    actions = _staves_actions(menu)
    assert [a.isEnabled() for a in actions] == [True, False, True]


def test_no_menu_before_a_score_loads(qapp) -> None:
    stage_menu = StageMenu(AppState(), StageView(), None)
    assert stage_menu.build() is None


# --- the per-system half (2026-08-10) --------------------------------------

from PySide6.QtCore import QPointF  # noqa: E402

from scoreanim.core.engraving.systems import SystemBand  # noqa: E402
from scoreanim.core.engraving.types import Rect  # noqa: E402
from scoreanim.core.project import SetSystemStaffHidden  # noqa: E402


class _Scenes:
    def __init__(self, count: int) -> None:
        self.scenes = [QGraphicsScene() for _ in range(count)]


@pytest.fixture
def with_systems(bound):
    """Two systems on page 1: system 1 starts at m1 (P1 plays there),
    system 2 starts at m5 (only P1 plays; P2's and P3's staves are
    hideable)."""
    stage_menu, state, view = bound
    scenes = _Scenes(2)
    bands = {1: SystemBand(system=1, page=1, rect=Rect(0, 100, 700, 200)),
             2: SystemBand(system=2, page=1, rect=Rect(0, 400, 700, 200))}
    stage_menu.bind_systems(scenes, bands, {1: 1, 2: 5},
                            {1: frozenset({"P1", "P2", "P3"}),
                             2: frozenset({"P1"})})
    return stage_menu, state, scenes


def _system_actions(menu):
    sub = next((a.menu() for a in menu.actions()
                if a.text() == "Staves in This System"), None)
    return sub.actions() if sub is not None else None


def test_the_system_submenu_resolves_the_band_under_the_cursor(
        with_systems) -> None:
    stage_menu, state, scenes = with_systems
    menu = stage_menu.build(scenes.scenes[0], QPointF(100, 450))
    actions = _system_actions(menu)
    assert [a.text() for a in actions] == ["Flute", "Viola", "Cello"]
    # P1 plays in system 2 -> grayed; the empty staves are hideable
    assert [a.isEnabled() for a in actions] == [False, True, True]
    assert all(a.isChecked() for a in actions)


def test_no_system_submenu_off_the_score(with_systems) -> None:
    stage_menu, _, scenes = with_systems
    foreign = QGraphicsScene()
    menu = stage_menu.build(foreign, QPointF(100, 450))
    assert _system_actions(menu) is None
    menu2 = stage_menu.build(None, None)
    assert _system_actions(menu2) is None


def test_triggering_hides_in_that_system_and_undo_restores(
        with_systems) -> None:
    stage_menu, state, scenes = with_systems
    menu = stage_menu.build(scenes.scenes[0], QPointF(100, 450))
    _system_actions(menu)[1].trigger()          # Viola, system @ m5
    assert dict(state.doc.system_staff_hides) == {5: frozenset({P2})}
    assert state.undo_text() == "hide staff in system"
    state.undo()
    assert state.doc.system_staff_hides == {}


def test_a_hidden_staff_is_unchecked_and_always_clearable(
        with_systems) -> None:
    stage_menu, state, scenes = with_systems
    state.execute(SetSystemStaffHidden(5, P2, True, (P1, P2, P3)))
    # even with the mechanism off (global hiding disabled), the entry
    # stays enabled so a stale hide can be cleared
    from scoreanim.core.project import SetHideEmptyStaves
    state.execute(SetHideEmptyStaves(False))
    menu = stage_menu.build(scenes.scenes[0], QPointF(100, 450))
    actions = _system_actions(menu)
    assert [a.isChecked() for a in actions] == [True, False, True]
    assert actions[1].isEnabled()               # clearable
    assert not actions[2].isEnabled()           # mechanism off
    actions[1].trigger()
    assert state.doc.system_staff_hides == {}


def test_system_one_grays_without_the_first_system_option(
        with_systems) -> None:
    stage_menu, state, scenes = with_systems
    menu = stage_menu.build(scenes.scenes[0], QPointF(100, 150))
    actions = _system_actions(menu)
    # every part plays in system 1 here anyway, but the gate is the
    # option: nothing is hideable on system 1 until it is on
    assert not any(a.isEnabled() for a in actions)
    from scoreanim.core.project import SetHideFirstSystem
    state.execute(SetHideFirstSystem(True))
    # with the option on the gate falls to the notes: rebind system 1
    # with only P1 playing and the other two become hideable
    stage_menu.bind_systems(
        scenes, {1: SystemBand(system=1, page=1,
                               rect=Rect(0, 100, 700, 200))},
        {1: 1}, {1: frozenset({"P1"})})
    menu2 = stage_menu.build(scenes.scenes[0], QPointF(100, 150))
    assert [a.isEnabled() for a in _system_actions(menu2)] == \
        [False, True, True]


def test_view_reports_the_right_click(qapp) -> None:
    """The view hook: a context-menu event on a view with a scene emits
    (global pos, scene pos); without a scene it emits nothing. A bare
    view — no StageMenu attached, or the emit would open a real modal
    menu and block the test."""
    view = StageView()
    seen: list = []
    view.context_menu_requested.connect(
        lambda global_pos, scene_pos: seen.append((global_pos, scene_pos)))
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse,
                              QPoint(10, 10), QPoint(100, 100))
    view.contextMenuEvent(event)         # no scene yet
    assert seen == []
    view.setScene(QGraphicsScene())
    view.contextMenuEvent(event)
    assert len(seen) == 1
    assert seen[0][0] == QPoint(100, 100)
