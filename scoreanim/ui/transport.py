"""Lower zone: transport strip above the waveform + tempo lanes (M1.3).

The timeline area formalized as a bottom QDockWidget (ruling
2026-07-24) — the stage keeps the central widget to itself, and one
`saveState` pair will persist this dock with the inspector (M1.8). The
two lanes share the time axis on purpose (tapping while watching the
waveform) and stay stacked, never tabbed; an internal splitter keeps
their heights user-adjustable, replacing the old three-way central
splitter (stage-vs-zone sizing moves to the dock boundary).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QSlider,
                               QSplitter, QToolButton, QVBoxLayout, QWidget)

from scoreanim.ui.app_state import AppState
from scoreanim.ui.playback import PlaybackController
from scoreanim.ui.readouts import format_time
from scoreanim.ui.taps import TapRecorder
from scoreanim.ui.tempo_lane import TempoLaneView
from scoreanim.ui.waveform import WaveformView


class TransportStrip(QWidget):
    """Play, seek slider, time readout, tap controls.

    Owns the play/arm/tap QActions — the window registers them
    window-level so Space / Shift+T / T fire regardless of focus, and
    the Playback menu shares the same play action so the two checked/
    text states cannot diverge. Observes the playback controller for
    time and play-state; pausing ends an armed tap session (the alpha
    `_on_playing` behavior, moved here with the widgets).
    """

    def __init__(self, playback: PlaybackController,
                 tap_recorder: TapRecorder,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._playback = playback
        self._tap_recorder = tap_recorder

        self.play_action = QAction("▶ Play", self)
        self.play_action.setShortcut(Qt.Key.Key_Space)
        self.play_action.triggered.connect(playback.toggle_play)

        self.arm_taps_action = QAction("● Arm Taps", self)
        self.arm_taps_action.setCheckable(True)
        self.arm_taps_action.setShortcut("Shift+T")
        self.arm_taps_action.toggled.connect(tap_recorder.set_armed)

        # visible for the first time (brief flag 5) — the shortcut is
        # unchanged; a visibility change, not a new capability
        self.tap_action = QAction("Tap", self)
        self.tap_action.setShortcut("T")
        self.tap_action.setAutoRepeat(False)
        self.tap_action.triggered.connect(tap_recorder.tap)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setSingleStep(100)        # ms
        self._slider.setPageStep(2000)
        self._slider.sliderMoved.connect(
            lambda ms: playback.seek(ms / 1000.0))
        self._slider.valueChanged.connect(self._on_slider_value)
        self._time_label = QLabel(" 0:00.0 / 0:00.0 ")

        row = QHBoxLayout(self)
        row.setContentsMargins(4, 2, 4, 2)
        row.addWidget(_action_button(self.play_action))
        row.addWidget(self._slider, 1)
        row.addWidget(self._time_label)
        row.addWidget(_action_button(self.arm_taps_action))
        row.addWidget(_action_button(self.tap_action))

        playback.time_changed.connect(self._on_time)
        playback.playing_changed.connect(self._on_playing)

    # -- playback feedback -----------------------------------------------------

    def _on_time(self, audio_seconds: float, duration: float) -> None:
        self._time_label.setText(
            f" {format_time(audio_seconds)} / {format_time(duration)} ")
        if not self._slider.isSliderDown():
            self._slider.blockSignals(True)
            self._slider.setRange(0, int(duration * 1000))
            self._slider.setValue(int(audio_seconds * 1000))
            self._slider.blockSignals(False)

    def _on_slider_value(self, ms: int) -> None:
        # keyboard/page-step changes (sliderMoved covers drags)
        if not self._slider.isSliderDown():
            self._playback.seek(ms / 1000.0)

    def _on_playing(self, playing: bool) -> None:
        self.play_action.setText("⏸ Pause" if playing else "▶ Play")
        if not playing and self._tap_recorder.armed:
            self.arm_taps_action.setChecked(False)   # pause ends the session


class LowerZone(QDockWidget):
    """Bottom dock: the transport strip over the two timeline lanes.

    A fixed-feeling zone (ruling 2026-07-24): no close/float/move
    titlebar chrome — its show/hide surface is the dock's
    `toggleViewAction()`, which the View menu picks up in M1.5. The
    lanes observe AppState only, exactly as before; they are
    re-parented here, not modified.
    """

    def __init__(self, app_state: AppState, playback: PlaybackController,
                 tap_recorder: TapRecorder,
                 parent: QWidget | None = None) -> None:
        super().__init__("Timeline", parent)
        self.setObjectName("LowerZone")      # saveState identity (M1.8)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.setTitleBarWidget(QWidget(self))    # no titlebar chrome at all
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.toggleViewAction().setText("Lower Zone")

        self.strip = TransportStrip(playback, tap_recorder, self)
        self.waveform = WaveformView(app_state)
        self.tempo_lane = TempoLaneView(app_state)
        lanes = QSplitter(Qt.Orientation.Vertical, self)
        lanes.addWidget(self.waveform)
        lanes.addWidget(self.tempo_lane)

        body = QWidget(self)
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.strip)
        column.addWidget(lanes, 1)
        self.setWidget(body)


def _action_button(action: QAction) -> QToolButton:
    """Toolbar-style button for a strip action: mirrors text/checked
    state, takes no focus (shortcuts stay window-level; the stage keeps
    keyboard focus)."""
    button = QToolButton()
    button.setDefaultAction(action)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return button
