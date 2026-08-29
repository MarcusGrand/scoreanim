"""TransportStrip / LowerZone (M1.3), offscreen: the controller wiring
that moved out of the window — time feedback, play-text flip — behaves
exactly as the alpha window did, plus the Systems toggle C2 brought
over from the inspector and D1's transport cluster. The seek bar is
gone (D1 revision); seeking by key is tests/test_seek_keys.py, and
seeking by mouse is the lanes' own tests.

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
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDockWidget,  # noqa: E402
                               QSlider, QToolButton)

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
    """The strip over a real AppState, for the Systems toggle — the one
    control here that is a document command."""
    state = AppState()
    playback = FakePlayback()
    return TransportStrip(state, playback), state, playback


def test_play_action_drives_controller(strip) -> None:
    widget, playback = strip
    widget.play_action.trigger()
    assert playback.toggles == 1


def test_time_feedback_updates_the_timecode(strip) -> None:
    widget, playback = strip
    playback.time_changed.emit(65.4, 120.0)
    assert widget._time_label.text() == " 1:05.4 / 2:00.0 "


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


def test_the_strip_reads_left_to_right_as_a_cluster(strip) -> None:
    """D1: go to start, play, the timecode, then what the stage shows —
    and C4's lane gear last of all, at the right edge, with nothing but
    space between."""
    widget, _ = strip
    row = widget.layout()
    order = [row.itemAt(i).widget() for i in range(row.count())]
    buttons = [w for w in order if isinstance(w, QToolButton)]
    assert [b.defaultAction() for b in buttons] \
        == [widget.to_start_action, widget.play_action,
            widget.systems_action, None]
    assert buttons[-1] is widget.lane_options
    assert order.index(widget._time_label) < order.index(buttons[2])
    assert order.index(buttons[2]) < order.index(widget.lane_options)
    assert widget.systems_action.isCheckable()
    assert not widget.systems_action.icon().isNull()
    assert widget.systems_action.toolTip() != widget.systems_action.text()


def test_the_seek_bar_is_gone(strip) -> None:
    """D1 revision: the lanes are the seek surface. Two playheads
    moving at different speeds read as two clocks disagreeing."""
    widget, _ = strip
    assert widget.findChild(QSlider) is None
    # and the spare width is plain space, not a control
    row = widget.layout()
    stretches = [row.stretch(i) for i in range(row.count())
                 if row.itemAt(i).widget() is not None]
    assert set(stretches) == {0}


def test_go_to_start_seeks_to_zero_and_nothing_else(strip) -> None:
    """It rewinds; it does not start or stop anything — playing stays
    playing and paused stays paused."""
    widget, playback = strip
    playback.time_changed.emit(42.0, 120.0)
    widget.to_start_action.trigger()
    assert playback.seeks == [0.0]
    assert playback.toggles == 0
    assert not widget.to_start_action.icon().isNull()
    # E2: the sentence is written by hand, the key is read off the
    # action — an icon-only button has nothing else to go on
    assert widget.to_start_action.shortcut() == QKeySequence(Qt.Key.Key_Home)
    tip = widget.to_start_action.toolTip()
    assert tip.startswith("Move the playhead back to the start")
    assert QKeySequence(Qt.Key.Key_Home).toString(
        QKeySequence.SequenceFormat.NativeText) in tip


def test_the_timecode_is_monospace_and_cannot_shrink(strip) -> None:
    """D1: a running clock must not shuffle the cluster beside it."""
    widget, playback = strip
    label = widget._time_label
    assert label.fontMetrics().horizontalAdvance("0") \
        == label.fontMetrics().horizontalAdvance("1")
    floor = label.minimumWidth()
    assert floor > 0
    playback.time_changed.emit(1.0, 2.0)         # the shortest text there is
    assert label.minimumWidth() == floor


def test_the_lane_gear_is_the_only_view_state_on_the_strip(strip) -> None:
    """C4: the lane's view options are a menu on the lanes' own header,
    and opening one never touches the document."""
    widget, _ = strip
    gear = widget.lane_options
    assert gear.menu() is gear.menu_widget
    assert not gear.icon().isNull()
    assert gear.menu_widget.actions()          # lane, grid, flatten


def test_there_is_no_follow_toggle(strip) -> None:
    """Ruling 2026-08-29: playing music always shows the music, so
    there is nothing to switch off."""
    widget, _ = strip
    assert not hasattr(widget, "follow_action")


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
