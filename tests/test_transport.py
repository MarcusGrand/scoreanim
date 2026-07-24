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
