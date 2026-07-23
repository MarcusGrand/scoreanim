"""WallClock: the live clock for no-audio playback (FIX 2, 2026-07-20).

When no recording is loaded, the score still plays: the transport reads
this wall-anchored clock instead of the AudioClock. Time is a PURE
FUNCTION of the wall clock since the last (re-)anchor —

    now = anchor_position + (perf_counter() - anchor_wall)

— never ``t += dt`` (CLAUDE.md rule 2). Play anchors to the current
wall time; pause freezes the extrapolated position; seek re-anchors to
the target. The AudioClock remains master whenever audio IS loaded
(rule 3); this clock only drives the audio-less case, where the audio
offset is simply 0 and the tempo map (default, sidecar, or taps) sets
the pace.

Qt-free on purpose (headless-testable): the wall source is injectable,
so tests drive it deterministically.
"""
from __future__ import annotations

import time
from typing import Callable

from scoreanim.core.timing import Clock


class WallClock(Clock):
    def __init__(self, now: Callable[[], float] = time.perf_counter) -> None:
        self._now = now
        self._playing = False
        self._position = 0.0       # frozen position; also the play anchor
        self._wall = 0.0           # wall time captured at the anchor

    def now_seconds(self) -> float:
        if self._playing:
            return self._position + (self._now() - self._wall)
        return self._position

    @property
    def is_playing(self) -> bool:
        return self._playing

    def play(self) -> None:
        if not self._playing:
            self._wall = self._now()      # anchor here; position unchanged
            self._playing = True

    def pause(self) -> None:
        if self._playing:
            self._position = self.now_seconds()   # freeze the extrapolation
            self._playing = False

    def seek(self, seconds: float) -> None:
        """Re-anchor to `seconds`; stays consistent whether playing or
        paused (the anchor pair is refreshed either way)."""
        self._position = max(0.0, seconds)
        self._wall = self._now()
