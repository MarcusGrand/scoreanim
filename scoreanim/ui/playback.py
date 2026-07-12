"""Playback wiring: tick → clock → applier → scene (PHASES 3.4).

The tick loop only ever READS the AudioClock (rule 3: the audio playhead
is master; the animation never steers audio) and hands the resulting t
to the applier — state stays a pure function of t. The QTimer runs only
while audio plays; seeks and tempo reloads do a one-shot full refresh,
so seek-while-paused updates the stage immediately and scrubbing is
stateless.

Per-tick cost is O(log n + items crossed this tick); the controller
accumulates per-tick wall times and reports mean/p95/max plus average
changed-items to the status bar every ~5 s and on pause, which is how
"frame cost stays flat on the densest page" is verified.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing import SwingRegion, TempoMap
from scoreanim.render.animate import AnimationApplier
from scoreanim.ui.audio import AudioTransport

_TICK_MS = 16
_STATS_EVERY_S = 5.0


class PlaybackController(QObject):
    page_changed = Signal(int)
    system_changed = Signal(int)             # Phase 7.4; window routes by mode
    status_message = Signal(str)
    time_changed = Signal(float, float)      # audio seconds, duration seconds

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.transport = AudioTransport(self)
        self._applier: AnimationApplier | None = None
        self._measures: Sequence[MeasureInfo] = ()
        self._offset_seconds = 0.0
        self._follow = True
        self._last_page = 1
        self._last_system = 1

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self.transport.playing_changed.connect(self._on_playing)
        self.transport.duration_changed.connect(
            lambda d: self.time_changed.emit(
                self.transport.clock.now_seconds(), d))

        self._tick_ms: list[float] = []
        self._changed: list[int] = []
        self._stats_wall = 0.0

    # -- configuration ---------------------------------------------------------

    def set_animation(self, applier: AnimationApplier,
                      measures: Sequence[MeasureInfo]) -> None:
        self._applier = applier
        self._measures = measures
        self._refresh()

    def set_timing_config(self, offset_seconds: float, tempo_map: TempoMap,
                          swing: Sequence[SwingRegion] = ()) -> None:
        """Retime the animation from the document's timing intent (called
        on every document change — edits, previews, undo). The offset is
        the audio time of beat 0 (never TempoMap's business)."""
        self._offset_seconds = offset_seconds
        if self._applier is not None:
            self._applier.set_timing(tempo_map, swing)
        self._refresh()

    def set_follow(self, follow: bool) -> None:
        self._follow = follow

    def set_style(self, style) -> None:
        """Forward the document's StyleRules (per-element effects +
        reveal mode) to the applier; the applier no-ops on unchanged
        rules."""
        if self._applier is not None:
            self._applier.set_style(style)

    # -- transport surface used by the window ----------------------------------

    def open_audio(self, path: Path) -> None:
        self.transport.load(path)
        self._refresh()
        self.status_message.emit(f"audio: {path.name}")

    def toggle_play(self) -> None:
        if self.transport.has_media():
            self.transport.toggle()

    def seek(self, audio_seconds: float) -> None:
        self.transport.seek(audio_seconds)
        self._refresh()

    # -- internals ---------------------------------------------------------------

    def _score_time(self, audio_seconds: float) -> float:
        return audio_seconds - self._offset_seconds

    def _refresh(self) -> None:
        t_audio = self.transport.clock.now_seconds()
        if self._applier is not None:
            self._applier.refresh(self._score_time(t_audio))
            self._follow_position()
        self.time_changed.emit(t_audio, self.transport.duration_seconds())

    def _follow_position(self) -> None:
        """Emit page/system changes off the applier's cursor. The
        controller stays document-agnostic: it reports both; the window
        routes by the document's presentation mode."""
        assert self._applier is not None
        page = self._applier.current_page()
        if page != self._last_page:
            self._last_page = page
            if self._follow:
                self.page_changed.emit(page)
        system = self._applier.current_system()
        if system != self._last_system:
            self._last_system = system
            if self._follow:
                self.system_changed.emit(system)

    def _on_playing(self, playing: bool) -> None:
        if playing:
            self._tick_ms.clear()
            self._changed.clear()
            self._stats_wall = time.perf_counter()
            self._timer.start()
        else:
            self._timer.stop()
            self._tick()                       # settle the final state
            self._emit_stats()

    def _tick(self) -> None:
        t0 = time.perf_counter()
        t_audio = self.transport.clock.now_seconds()
        changed = 0
        if self._applier is not None:
            changed = self._applier.apply_at(self._score_time(t_audio))
            self._follow_position()
        self.time_changed.emit(t_audio, self.transport.duration_seconds())
        self._tick_ms.append((time.perf_counter() - t0) * 1000.0)
        self._changed.append(changed)
        if t0 - self._stats_wall >= _STATS_EVERY_S:
            self._emit_stats()
            self._stats_wall = t0

    def _emit_stats(self) -> None:
        if not self._tick_ms:
            return
        ordered = sorted(self._tick_ms)
        p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
        self.status_message.emit(
            f"tick mean {sum(ordered) / len(ordered):.2f} ms · "
            f"p95 {p95:.2f} · max {ordered[-1]:.2f} · "
            f"avg changed {sum(self._changed) / len(self._changed):.1f}/tick "
            f"· {len(ordered)} ticks")
