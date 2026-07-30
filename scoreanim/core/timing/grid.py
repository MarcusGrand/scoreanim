"""The timeline grid: which beats get a line in the lane.

Pure beat arithmetic. A tick is a musical beat on the performance axis
(rule 12) — never a measure ordinal and never a pixel — so repeats need
no special case here: a repeated bar's second pass has its own beats and
gets its own ticks.

Bar spans come from `MeasureInfo.quarter_length`, which is the ENGRAVED
span, so pickups, meter changes and the final bar are already right and
need no time-signature reading. A bar whose span is not a whole number of
steps simply gets fewer ticks; none is ever emitted at or past the bar
end.

Known limit — a repeated bar's second pass gets subdivisions but NO
barline and no number. `MeasureInfo` holds one entry per document-order
measure, so the bar at a repeat end carries a `quarter_length` covering
the whole second pass (measured on complex3: ordinal 37 spans 12.0 for a
4/4 bar). The pass offset is a whole number of quarters, so the
subdivisions still land on real beats. See BACKLOG.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Sequence

from scoreanim.core.score.identity import Beats
from scoreanim.core.score.model import MeasureInfo

_EPS = 1e-9
_PLACES = 6                      # tick beats round here, so 1/8T is stable


@dataclass(frozen=True)
class GridUnit:
    """One entry of the lane's grid selector."""
    label: str
    beats: float | None          # step in quarters; None = barlines only


BARS = GridUnit("Bars", None)
QUARTER = GridUnit("1/4", 1.0)
EIGHTH = GridUnit("1/8", 0.5)
EIGHTH_TRIPLET = GridUnit("1/8T", 1.0 / 3.0)
SIXTEENTH = GridUnit("1/16", 0.25)

GRID_UNITS: tuple[GridUnit, ...] = (BARS, QUARTER, EIGHTH, EIGHTH_TRIPLET,
                                    SIXTEENTH)

# Coarsening ladder, used when ticks crowd together on screen. Every step
# up drops lines and keeps the rest exactly where they were — each unit's
# beats are a subset of the finer one's (1/8T thins to 1/4, not 1/8).
_COARSER: dict[str, GridUnit] = {
    SIXTEENTH.label: EIGHTH,
    EIGHTH_TRIPLET.label: QUARTER,
    EIGHTH.label: QUARTER,
    QUARTER.label: BARS,
}


@dataclass(frozen=True)
class GridTick:
    beat: Beats
    barline: bool
    measure: int | None          # printed number; barlines only


@dataclass(frozen=True)
class TickGrid:
    """Ticks in beat order, plus the parallel beat tuple to bisect on."""
    ticks: tuple[GridTick, ...]
    beats: tuple[Beats, ...]

    def between(self, lo: Beats, hi: Beats) -> tuple[GridTick, ...]:
        """The ticks with lo <= beat <= hi."""
        return self.ticks[bisect_left(self.beats, lo):
                          bisect_right(self.beats, hi)]

    def nearest(self, beat: Beats) -> GridTick | None:
        """The tick closest to `beat`, or None on an empty grid."""
        if not self.ticks:
            return None
        i = bisect_left(self.beats, beat)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(self.ticks):
                if best is None or abs(self.beats[j] - beat) < \
                        abs(self.beats[best] - beat):
                    best = j
        return self.ticks[best] if best is not None else None


EMPTY = TickGrid((), ())


def grid_ticks(measures: Sequence[MeasureInfo], unit: GridUnit) -> TickGrid:
    """A barline at every measure start, plus a tick every `unit.beats`
    quarters inside each bar's engraved span."""
    ticks: list[GridTick] = []
    for measure in measures:
        start = round(measure.start, _PLACES)
        ticks.append(GridTick(start, True, measure.number))
        step = unit.beats
        if step is None or step <= 0.0:
            continue
        k = 1
        while k * step < measure.quarter_length - _EPS:
            ticks.append(GridTick(round(start + k * step, _PLACES),
                                  False, None))
            k += 1
    ticks.sort(key=lambda t: t.beat)
    return TickGrid(tuple(ticks), tuple(t.beat for t in ticks))


def coarsened(unit: GridUnit, px_per_beat: float,
              min_px: float = 6.0) -> GridUnit:
    """Thin the grid until its ticks are at least `min_px` apart, so a
    zoomed-out 1/16 grid reads as bars instead of a grey wall."""
    while unit.beats is not None and unit.beats * px_per_beat < min_px:
        unit = _COARSER[unit.label]
    return unit
