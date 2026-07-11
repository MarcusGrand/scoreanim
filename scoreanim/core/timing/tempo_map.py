"""Beats ⇄ seconds from piecewise-constant tempo events.

Piecewise-constant bpm makes the beats→seconds mapping piecewise linear
and strictly monotone (bpm > 0 enforced), hence exactly invertible.
Segment boundaries are precomputed at construction; lookups are
bisect + lerp both directions.

Conventions:
- ``seconds_at(0.0) == 0.0`` by construction. Audio lead-in ("beat 0 is
  at 1.8 s of the recording") is the transport's ``offset``, never
  TempoMap's business.
- Before the first event the first event's bpm extends back to beat 0
  (and below); after the last event the last bpm extends forever.
- Swing (Phase 4) is a beat-domain onset warp applied to trigger beats
  BEFORE calling ``seconds_at``; this class does not change for it.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Sequence

from scoreanim.core.score.identity import Beats


@dataclass(frozen=True)
class TempoEvent:
    position: Beats          # quarter notes from score start
    bpm: float


class TempoMap:
    def __init__(self, events: Sequence[TempoEvent]) -> None:
        if not events:
            raise ValueError("TempoMap requires at least one tempo event")
        ordered = sorted(events, key=lambda e: e.position)
        for ev in ordered:
            if ev.bpm <= 0:
                raise ValueError(f"bpm must be positive, got {ev.bpm} "
                                 f"at beat {ev.position}")
        for a, b in zip(ordered, ordered[1:]):
            if a.position == b.position:
                raise ValueError(f"duplicate tempo events at beat {a.position}")
        self._events = tuple(ordered)
        self._beats = tuple(ev.position for ev in ordered)
        self._spb = tuple(60.0 / ev.bpm for ev in ordered)   # seconds per beat
        # seconds at each event position, anchored so seconds_at(0) == 0:
        # the first event's bpm extends back to beat 0.
        secs = [self._beats[0] * self._spb[0]]
        for i in range(1, len(ordered)):
            secs.append(secs[-1] + (self._beats[i] - self._beats[i - 1])
                        * self._spb[i - 1])
        self._secs = tuple(secs)

    @property
    def events(self) -> tuple[TempoEvent, ...]:
        return self._events

    def seconds_at(self, beats: Beats) -> float:
        i = max(0, bisect_right(self._beats, beats) - 1)
        return self._secs[i] + (beats - self._beats[i]) * self._spb[i]

    def beats_at(self, seconds: float) -> Beats:
        i = max(0, bisect_right(self._secs, seconds) - 1)
        return self._beats[i] + (seconds - self._secs[i]) / self._spb[i]
