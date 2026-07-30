"""TransportStrip / LowerZone (M1.3), offscreen: the controller wiring
that moved out of the window — slider seeks, time feedback, play-text
flip, pause-disarms-taps — behaves exactly as the alpha window did.

The strip is exercised against fake controller QObjects (real signals,
recorded calls); the zone against a real AppState (its lanes observe
only that).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QDockWidget  # noqa: E402

from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.transport import LowerZone, TransportStrip  # noqa: E402


class FakePlayback(QObject):
    time_changed = Signal(float, float)
    playing_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.seeks: list[float] = []
        self.toggles = 0

    def toggle_play(self) -> None:
        self.toggles += 1

    def seek(self, seconds: float) -> None:
        self.seeks.append(seconds)


class FakeTapRecorder(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.armed = False
        self.taps = 0

    def set_armed(self, armed: bool) -> None:
        self.armed = armed

    def tap(self) -> None:
        self.taps += 1


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def strip(qapp):
    playback = FakePlayback()
    taps = FakeTapRecorder()
    return TransportStrip(AppState(), playback, taps), playback, taps


def test_actions_drive_controller(strip) -> None:
    widget, playback, taps = strip
    widget.play_action.trigger()
    assert playback.toggles == 1
    widget.arm_taps_action.setChecked(True)
    assert taps.armed
    widget.tap_action.trigger()
    assert taps.taps == 1


def test_time_feedback_updates_label_and_slider(strip) -> None:
    widget, playback, _ = strip
    playback.time_changed.emit(65.4, 120.0)
    assert widget._time_label.text() == " 1:05.4 / 2:00.0 "
    assert widget._slider.maximum() == 120000
    assert widget._slider.value() == 65400


def test_slider_untouched_while_user_drags(strip) -> None:
    widget, playback, _ = strip
    playback.time_changed.emit(10.0, 120.0)
    widget._slider.setSliderDown(True)
    playback.time_changed.emit(50.0, 120.0)
    assert widget._slider.value() == 10000       # no fight with the drag
    assert widget._time_label.text().startswith(" 0:50.0")


def test_drag_and_keyboard_step_seek(strip) -> None:
    widget, playback, _ = strip
    widget._slider.setRange(0, 120000)
    widget._slider.setSliderDown(True)
    widget._slider.sliderMoved.emit(2500)        # drag → seek
    widget._slider.setSliderDown(False)
    widget._slider.setValue(4000)                # keyboard/page step → seek
    assert playback.seeks == [2.5, 4.0]


def test_playing_flips_text_and_pause_disarms(strip) -> None:
    widget, playback, taps = strip
    widget.arm_taps_action.setChecked(True)
    playback.playing_changed.emit(True)
    assert widget.play_action.text() == "⏸ Pause"
    assert taps.armed
    playback.playing_changed.emit(False)
    assert widget.play_action.text() == "▶ Play"
    assert not widget.arm_taps_action.isChecked()
    assert not taps.armed                        # pause ended the session


def test_time_fields_commit_one_command_each(qapp) -> None:
    """Tempo/Offset/Swing live on the strip (ruling 2026-07-24) with the
    alpha commit wiring: epsilon no-op guard, one undoable command."""
    state = AppState()
    widget = TransportStrip(state, FakePlayback(), FakeTapRecorder())

    widget._offset_spin.setValue(1.25)
    widget._commit_offset()
    assert state.doc.timing.offset_seconds == 1.25
    widget._commit_offset()                      # same value → no-op
    state.undo()
    assert state.doc.timing.offset_seconds == 0.0
    assert not state.can_undo                    # exactly one command

    widget._bpm_spin.setValue(96.0)
    widget._commit_bpm()
    assert state.doc.timing.tempo_events[0].bpm == 96.0
    state.undo()
    assert not state.can_undo

    # swing with no measures loaded: guarded no-op (no end beat to span)
    widget._swing_spin.setValue(0.67)
    widget._commit_swing()
    assert not state.can_undo


def test_sync_from_document_never_reexecutes(qapp) -> None:
    state = AppState()
    widget = TransportStrip(state, FakePlayback(), FakeTapRecorder())
    widget._offset_spin.setValue(1.25)
    widget._commit_offset()
    widget.sync_from_document(state.doc)         # the resync pass
    assert widget._offset_spin.value() == 1.25
    assert widget._bpm_spin.value() == state.doc.timing.tempo_events[0].bpm
    assert widget._swing_spin.value() == 0.5     # no regions → straight
    state.undo()                                 # resync added no command
    assert not state.can_undo
    widget.sync_from_document(state.doc)
    assert widget._offset_spin.value() == 0.0


def test_lower_zone_is_a_fixed_bottom_dock(qapp) -> None:
    zone = LowerZone(AppState(), FakePlayback(), FakeTapRecorder())
    assert zone.objectName() == "LowerZone"      # saveState identity (M1.8)
    assert zone.features() \
        == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
    assert zone.allowedAreas() == Qt.DockWidgetArea.BottomDockWidgetArea
    # strip above the two lanes, lanes on the internal splitter
    assert zone.strip is not None
    assert zone.waveform.parent() is zone.tempo_lane.parent()  # the splitter


def test_lane_controls_drive_the_view_state_and_no_command(qapp) -> None:
    """Which lines the lane shows is view state (rule 5): the controls set
    AppState.grid and never touch the document or the undo stack."""
    from scoreanim.core.timing import EIGHTH, GRID_UNITS
    from scoreanim.ui.grid_options import LaneDisplay

    state = AppState()
    widget = TransportStrip(state, FakePlayback(), FakeTapRecorder())
    changes = []
    state.grid.changed.connect(lambda: changes.append(state.grid.display))

    # ticks is the default now, so the grid controls start live
    assert state.grid.display is LaneDisplay.TICKS
    assert widget._lane_mode.currentData() is LaneDisplay.TICKS
    assert widget._grid_unit.isEnabled() and widget._shape_button.isEnabled()
    widget._lane_mode.setCurrentIndex(
        widget._lane_mode.findData(LaneDisplay.TEMPO))
    assert state.grid.display is LaneDisplay.TEMPO
    assert not widget._grid_unit.isEnabled()
    widget._lane_mode.setCurrentIndex(
        widget._lane_mode.findData(LaneDisplay.TICKS))

    widget._grid_unit.setCurrentIndex(GRID_UNITS.index(EIGHTH))
    assert state.grid.unit == EIGHTH

    # the button is CHECKED for "keep shape", so the flag inverts
    assert widget._shape_button.text() == "Flatten" and state.grid.flatten
    widget._shape_button.setChecked(True)
    assert not state.grid.flatten
    assert widget._shape_button.text() == "Keep shape"

    assert not state.can_undo and not state.is_dirty


def test_tempo_field_follows_the_lane_selection(qapp) -> None:
    """Clicking a line and typing a tempo is the replacement for dragging
    the old tempo line: it sets the tempo from there to the end."""
    from scoreanim.core.score.model import MeasureInfo
    from scoreanim.core.timing import TempoEvent

    state = AppState()
    state.set_measures(tuple(MeasureInfo(number=n + 1, start=n * 4.0,
                                         quarter_length=4.0)
                             for n in range(8)))
    widget = TransportStrip(state, FakePlayback(), FakeTapRecorder())
    assert widget._bpm_label.text() == "Tempo"

    state.grid.set_selected_beat(8.0)
    assert widget._bpm_label.text() == "Tempo from m3"
    widget._bpm_spin.setValue(90.0)
    widget._commit_bpm()
    assert state.doc.timing.tempo_events == (TempoEvent(0.0, 120.0),
                                             TempoEvent(8.0, 90.0))
    assert state.undo_text() == "set tempo"
    assert widget._bpm_spin.value() == 90.0       # shows what it just set
    widget._commit_bpm()                          # same value -> no-op
    state.undo()
    assert not state.can_undo

    state.grid.set_selected_beat(None)            # back to the initial tempo
    assert widget._bpm_label.text() == "Tempo"
    widget._bpm_spin.setValue(96.0)
    widget._commit_bpm()
    assert state.doc.timing.tempo_events[0].bpm == 96.0
    assert state.undo_text() == "move tempo event"


def test_tempo_previews_while_you_type(qapp) -> None:
    """The ticks have to move with the number, not wait for the click
    outside: every valid value previews, and the whole typing session
    still lands as ONE undo entry."""
    from scoreanim.core.score.model import MeasureInfo
    from scoreanim.core.timing import TempoEvent

    state = AppState()
    state.set_measures(tuple(MeasureInfo(number=n + 1, start=n * 4.0,
                                         quarter_length=4.0)
                             for n in range(8)))
    widget = TransportStrip(state, FakePlayback(), FakeTapRecorder())
    state.grid.set_selected_beat(8.0)
    repaints = []
    state.document_changed.connect(lambda: repaints.append(state.doc))

    widget._bpm_spin.setValue(100.0)              # typing, box still focused
    assert state.doc.timing.tempo_events == (TempoEvent(0.0, 120.0),
                                             TempoEvent(8.0, 100.0))
    assert len(repaints) == 1                     # the lanes were told
    assert state.committed.timing.tempo_events == (TempoEvent(0.0, 120.0),)
    assert not state.can_undo                     # nothing committed yet

    widget._bpm_spin.setValue(90.0)               # still typing
    assert state.doc.timing.tempo_events[1].bpm == 90.0
    # previews apply to the COMMITTED doc, so they never stack up
    assert len(state.doc.timing.tempo_events) == 2
    assert not state.can_undo

    widget._commit_bpm()                          # Enter / click away
    assert state.committed.timing.tempo_events == (TempoEvent(0.0, 120.0),
                                                   TempoEvent(8.0, 90.0))
    assert state.undo_text() == "set tempo"
    state.undo()
    assert not state.can_undo                     # exactly one entry


def test_resync_does_not_fight_the_typing(qapp) -> None:
    """A preview emits document_changed, which comes straight back here
    as a resync — it must not rewrite the number under the cursor."""
    state = AppState()
    widget = TransportStrip(state, FakePlayback(), FakeTapRecorder())

    widget._bpm_spin.setValue(100.0)
    widget.sync_from_document(state.doc)          # what the window does
    assert widget._bpm_spin.value() == 100.0
    widget._sync_from_grid()
    assert widget._bpm_spin.value() == 100.0
    assert not state.can_undo

    widget._commit_bpm()
    assert state.committed.timing.tempo_events[0].bpm == 100.0
    # the edit is over: a resync owns the field again
    state.undo()
    widget.sync_from_document(state.doc)
    assert widget._bpm_spin.value() == 120.0


def test_typing_back_to_the_start_cancels_the_preview(qapp) -> None:
    state = AppState()
    widget = TransportStrip(state, FakePlayback(), FakeTapRecorder())

    widget._bpm_spin.setValue(100.0)
    assert state.doc is not state.committed       # a preview is live
    widget._bpm_spin.setValue(120.0)              # back where it started
    assert state.doc is state.committed           # preview dropped
    assert not state.axis._held                   # and the axis released
    widget._commit_bpm()
    assert not state.can_undo and not state.is_dirty


def test_undo_during_an_edit_takes_the_field_back(qapp) -> None:
    """An undo (or a project load) drops the preview from under the
    field. It must let go rather than sit on a number nothing shows."""
    state = AppState()
    widget = TransportStrip(state, FakePlayback(), FakeTapRecorder())
    widget._bpm_spin.setValue(100.0)
    widget._commit_bpm()

    widget._bpm_spin.setValue(90.0)               # typing again
    assert state.doc.timing.tempo_events[0].bpm == 90.0
    state.undo()                                  # pulls the rug out
    widget.sync_from_document(state.doc)
    assert widget._bpm_spin.value() == 120.0      # follows the document
    assert not widget._bpm_previewing()
