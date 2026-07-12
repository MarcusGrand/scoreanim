"""The Clock seam (CLAUDE.md rules 2/3).

Animation state is a pure function of t; t comes from a Clock injected
by the caller. ``AudioClock`` (the live implementation, wrapping the Qt
audio backend's playhead) lives in ui/audio.py — Qt must never be
imported here. ``FrameClock`` (t = n / fps) drives deterministic export
(Phase 6): the driver sets the frame index and reads the same
``now_seconds()`` surface playback reads.

The surface is ``now_seconds()`` only. ARCHITECTURE §5 sketched "plus
transport state", but no core consumer branches on transport: the UI
drives the tick and owns play/pause/seek on the Qt wrapper. Transport
state joins this ABC only when a core consumer actually needs it
(amendment ruled 2026-07-11, Phase 3 plan).
"""
from __future__ import annotations

import abc


class Clock(abc.ABC):
    @abc.abstractmethod
    def now_seconds(self) -> float:
        """Current time in seconds relative to transport start."""


class ManualClock(Clock):
    """Settable clock for headless tests and offline tools."""

    def __init__(self, t: float = 0.0) -> None:
        self._t = t

    def set(self, t: float) -> None:
        self._t = t

    def now_seconds(self) -> float:
        return self._t


class FrameClock(Clock):
    """Deterministic export clock: t = frame / fps.

    Every query is a fresh division from the absolute frame index —
    never ``t += 1/fps`` (rule 2) — so drift over any number of frames
    is impossible by construction, and setting frames out of order
    yields the same times as walking them in order."""

    def __init__(self, fps: float) -> None:
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        self._fps = float(fps)
        self._frame = 0

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def frame(self) -> int:
        return self._frame

    def set_frame(self, n: int) -> None:
        if n < 0:
            raise ValueError(f"frame index must be >= 0, got {n}")
        self._frame = n

    def now_seconds(self) -> float:
        return self._frame / self._fps
