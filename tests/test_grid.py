"""The timeline grid: tick beats, the window query, and coarsening."""
from __future__ import annotations

import pytest

from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing.grid import (BARS, EIGHTH, EIGHTH_TRIPLET, QUARTER,
                                        SIXTEENTH, coarsened, grid_ticks)

# a pickup, two 4/4 bars, a 3/2 bar, and a 1.5-beat oddity
MEASURES = (
    MeasureInfo(number=0, start=0.0, quarter_length=1.0),
    MeasureInfo(number=1, start=1.0, quarter_length=4.0),
    MeasureInfo(number=2, start=5.0, quarter_length=4.0),
    MeasureInfo(number=3, start=9.0, quarter_length=6.0),
    MeasureInfo(number=4, start=15.0, quarter_length=1.5),
)


def test_bars_only_are_the_measure_starts() -> None:
    grid = grid_ticks(MEASURES, BARS)
    assert grid.beats == (0.0, 1.0, 5.0, 9.0, 15.0)
    assert all(t.barline for t in grid.ticks)
    assert [t.measure for t in grid.ticks] == [0, 1, 2, 3, 4]


def test_subdivisions_stay_inside_the_engraved_span() -> None:
    grid = grid_ticks(MEASURES, QUARTER)
    # the 1.0-beat pickup gets its barline and nothing else; the 1.5-beat
    # bar gets one tick and none at the bar end
    assert [t.beat for t in grid.ticks if 0.0 <= t.beat < 1.0] == [0.0]
    assert [t.beat for t in grid.ticks if t.beat >= 15.0] == [15.0, 16.0]


@pytest.mark.parametrize("unit,per_quarter", [(QUARTER, 1), (EIGHTH, 2),
                                              (EIGHTH_TRIPLET, 3),
                                              (SIXTEENTH, 4)])
def test_tick_count_in_a_four_four_bar(unit, per_quarter) -> None:
    bar = (MeasureInfo(number=1, start=1.0, quarter_length=4.0),)
    assert len(grid_ticks(bar, unit).ticks) == 4 * per_quarter


def test_triplets_land_on_thirds_and_include_the_whole_beats() -> None:
    bar = (MeasureInfo(number=1, start=0.0, quarter_length=2.0),)
    assert grid_ticks(bar, EIGHTH_TRIPLET).beats == (
        0.0, 0.333333, 0.666667, 1.0, 1.333333, 1.666667)


def test_ticks_are_sorted_and_unique() -> None:
    for unit in (BARS, QUARTER, EIGHTH, EIGHTH_TRIPLET, SIXTEENTH):
        beats = grid_ticks(MEASURES, unit).beats
        assert list(beats) == sorted(beats)
        assert len(set(beats)) == len(beats)


def test_only_barlines_carry_a_measure_number() -> None:
    for tick in grid_ticks(MEASURES, SIXTEENTH).ticks:
        assert (tick.measure is not None) == tick.barline


def test_between_is_inclusive_at_both_ends() -> None:
    grid = grid_ticks(MEASURES, QUARTER)
    assert [t.beat for t in grid.between(5.0, 7.0)] == [5.0, 6.0, 7.0]
    assert grid.between(100.0, 200.0) == ()


def test_nearest_picks_the_closer_side() -> None:
    grid = grid_ticks(MEASURES, QUARTER)
    assert grid.nearest(6.4).beat == 6.0
    assert grid.nearest(6.6).beat == 7.0
    assert grid.nearest(-50.0).beat == 0.0
    assert grid.nearest(500.0).beat == 16.0
    assert grid_ticks((), QUARTER).nearest(1.0) is None


def test_empty_score_has_no_ticks() -> None:
    assert grid_ticks((), SIXTEENTH).ticks == ()


@pytest.mark.parametrize("unit,px_per_beat,expected", [
    (SIXTEENTH, 100.0, SIXTEENTH),       # roomy: unchanged
    (SIXTEENTH, 20.0, EIGHTH),           # 5 px apart -> thin once
    (SIXTEENTH, 10.0, QUARTER),
    (SIXTEENTH, 2.0, BARS),              # thins all the way out
    (EIGHTH_TRIPLET, 10.0, QUARTER),     # triplets thin to quarters
    (BARS, 0.01, BARS),                  # barlines always draw
])
def test_coarsening_ladder(unit, px_per_beat, expected) -> None:
    assert coarsened(unit, px_per_beat) == expected
