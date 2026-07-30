"""The lane's ticks mode, offscreen: dragging a grid line onto the
waveform edits tempo and holds its anchors, in one undo entry.

The maths lives in tests/test_retime.py and the command in
tests/test_project_commands.py; this pins the gesture — which line the
pointer grabs, which anchors it uses, and what one drag costs the undo
stack.

Geometry throughout: eight 4/4 bars at 120 bpm with no offset, so beat b
sits at b/2 seconds, and a 20 s axis across 800 px puts one second at
40 px. Bar 3 starts at beat 8 = 4.0 s = x 160.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.score.model import MeasureInfo  # noqa: E402
from scoreanim.core.project import (AddTempoEvent,  # noqa: E402
                                    SetBeatLock)
from scoreanim.core.timing import (BARS, EIGHTH,  # noqa: E402
                                   QUARTER, SIXTEENTH, TempoMap)
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.grid_options import LaneDisplay  # noqa: E402
from scoreanim.ui.tempo_lane import TempoLaneView  # noqa: E402

MEASURES = tuple(MeasureInfo(number=n + 1, start=n * 4.0, quarter_length=4.0)
                 for n in range(8))


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def lane(app):
    state = AppState()
    state.set_measures(MEASURES)
    state.axis.set_duration(20.0)
    view = TempoLaneView(state)
    view.resize(800, 130)
    state.grid.set_display(LaneDisplay.TICKS)
    return view


def audio_at(state, beat: float) -> float:
    """Where a beat sits on the recording, the way the lane draws it."""
    return state.doc.timing.offset_seconds + TempoMap(
        list(state.doc.timing.tempo_events)).seconds_at(beat)


def press(lane, x, y=60.0):
    lane.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, x, y))


def drag_to(lane, x, y=60.0, modifiers=Qt.KeyboardModifier.NoModifier):
    lane.mouseMoveEvent(_mouse(QMouseEvent.Type.MouseMove, x, y, modifiers))


def release(lane, x, y=60.0):
    lane.mouseReleaseEvent(_mouse(QMouseEvent.Type.MouseButtonRelease, x, y))


def double_click(lane, x, y=60.0):
    """Qt's real order: the first click's press/release land first."""
    press(lane, x, y)
    release(lane, x, y)
    lane.mouseDoubleClickEvent(_mouse(QMouseEvent.Type.MouseButtonDblClick,
                                      x, y))


def _mouse(kind, x, y, modifiers=Qt.KeyboardModifier.NoModifier):
    button = Qt.MouseButton.LeftButton
    return QMouseEvent(kind, QPointF(x, y), button, button, modifiers)


def test_the_fixture_geometry_is_what_the_tests_assume(lane) -> None:
    assert audio_at(lane.state, 8.0) == 4.0
    assert lane.x_of_beat(8.0) == pytest.approx(160.0)


def test_dragging_a_barline_evens_out_the_span_before_it(lane) -> None:
    state = lane.state
    press(lane, 160.0)                       # bar 3's line, at 4.0 s
    drag_to(lane, 200.0)                     # one second later
    release(lane, 200.0)
    assert audio_at(state, 8.0) == pytest.approx(5.0, abs=1e-6)
    m = TempoMap(list(state.doc.timing.tempo_events))
    steps = [round(m.seconds_at(b + 1.0) - m.seconds_at(b), 9)
             for b in range(8)]
    assert len(set(steps)) == 1              # start -> bar 3, evenly
    assert audio_at(state, 0.0) == 0.0       # the score start holds


def test_a_drag_locks_the_line_it_placed(lane) -> None:
    state = lane.state
    press(lane, 160.0)
    drag_to(lane, 200.0)
    release(lane, 200.0)
    assert state.doc.timing.locked_beats == (8.0,)


def test_a_later_drag_leaves_an_earlier_placement_alone(lane) -> None:
    """The whole point of the auto-lock: aligning left to right holds
    everything already put down."""
    state = lane.state
    press(lane, 160.0)                       # bar 3 -> 5.0 s
    drag_to(lane, 200.0)
    release(lane, 200.0)
    press(lane, lane.x_of_beat(16.0))        # bar 5, wherever it now is
    drag_to(lane, 400.0)
    release(lane, 400.0)
    assert audio_at(state, 16.0) == pytest.approx(10.0, abs=1e-6)
    assert audio_at(state, 8.0) == pytest.approx(5.0, abs=1e-6)
    assert state.doc.timing.locked_beats == (8.0, 16.0)


def test_one_drag_is_one_undo_entry(lane) -> None:
    state = lane.state
    before = state.doc.timing.tempo_events
    press(lane, 160.0)
    for x in (170.0, 180.0, 190.0, 200.0):   # a real drag sends many moves
        drag_to(lane, x)
    release(lane, 200.0)
    assert state.undo_text() == "align beat"
    state.undo()
    assert state.doc.timing.tempo_events == before
    assert state.doc.timing.locked_beats == ()   # the lock went back too
    assert not state.can_undo


def test_the_music_after_the_line_keeps_its_tempo_and_slides(lane) -> None:
    state = lane.state
    was = {beat: audio_at(state, beat) for beat in (12.0, 16.0, 32.0)}
    press(lane, 160.0)
    drag_to(lane, 200.0)
    release(lane, 200.0)
    for beat, before in was.items():
        assert audio_at(state, beat) == pytest.approx(before + 1.0, abs=1e-6)


def test_a_lock_after_the_line_pins_the_tail(lane) -> None:
    state = lane.state
    state.execute(SetBeatLock(16.0, True))
    was = audio_at(state, 16.0)
    press(lane, 160.0)
    drag_to(lane, 200.0)
    release(lane, 200.0)
    assert audio_at(state, 8.0) == pytest.approx(5.0, abs=1e-6)
    assert audio_at(state, 16.0) == pytest.approx(was, abs=1e-9)


def test_double_click_locks_the_line_and_unlocks_it_again(lane) -> None:
    state = lane.state
    double_click(lane, 160.0)
    assert state.doc.timing.locked_beats == (8.0,)
    assert state.undo_text() == "lock beat"
    double_click(lane, 160.0)
    assert state.doc.timing.locked_beats == ()
    assert state.undo_text() == "unlock beat"


def test_a_lock_stays_grabbable_when_the_grid_would_not_show_it(lane
                                                                ) -> None:
    """A lock set at 1/8 must not vanish, or become ungrabbable, when the
    user switches to Bars — it still steers every drag."""
    state = lane.state
    state.grid.set_unit(EIGHTH)
    double_click(lane, 170.0)                # beat 8.5, an off-beat
    assert state.doc.timing.locked_beats == (8.5,)
    state.grid.set_unit(BARS)
    mode = lane._modes[LaneDisplay.TICKS]
    assert 8.5 in [t.beat for _x, t in mode._handles()]
    press(lane, 170.0)
    drag_to(lane, 180.0)
    release(lane, 180.0)
    assert audio_at(state, 8.5) == pytest.approx(4.5, abs=1e-6)


def test_keep_shape_preserves_tempo_detail_inside_the_span(lane) -> None:
    state = lane.state
    state.execute(AddTempoEvent(6.0, 60.0))
    state.grid.set_flatten(False)
    press(lane, 160.0)
    drag_to(lane, 200.0)
    release(lane, 200.0)
    assert 6.0 in [e.position for e in state.doc.timing.tempo_events]


def test_alt_flips_the_drag_rule_for_one_drag(lane) -> None:
    state = lane.state                       # Flatten is set; Alt keeps shape
    state.execute(AddTempoEvent(6.0, 60.0))
    press(lane, 160.0)
    drag_to(lane, 200.0, modifiers=Qt.KeyboardModifier.AltModifier)
    release(lane, 200.0)
    assert 6.0 in [e.position for e in state.doc.timing.tempo_events]


def test_dragging_the_first_line_sets_the_offset(lane) -> None:
    state = lane.state
    press(lane, 0.0)                         # bar 1's line, at 0.0 s
    drag_to(lane, 60.0)                      # 1.5 s in
    release(lane, 60.0)
    assert state.undo_text() == "set offset"
    assert state.doc.timing.offset_seconds == pytest.approx(1.5)
    assert state.doc.timing.tempo_events[0].bpm == 120.0    # tempo untouched
    assert audio_at(state, 8.0) == pytest.approx(5.5)       # all of it slid


def test_escape_cancels_a_drag_and_leaves_no_undo_entry(lane) -> None:
    state = lane.state
    before = state.doc.timing.tempo_events
    press(lane, 160.0)
    drag_to(lane, 220.0)
    assert state.doc.timing.tempo_events != before          # preview showing
    lane.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                 Qt.KeyboardModifier.NoModifier))
    assert state.doc.timing.tempo_events == before
    assert not state.can_undo


def test_switching_mode_mid_drag_cancels_it(lane) -> None:
    state = lane.state
    before = state.doc.timing.tempo_events
    press(lane, 160.0)
    drag_to(lane, 220.0)
    state.grid.set_display(LaneDisplay.TEMPO)
    assert state.doc.timing.tempo_events == before
    assert not state.can_undo


def test_a_press_that_misses_every_line_seeks(lane) -> None:
    seeks: list[float] = []
    lane.state.seek_requested.connect(seeks.append)
    press(lane, 100.0)                       # between bar 2 and bar 3
    release(lane, 100.0)
    assert seeks == [pytest.approx(2.5)]
    assert not lane.state.can_undo


def test_a_press_on_a_line_does_not_seek(lane) -> None:
    seeks: list[float] = []
    lane.state.seek_requested.connect(seeks.append)
    press(lane, 160.0)
    release(lane, 160.0)                     # a click, not a drag
    assert seeks == []
    assert not lane.state.can_undo


def test_a_crowded_grid_thins_out_and_its_hidden_ticks_are_not_grabbable(
        lane) -> None:
    state = lane.state
    state.grid.set_unit(SIXTEENTH)
    mode = lane._modes[LaneDisplay.TICKS]
    assert mode.grid_unit() == EIGHTH             # 20 px a beat: 1/16 would crowd
    assert all(abs(t.beat / 0.5 - round(t.beat / 0.5)) < 1e-9
               for _x, t in mode._handles())
    state.axis.set_visible(4.0, 6.0)          # zoom in: room for all of them
    assert mode.grid_unit() == SIXTEENTH


def test_the_lane_paints_in_both_modes(lane) -> None:
    for display in LaneDisplay:
        lane.state.grid.set_display(display)
        for unit in (QUARTER, SIXTEENTH):
            lane.state.grid.set_unit(unit)
            lane.grab()                       # would raise on a paint error


def test_the_view_does_not_move_across_a_whole_drag(lane) -> None:
    """The regression test for the reported jump, end to end: no audio
    bound, so retiming changes the score's own length on every preview
    frame, and the axis must not re-fit under the cursor."""
    state = lane.state
    state.axis.set_visible(2.0, 8.0)
    window = (state.axis.t0, state.axis.t1)
    press(lane, lane.x_of_beat(8.0))
    for x in (200.0, 240.0, 300.0, 260.0):
        drag_to(lane, x)
        state.axis.set_duration(19.0 + x / 100.0)   # what playback does
        assert (state.axis.t0, state.axis.t1) == window
    release(lane, 260.0)
    assert (state.axis.t0, state.axis.t1) == window


def test_the_grid_step_is_frozen_for_the_length_of_a_drag(lane) -> None:
    """Retiming a span changes px per beat, so the drawn step could
    cross a crowding threshold mid-gesture — half the lines appearing or
    vanishing under the cursor. The step is captured at press, whatever
    would otherwise change it."""
    state = lane.state
    state.grid.set_unit(QUARTER)
    mode = lane._modes[LaneDisplay.TICKS]
    assert mode.grid_unit() == QUARTER
    press(lane, lane.x_of_beat(8.0))
    drag_to(lane, 300.0)
    state.grid.set_unit(SIXTEENTH)           # anything that would change it
    state.axis.set_visible(3.9, 4.1)
    assert mode.grid_unit() == QUARTER       # still the step we started on
    release(lane, 300.0)
    assert mode.grid_unit() == SIXTEENTH     # and it catches up after
