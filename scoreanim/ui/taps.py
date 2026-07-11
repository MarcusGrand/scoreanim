"""TapRecorder: the key-event side of tap capture (PHASES 4.3).

Only the key event lives here — all tap→tempo math is core
(core/timing/taps.py). Timestamps come from the AudioClock
(``transport.clock.now_seconds()``, tier 2b — never the raw coarse
``position()``). Beat assignment per ruling 2026-07-11: the first tap
snaps to the nearest beat under the current map (echoed immediately in
the status bar so a mis-snap is obvious); every later tap is
``first + n · unit``.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from scoreanim.core.timing import TempoMap
from scoreanim.core.timing.taps import MIN_TAPS, Tap, TapSession
from scoreanim.ui.app_state import AppState
from scoreanim.ui.audio import AudioTransport


class TapRecorder(QObject):
    status = Signal(str)
    session_finished = Signal(object)    # TapSession

    def __init__(self, app_state: AppState, transport: AudioTransport,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._transport = transport
        self._armed = False
        self._unit = 1.0
        self._taps: list[Tap] = []

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def has_taps(self) -> bool:
        return bool(self._taps)

    def set_armed(self, armed: bool, unit: float = 1.0) -> None:
        if armed and not self._armed:
            self._armed = True
            self._unit = unit
            self._taps = []
            self.status.emit("taps armed — play and tap T on the beats")
        elif not armed and self._armed:
            self.finish()

    def tap(self) -> None:
        if not self._armed:
            return
        if not self._transport.is_playing:
            self.status.emit("tap ignored — transport not playing")
            return
        now = self._transport.clock.now_seconds()
        if self._taps and now <= self._taps[-1].seconds:
            self.status.emit("tap ignored — clock has not advanced")
            return
        if not self._taps:
            beat = self._anchor_beat(now)
            self._taps.append(Tap(beat, now))
            self.status.emit(f"tap 1 → {self._describe_beat(beat)}")
        else:
            beat = self._taps[0].beat + len(self._taps) * self._unit
            self._taps.append(Tap(beat, now))
            self.status.emit(
                f"tap {len(self._taps)} → {self._describe_beat(beat)}")

    def finish(self) -> None:
        """End the session (disarm, pause, or toggle-off). Emits the
        session when it has enough taps to derive from."""
        taps, self._taps = self._taps, []
        self._armed = False
        if len(taps) >= MIN_TAPS:
            self.session_finished.emit(TapSession(self._unit, tuple(taps)))
        elif taps:
            self.status.emit(
                f"tap session discarded ({len(taps)} taps < {MIN_TAPS})")

    # -- helpers -----------------------------------------------------------------

    def _anchor_beat(self, audio_seconds: float) -> float:
        """Nearest beat under the current map (ruling 2026-07-11): the
        user seeks near the passage first, so the map is locally right
        even when globally drifting."""
        timing = self._state.doc.timing
        tempo_map = TempoMap(list(timing.tempo_events))
        score_seconds = max(0.0, audio_seconds - timing.offset_seconds)
        return max(0.0, round(tempo_map.beats_at(score_seconds)))

    def _describe_beat(self, beat: float) -> str:
        for m in self._state.measures:
            if m.start <= beat < m.start + m.quarter_length:
                return f"m{m.number} beat {beat - m.start + 1:g}"
        return f"beat {beat:g}"
