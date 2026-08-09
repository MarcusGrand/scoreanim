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
