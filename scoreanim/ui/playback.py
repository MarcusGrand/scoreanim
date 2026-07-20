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
from scoreanim.core.timing.swing import resolve_seconds
from scoreanim.render.animate import AnimationApplier
from scoreanim.ui.audio import AudioTransport
from scoreanim.ui.wall_clock import WallClock

_TICK_MS = 16
_STATS_EVERY_S = 5.0


class PlaybackController(QObject):
    page_changed = Signal(int)
    system_changed = Signal(int)             # Phase 7.4; window routes by mode
    status_message = Signal(str)
    time_changed = Signal(float, float)      # audio seconds, duration seconds
    # The controller is the single bridge to the transport (docstring), so
    # the window reads play-state and duration from HERE, not the audio
    # wrapper — that keeps the no-audio path (WallClock) identical to the
    # audio path from the window's side (FIX 2).
    playing_changed = Signal(bool)
    duration_changed = Signal(float)         # seconds; audio OR score length

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.transport = AudioTransport(self)
        # No-audio playback (FIX 2): when no recording is loaded the tick
        # reads this wall-anchored clock instead. The AudioClock stays
        # master whenever audio IS loaded (rule 3).
        self._wall = WallClock()
        self._applier: AnimationApplier | None = None
        self._measures: Sequence[MeasureInfo] = ()
        self._tempo_map: TempoMap | None = None
        self._swing: Sequence[SwingRegion] = ()
        self._offset_seconds = 0.0
        self._follow = True
        self._last_page = 1
        self._last_system = 1

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self.transport.playing_changed.connect(self._set_playing)
        self.transport.duration_changed.connect(self._on_audio_duration)

        self._tick_ms: list[float] = []
        self._changed: list[int] = []
        self._stats_wall = 0.0

    # -- active clock + duration (audio OR no-audio) ---------------------------

    @property
    def _clock(self):
        """The master clock: the audio playhead when a recording is
        loaded (rule 3), else the wall clock (FIX 2)."""
        return self.transport.clock if self.transport.has_media() \
            else self._wall

    def _duration(self) -> float:
        if self.transport.has_media():
            return self.transport.duration_seconds()
        return self._score_duration()

    def _score_duration(self) -> float:
        """Score length in seconds through the same swing-aware
        resolve_seconds seam as triggers (offset is 0 with no audio)."""
        if self._tempo_map is None or not self._measures:
            return 0.0
        end_beats = max((m.start + m.quarter_length for m in self._measures),
                        default=0.0)
        return resolve_seconds([end_beats], self._tempo_map, self._swing)[0]

    def _on_audio_duration(self, d: float) -> None:
        self.duration_changed.emit(d)
        self.time_changed.emit(self._clock.now_seconds(), d)

    # -- configuration ---------------------------------------------------------

    def set_animation(self, applier: AnimationApplier,
                      measures: Sequence[MeasureInfo]) -> None:
        self._applier = applier
        self._measures = measures
        self._emit_duration_if_no_audio()
        self._refresh()

    def set_timing_config(self, offset_seconds: float, tempo_map: TempoMap,
                          swing: Sequence[SwingRegion] = ()) -> None:
        """Retime the animation from the document's timing intent (called
        on every document change — edits, previews, undo). The offset is
        the audio time of beat 0 (never TempoMap's business). The tempo
        map + measures also give the no-audio timeline its length."""
        self._offset_seconds = offset_seconds
        self._tempo_map = tempo_map
        self._swing = swing
        if self._applier is not None:
            self._applier.set_timing(tempo_map, swing)
        self._emit_duration_if_no_audio()
        self._refresh()

    def _emit_duration_if_no_audio(self) -> None:
        # with a recording, the audio backend owns duration; without one,
        # the score's own length drives the slider and the axis (FIX 2)
        if not self.transport.has_media():
            self.duration_changed.emit(self._score_duration())

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
        if self._wall.is_playing:            # stop no-audio playback first
            self._wall.pause()
            self._set_playing(False)
        self.transport.load(path)
        self._refresh()
        self.status_message.emit(f"audio: {path.name}")

    def pause(self) -> None:
        """Pause whichever clock is playing (audio or no-audio). Used
        before modal dialogs so no tick runs underneath them."""
        if self.transport.has_media():
            self.transport.pause()
        elif self._wall.is_playing:
            self._wall.pause()
            self._set_playing(False)

    def toggle_play(self) -> None:
        if self.transport.has_media():
            self.transport.toggle()          # audio: state flows back via signal
            return
        # no-audio playback (FIX 2): drive the wall clock + timer directly
        if self._applier is None or self._score_duration() <= 0.0:
            return                           # nothing to play
        if self._wall.is_playing:
            self._wall.pause()
            self._set_playing(False)
        else:
            if self._clock.now_seconds() >= self._score_duration():
                self._wall.seek(0.0)         # replay from the top at the end
            self._wall.play()
            self._set_playing(True)

    def seek(self, audio_seconds: float) -> None:
        if self.transport.has_media():
            self.transport.seek(audio_seconds)
        else:
            self._wall.seek(audio_seconds)
        self._refresh()

    # -- internals ---------------------------------------------------------------

    def _score_time(self, audio_seconds: float) -> float:
        return audio_seconds - self._offset_seconds

    def _refresh(self) -> None:
        t_audio = self._clock.now_seconds()
        if self._applier is not None:
            self._applier.refresh(self._score_time(t_audio))
            self._follow_position()
        self.time_changed.emit(t_audio, self._duration())

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

    def _set_playing(self, playing: bool) -> None:
        """Start/stop the tick loop and report the state. Driven by the
        audio transport's playing_changed (audio) OR directly by
        toggle_play (no-audio) — one path, so the window sees a single
        playing signal regardless of the clock source."""
        if playing:
            self._tick_ms.clear()
            self._changed.clear()
            self._stats_wall = time.perf_counter()
            self._timer.start()
        else:
            self._timer.stop()
            self._tick()                       # settle the final state
            self._emit_stats()
        self.playing_changed.emit(playing)

    def _tick(self) -> None:
        t0 = time.perf_counter()
        t_audio = self._clock.now_seconds()
        # no-audio playback stops itself at the end of the score (audio
        # stops via the backend's end-of-media); do it before applying so
        # the final frame settles exactly on the last onset
        if (self._wall.is_playing and not self.transport.has_media()
                and t_audio >= self._score_duration() > 0.0):
            self._wall.pause()
            self._set_playing(False)
            return
        changed = 0
        if self._applier is not None:
            changed = self._applier.apply_at(self._score_time(t_audio))
            self._follow_position()
        self.time_changed.emit(t_audio, self._duration())
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
