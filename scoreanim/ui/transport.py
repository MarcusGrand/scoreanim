"""Lower zone: transport strip above the waveform + tempo lanes (M1.3).

The timeline area formalized as a bottom QDockWidget (ruling
2026-07-24) — the stage keeps the central widget to itself, and one
`saveState` pair will persist this dock with the inspector (M1.8). The
two lanes share the time axis on purpose (tapping while watching the
waveform) and stay stacked, never tabbed; an internal splitter keeps
their heights user-adjustable, replacing the old three-way central
splitter (stage-vs-zone sizing moves to the dock boundary).

Ruling (Marcus, 2026-07-24): everything time-related — Tempo, Offset,
Swing — lives HERE, on the strip with the transport it configures, not
in the inspector. The M1.4 inspector keeps the non-time controls
(Follow/Systems, appearance).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QDockWidget, QDoubleSpinBox, QHBoxLayout,
                               QLabel, QSlider, QSplitter, QToolButton,
                               QVBoxLayout, QWidget)

from scoreanim.core.project import (DEFAULT_BPM, MoveTempoEvent, ProjectDoc,
                                    SetGlobalSwing, SetOffset)
from scoreanim.ui.app_state import AppState
from scoreanim.ui.playback import PlaybackController
from scoreanim.ui.readouts import (format_time, global_swing_ratio,
                                   initial_tempo_event)
from scoreanim.ui.taps import TapRecorder
from scoreanim.ui.tempo_lane import TempoLaneView
from scoreanim.ui.waveform import WaveformView


class TransportStrip(QWidget):
    """Play, seek slider, time readout, the time fields, tap controls.

    Owns the play/arm/tap QActions — the window registers them
    window-level so Space / Shift+T / T fire regardless of focus, and
    the Playback menu shares the same play action so the two checked/
    text states cannot diverge. Observes the playback controller for
    time and play-state; pausing ends an armed tap session (the alpha
    `_on_playing` behavior, moved here with the widgets).

    Tempo/Offset/Swing are labeled fields (the prefix-in-spinbox look
    is retired) with the alpha commit wiring verbatim: keyboard
    tracking off, commit on editingFinished, epsilon no-op guard, and
    a blockSignals resync via `sync_from_document` — the window calls
    it on every document change, so a resync never re-executes a
    command.
    """

    def __init__(self, app_state: AppState, playback: PlaybackController,
                 tap_recorder: TapRecorder,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
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

        # initial tempo (FIX 2): edits the beat-0 tempo event through the
        # existing tempo-map machinery (MoveTempoEvent) — not a parallel
        # path. With no audio it sets the no-audio playback pace; the
        # offset is simply 0 then.
        self._bpm_spin = QDoubleSpinBox()
        self._bpm_spin.setDecimals(1)
        self._bpm_spin.setSingleStep(1.0)
        self._bpm_spin.setRange(20.0, 400.0)
        self._bpm_spin.setKeyboardTracking(False)
        self._bpm_spin.setToolTip("Initial tempo (bpm) — drives no-audio "
                                  "playback and the tempo map")
        self._bpm_spin.editingFinished.connect(self._commit_bpm)

        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setSuffix(" s")      # a unit, not a label
        self._offset_spin.setDecimals(2)
        self._offset_spin.setSingleStep(0.05)
        self._offset_spin.setRange(-60.0, 3600.0)
        self._offset_spin.setKeyboardTracking(False)
        self._offset_spin.editingFinished.connect(self._commit_offset)

        # global swing ratio (ruling 2026-07-11): 0.50 straight … 0.67
        # triplet, one value for the whole piece; regions later (BACKLOG 7)
        self._swing_spin = QDoubleSpinBox()
        self._swing_spin.setDecimals(2)
        self._swing_spin.setSingleStep(0.01)
        self._swing_spin.setRange(0.50, 0.75)
        self._swing_spin.setKeyboardTracking(False)
        self._swing_spin.editingFinished.connect(self._commit_swing)

        row = QHBoxLayout(self)
        row.setContentsMargins(4, 2, 4, 2)
        row.addWidget(_action_button(self.play_action))
        row.addWidget(self._slider, 1)
        row.addWidget(self._time_label)
        for label, spin in (("Tempo", self._bpm_spin),
                            ("Offset", self._offset_spin),
                            ("Swing", self._swing_spin)):
            row.addWidget(QLabel(label))
            row.addWidget(spin)
        row.addWidget(_action_button(self.arm_taps_action))
        row.addWidget(_action_button(self.tap_action))

        playback.time_changed.connect(self._on_time)
        playback.playing_changed.connect(self._on_playing)

    # -- document sync ---------------------------------------------------------

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Resync the time fields from document intent (execute, undo,
        redo, and project load all arrive here via the window)."""
        self._offset_spin.blockSignals(True)
        self._offset_spin.setValue(doc.timing.offset_seconds)
        self._offset_spin.blockSignals(False)
        first_tempo = initial_tempo_event(doc)
        self._bpm_spin.blockSignals(True)
        self._bpm_spin.setValue(first_tempo.bpm if first_tempo
                                else DEFAULT_BPM)
        self._bpm_spin.blockSignals(False)
        self._swing_spin.blockSignals(True)
        self._swing_spin.setValue(global_swing_ratio(doc))
        self._swing_spin.blockSignals(False)

    # -- commit handlers -------------------------------------------------------

    def _commit_bpm(self) -> None:
        """Set the initial (beat-0) tempo through the existing tempo-map
        machinery — MoveTempoEvent on the first event, so a tempo curve's
        later events survive. Drives no-audio playback (FIX 2)."""
        first = initial_tempo_event(self._state.doc)
        value = self._bpm_spin.value()
        if first is None or abs(value - first.bpm) < 1e-9:
            return
        self._state.execute(
            MoveTempoEvent(first.position, first.position, value))

    def _commit_offset(self) -> None:
        value = self._offset_spin.value()
        if abs(value - self._state.doc.timing.offset_seconds) > 1e-9:
            self._state.execute(SetOffset(value))

    def _commit_swing(self) -> None:
        value = self._swing_spin.value()
        if abs(value - global_swing_ratio(self._state.doc)) < 1e-9:
            return
        measures = self._state.measures
        if not measures:
            return
        end_beat = measures[-1].start + measures[-1].quarter_length
        self._state.execute(SetGlobalSwing(value, end_beat))

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

        self.strip = TransportStrip(app_state, playback, tap_recorder, self)
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
