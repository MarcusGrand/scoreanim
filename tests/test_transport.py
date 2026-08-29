"""TransportStrip / LowerZone (M1.3), offscreen: the controller wiring
that moved out of the window — slider seeks, time feedback, play-text
flip — behaves exactly as the alpha window did, plus the two stage
toggles C2 brought over from the inspector.

The strip is exercised against a fake controller QObject (real signals,
recorded calls); the zone against a real AppState (its lanes observe
only that). The time fields moved to ui/timeline_bar.py and are tested
in tests/test_timeline_bar.py.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDockWidget,  # noqa: E402
                               QToolButton)

from scoreanim.core.project import PresentationMode  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.transport import LowerZone, TransportStrip  # noqa: E402


class FakePlayback(QObject):
    time_changed = Signal(float, float)
    playing_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.seeks: list[float] = []
        self.toggles = 0
        self.follow_calls: list[bool] = []

    def set_follow(self, follow: bool) -> None:
        self.follow_calls.append(follow)

    def toggle_play(self) -> None:
        self.toggles += 1

    def seek(self, seconds: float) -> None:
        self.seeks.append(seconds)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def strip(qapp):
    state = AppState()
    playback = FakePlayback()
    return TransportStrip(state, playback), playback


@pytest.fixture
def toggles(qapp):
    """The strip over a real AppState, for the two stage toggles: one
    is transient controller state, the other is a document command."""
    state = AppState()
    playback = FakePlayback()
    return TransportStrip(state, playback), state, playback


def test_play_action_drives_controller(strip) -> None:
    widget, playback = strip
    widget.play_action.trigger()
    assert playback.toggles == 1


def test_time_feedback_updates_label_and_slider(strip) -> None:
    widget, playback = strip
    playback.time_changed.emit(65.4, 120.0)
    assert widget._time_label.text() == " 1:05.4 / 2:00.0 "
    assert widget._slider.maximum() == 120000
    assert widget._slider.value() == 65400


def test_slider_untouched_while_user_drags(strip) -> None:
    widget, playback = strip
    playback.time_changed.emit(10.0, 120.0)
    widget._slider.setSliderDown(True)
    playback.time_changed.emit(50.0, 120.0)
    assert widget._slider.value() == 10000       # no fight with the drag
    assert widget._time_label.text().startswith(" 0:50.0")


def test_drag_and_keyboard_step_seek(strip) -> None:
    widget, playback = strip
    widget._slider.setRange(0, 120000)
    widget._slider.setSliderDown(True)
    widget._slider.sliderMoved.emit(2500)        # drag → seek
    widget._slider.setSliderDown(False)
    widget._slider.setValue(4000)                # keyboard/page step → seek
    assert playback.seeks == [2.5, 4.0]


def test_playing_flips_the_play_text_and_icon(strip) -> None:
    widget, playback = strip
    play_icon = widget.play_action.icon().cacheKey()
    playback.playing_changed.emit(True)
    assert widget.play_action.text() == "Pause"
    assert widget.play_action.icon().cacheKey() != play_icon
    playback.playing_changed.emit(False)
    assert widget.play_action.text() == "Play"
    assert widget.play_action.icon().cacheKey() == play_icon


def test_the_play_button_is_an_icon_with_a_tooltip(strip) -> None:
    """No "▶ Play" text on the strip any more (A2): the button is the
    icon, and the tooltip names both halves of the toggle and its key."""
    widget, _ = strip
    assert not widget.play_action.icon().isNull()
    assert widget.play_action.toolTip() == "Play / Pause (Space)"
    button = widget.findChild(QToolButton)
    assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly


def test_the_toggles_sit_after_the_time_readout(strip) -> None:
    """C2: play, the slider, the readout, then what the stage shows."""
    widget, _ = strip
    row = widget.layout()
    order = [row.itemAt(i).widget() for i in range(row.count())]
    buttons = [w for w in order if isinstance(w, QToolButton)]
    assert [b.defaultAction() for b in buttons] \
        == [widget.play_action, widget.follow_action, widget.systems_action]
    assert order.index(widget._time_label) < order.index(buttons[1])
    for action in (widget.follow_action, widget.systems_action):
        assert action.isCheckable()
        assert not action.icon().isNull()
        assert action.toolTip() and action.toolTip() != action.text()


def test_follow_is_transient_state_not_a_command(toggles) -> None:
    """The SAME QAction the Playback menu adds, so the two cannot
    diverge — and nothing about it reaches the document."""
    widget, state, playback = toggles
    assert widget.follow_action.isChecked()      # on by default
    widget.follow_action.setChecked(False)
    widget.follow_action.setChecked(True)
    assert playback.follow_calls == [False, True]
    assert not state.can_undo


def test_follow_never_resynced_from_the_document(toggles) -> None:
    widget, state, _ = toggles
    widget.follow_action.setChecked(False)
    widget.sync_from_document(state.doc)
    assert not widget.follow_action.isChecked()  # transient state survives
    assert not state.can_undo                    # and no command ever ran


def test_systems_is_one_undoable_command(toggles) -> None:
    widget, state, _ = toggles
    assert not widget.systems_action.isChecked()
    widget.systems_action.setChecked(True)
    assert state.doc.stage.mode is PresentationMode.SYSTEM
    state.undo()
    assert state.doc.stage.mode is PresentationMode.PAGED


def test_systems_resyncs_without_reexecuting(toggles) -> None:
    """Undo, redo and project load all arrive through the window's
    resync; a resync pushes the mode onto the button and stops there."""
    widget, state, _ = toggles
    widget.systems_action.setChecked(True)
    state.undo()                                 # button is now stale
    widget.sync_from_document(state.doc)
    assert not widget.systems_action.isChecked()
    assert state.can_redo                        # the resync ran no command
    state.redo()
    widget.sync_from_document(state.doc)
    assert widget.systems_action.isChecked()
    assert not state.can_redo


def test_lower_zone_is_a_fixed_bottom_dock(qapp) -> None:
    zone = LowerZone(AppState(), FakePlayback())
    assert zone.objectName() == "LowerZone"      # saveState identity (M1.8)
    assert zone.features() \
        == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
    assert zone.allowedAreas() == Qt.DockWidgetArea.BottomDockWidgetArea
    # strip on top, lanes on the internal splitter, timeline bar under
    # the lanes it drives
    assert zone.strip is not None and zone.bar is not None
    assert zone.waveform.parent() is zone.tempo_lane.parent()  # the splitter
    body = zone.widget().layout()
    assert body.indexOf(zone.strip) < body.indexOf(zone.bar)
    assert body.indexOf(zone.bar) == body.count() - 1
