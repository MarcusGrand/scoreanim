"""The lane gear, offscreen: the lane's view options in a popup menu.

Everything here sets `AppState.grid` (rule 5 view state), so the checks
are the same three every time — the state moved, the menu shows it, and
the undo stack never heard about it.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.timing import BARS, EIGHTH, GRID_UNITS  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.grid_options import LaneDisplay  # noqa: E402
from scoreanim.ui.lane_menu import LaneOptionsButton  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_the_menu_opens_on_the_state_the_lane_is_in(qapp) -> None:
    state = AppState()
    gear = LaneOptionsButton(state)

    assert gear.lane_actions[LaneDisplay.TICKS].isChecked()
    assert not gear.lane_actions[LaneDisplay.TEMPO].isChecked()
    assert gear.unit_actions[GRID_UNITS.index(BARS)].isChecked()
    assert gear.flatten_action.isChecked()          # flatten is the default
    assert "Ticks" in gear.toolTip()                # readable without opening


def test_picking_a_lane_moves_the_view_state_and_nothing_else(qapp) -> None:
    """Rule 5: which lane is showing is view state — no command, no
    dirty document."""
    state = AppState()
    gear = LaneOptionsButton(state)

    gear.lane_actions[LaneDisplay.TEMPO].trigger()
    assert state.grid.display is LaneDisplay.TEMPO
    assert "Tempo" in gear.toolTip()
    gear.lane_actions[LaneDisplay.TICKS].trigger()
    assert state.grid.display is LaneDisplay.TICKS

    assert not state.can_undo and not state.is_dirty


def test_the_grid_step_and_flatten_still_work_from_the_menu(qapp) -> None:
    state = AppState()
    gear = LaneOptionsButton(state)

    gear.unit_actions[GRID_UNITS.index(EIGHTH)].trigger()
    assert state.grid.unit == EIGHTH
    assert gear.unit_actions[GRID_UNITS.index(EIGHTH)].isChecked()
    assert not gear.unit_actions[GRID_UNITS.index(BARS)].isChecked()

    gear.flatten_action.trigger()                   # untick: keep the shape
    assert not state.grid.flatten
    gear.flatten_action.trigger()
    assert state.grid.flatten

    assert not state.can_undo and not state.is_dirty


def test_the_tempo_lane_grays_out_what_it_cannot_use(qapp) -> None:
    """Grid step and Flatten only mean something to the tick grid."""
    state = AppState()
    gear = LaneOptionsButton(state)
    assert all(action.isEnabled() for action in gear.unit_actions)
    assert gear.flatten_action.isEnabled()

    state.grid.set_display(LaneDisplay.TEMPO)
    assert not any(action.isEnabled() for action in gear.unit_actions)
    assert not gear.flatten_action.isEnabled()

    state.grid.set_display(LaneDisplay.TICKS)
    assert gear.flatten_action.isEnabled()


def test_a_resync_never_looks_like_a_click(qapp) -> None:
    """The grid is set from elsewhere too (a lane drag, a project load).
    The menu follows it without echoing back a second set."""
    state = AppState()
    gear = LaneOptionsButton(state)
    changes = []
    state.grid.changed.connect(lambda: changes.append(state.grid.unit))

    state.grid.set_unit(EIGHTH)
    assert gear.unit_actions[GRID_UNITS.index(EIGHTH)].isChecked()
    assert len(changes) == 1                        # one signal, not two

    state.grid.set_flatten(False)
    assert not gear.flatten_action.isChecked()
    assert len(changes) == 2
