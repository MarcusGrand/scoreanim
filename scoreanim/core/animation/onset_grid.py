"""The tick grid a re-timed element can lock onto (2026-08-08 round 3).

Events are not enough: Marcus wants the cursor to land BETWEEN notes
too, on a Dorico-style grid — bars, beats, eighths, and no finer for
now. A tick's page x comes from straight-line interpolation between
the system's event stops (engraved spacing is close to linear between
onsets, and the ruler only has to look right), stretched to the
system's right edge so the last bar gets its ticks too.

Two consumers, one build: the ruler draws the ticks by rank, and the
drag snaps to `snap_targets` — the ticks MERGED with the event stops,
events winning where they coincide because their x is exact. That
merge is also what keeps a note on a 16th reachable: the ruler shows
eighths, but the note's own stop stays in the snap list.

Ranks are quarter-based for now: BEAT ticks sit on integer quarters
from the barline, so a 6/8 bar shows three quarter ticks rather than
two dotted-quarter beats. Meter-aware beats need the meter, which
MeasureInfo does not carry — a later step if it grates.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Mapping, Sequence

from scoreanim.core.animation.onset_stops import OnsetStop, x_at
from scoreanim.core.animation.schedule import quantize_beats
from scoreanim.core.engraving.types import Layout
from scoreanim.core.score.identity import Beats

EIGHTH = 0.5                     # the finest tick, in quarters


class TickRank(enum.IntEnum):
    BAR = 3
    BEAT = 2
    EIGHTH = 1


@dataclass(frozen=True)
class GridTick:
    beats: Beats
    x: float
    rank: TickRank


def system_end_x(layout: Layout, system: int) -> float | None:
    """The system's right edge: the furthest ink in it (the closing
    barline is an element, so it counts). None for an unknown system."""
    xs = [el.bbox.x2 for el in layout.elements if el.system == system]
    return max(xs) if xs else None


def grid_for_system(stops: Sequence[OnsetStop],
                    measures: Sequence,
                    ordinals: Sequence[int],
                    end_x: float | None = None) -> tuple[GridTick, ...]:
    """Bar, beat and eighth ticks across a system's measures.

    `ordinals` are the 1-based measure ordinals drawn in this system;
    `end_x` (system_end_x) anchors the last bar's ticks — without it
    they would all clamp onto the final onset's x. A closing BAR tick
    marks the system's end barline.
    """
    if not stops or not ordinals:
        return ()
    anchors = list(stops)
    last = measures[ordinals[-1] - 1]
    end_beats = last.start + last.quarter_length
    if end_x is not None and end_beats > anchors[-1].beats:
        anchors.append(OnsetStop(end_beats, max(end_x, anchors[-1].x)))
    ticks = []
    for ordinal in ordinals:
        measure = measures[ordinal - 1]
        steps = int(round(measure.quarter_length / EIGHTH))
        for k in range(steps):
            offset = k * EIGHTH
            beat = measure.start + offset
            rank = (TickRank.BAR if k == 0
                    else TickRank.BEAT if offset == int(offset)
                    else TickRank.EIGHTH)
            ticks.append(GridTick(beat, x_at(anchors, beat), rank))
    ticks.append(GridTick(end_beats, x_at(anchors, end_beats),
                          TickRank.BAR))
    return tuple(ticks)


def snap_targets(stops: Sequence[OnsetStop],
                 ticks: Sequence[GridTick]) -> tuple[OnsetStop, ...]:
    """Everything the cursor may land on: the grid plus the events,
    one target per distinct quantized beat, the event's exact x winning
    over a tick's interpolated one."""
    by_q = {quantize_beats(t.beats): OnsetStop(t.beats, t.x)
            for t in ticks}
    by_q.update({quantize_beats(s.beats): s for s in stops})
    return tuple(stop for _, stop in sorted(by_q.items()))
