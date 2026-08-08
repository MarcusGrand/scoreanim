"""The places an element may be moved to: one system's onset stops.

A re-timed element steps between the events that already exist in its
OWN system — its own system, so it can never be sent to a page that is
not on screen when it fires. A stop is one distinct NOTATED onset of
the system's anchor ink (noteheads, rests, whole-bar rests, slashes,
bar repeats) across ALL parts. Notated onset, not trigger: a rest's
trigger is retrospective, but the place it sits on the page is its
onset.

`x` is the LEFTMOST ink at that onset, in page units — unused by the
stepper, but the next step's on-page drag indicator snaps to it, and
building it here means the two steps snap to provably the same stops.
(The two existing per-onset sweeps, reveal.py's anchor builder and the
oracle's D2 audit, both keep the RIGHT edge — max bbox.x2 — because a
reveal edge is where ink ends; a stop is where it starts.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from scoreanim.core.animation.schedule import ANCHOR_KINDS, quantize_beats
from scoreanim.core.engraving.types import Layout
from scoreanim.core.score.identity import Beats


@dataclass(frozen=True)
class OnsetStop:
    beats: Beats
    x: float


def stops_for_system(layout: Layout, system: int) -> tuple[OnsetStop, ...]:
    """All distinct anchor onsets of one system, sorted by beat, each
    carrying the leftmost ink at that onset."""
    by_q: dict[int, tuple[Beats, float]] = {}
    for el in layout.elements:
        ident = el.identity
        if (el.system != system or ident.kind not in ANCHOR_KINDS
                or ident.onset is None):
            continue
        q = quantize_beats(ident.onset)
        kept = by_q.get(q)
        if kept is None or el.bbox.x < kept[1]:
            by_q[q] = (ident.onset, el.bbox.x)
    return tuple(OnsetStop(beats, x)
                 for _, (beats, x) in sorted(by_q.items()))


def step_from(stops: Sequence[OnsetStop], current: Beats,
              direction: int) -> Beats | None:
    """The beat one step earlier (direction < 0) or later (> 0) than
    `current`, or None when no stop lies that way.

    Earlier is the nearest stop strictly before the current effective
    beat, later the nearest strictly after — so from an automatic time
    sitting between stops, the first press goes to the nearest stop in
    the pressed direction, and from a stop it walks to its neighbour.
    Stepping past either end of the system does nothing.
    """
    q = quantize_beats(current)
    if direction < 0:
        for stop in reversed(stops):
            if quantize_beats(stop.beats) < q:
                return stop.beats
    else:
        for stop in stops:
            if quantize_beats(stop.beats) > q:
                return stop.beats
    return None
