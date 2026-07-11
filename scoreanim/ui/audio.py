"""Audio transport + the live AudioClock (tier 2b per the Phase 3 spike).

The audio playhead is the master clock (CLAUDE.md rule 3); core only
ever sees the Clock interface. Transport commands (load/play/pause/seek)
live here on the Qt wrapper, never on Clock — core reads time, nothing
else.

Why the clock extrapolates, and why that does not violate rule 2 ("time
is never accumulated"): the spike (spikes/audio_playhead.py, findings in
spikes/NOTES.md Phase 3) measured that QMediaPlayer.position() updates
only every 100 ms (wav) / 50 ms (mp3) on the Qt ffmpeg backend — a raw
read is a staircase with errors up to ~120 ms. But audio and wall clocks
run at the same rate to ~4e-5, so the clock reports

    now = perf_counter() + mean(position_i - perf_counter_i)

over the last ~12 positionChanged anchors (~1.2 s), clamped monotone.
There is no ``t += dt`` and no unbounded accumulation: the estimate is a
pure function of (recent authoritative audio positions, wall time).
Every positionChanged refreshes the window, so error is bounded by the
anchor cadence (measured: p95 7 ms wav / 1 ms mp3) and cannot grow over
a minutes-long piece; if audio stalls, anchors stall and the clock
stalls with it. Extrapolation freezes while paused. Seeks immediately
re-anchor to the target (measured settle < 1 ms), which is what makes
scrubbing feel instant; the monotone clamp resets with each seek so
backward seeks take effect at once.
"""
from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from statistics import fmean

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from scoreanim.core.timing import Clock

_ANCHOR_WINDOW = 12                    # ~1.2 s at the coarsest (wav) cadence


class AudioClock(Clock):
    """Sliding-mean anchored extrapolation over the backend's playhead.

    Fed by AudioTransport; consumers only ever call now_seconds().
    """

    def __init__(self) -> None:
        self._offsets: deque[float] = deque(maxlen=_ANCHOR_WINDOW)
        self._frozen = 0.0             # authoritative position while paused
        self._playing = False
        self._floor = 0.0              # monotone floor, reset on seek

    def now_seconds(self) -> float:
        if self._playing and self._offsets:
            estimate = time.perf_counter() + fmean(self._offsets)
            estimate = max(estimate, self._floor)
        else:
            estimate = self._frozen
        self._floor = max(self._floor, estimate)
        return estimate

    # -- fed by AudioTransport ------------------------------------------------

    def _anchor(self, position_s: float) -> None:
        self._offsets.append(position_s - time.perf_counter())

    def _set_playing(self, playing: bool) -> None:
        if playing and not self._playing:
            self._offsets.clear()      # resume jumps ~20-60 ms; re-sync fresh
        if not playing and self._playing:
            self._frozen = self.now_seconds()
        self._playing = playing

    def _jump_to(self, position_s: float) -> None:
        """Seek/load: the target is authoritative right now. It also
        seeds the anchor window (measured seek settle < 1 ms), so a seek
        during playback extrapolates immediately instead of stalling
        until the next positionChanged."""
        self._offsets.clear()
        self._offsets.append(position_s - time.perf_counter())
        self._frozen = position_s
        self._floor = position_s


class AudioTransport(QObject):
    """Owns QMediaPlayer + QAudioOutput; exposes transport commands and
    the Clock. mm:ss display and slider state read duration/position
    through this wrapper only."""

    playing_changed = Signal(bool)
    duration_changed = Signal(float)   # seconds; 0.0 until media is loaded

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._clock = AudioClock()
        self._player.positionChanged.connect(self._on_position)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.durationChanged.connect(
            lambda ms: self.duration_changed.emit(ms / 1000.0))

    @property
    def clock(self) -> Clock:
        return self._clock

    @property
    def is_playing(self) -> bool:
        return (self._player.playbackState()
                == QMediaPlayer.PlaybackState.PlayingState)

    def has_media(self) -> bool:
        return not self._player.source().isEmpty()

    def duration_seconds(self) -> float:
        return self._player.duration() / 1000.0

    def load(self, path: Path) -> None:
        self._player.stop()
        self._clock._jump_to(0.0)
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle(self) -> None:
        self.pause() if self.is_playing else self.play()

    def seek(self, seconds: float) -> None:
        seconds = max(0.0, min(seconds, self.duration_seconds()))
        self._clock._jump_to(seconds)
        self._player.setPosition(int(round(seconds * 1000)))

    # -- backend signals -------------------------------------------------------

    def _on_position(self, ms: int) -> None:
        if self.is_playing:
            self._clock._anchor(ms / 1000.0)

    def _on_state(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._clock._set_playing(playing)
        self.playing_changed.emit(playing)
