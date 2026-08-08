"""The tick grid (core/animation/onset_grid.py): bar/beat/eighth
ranks, interpolated x, the end-anchor stretch, and the snap merge that
keeps a note on a 16th reachable."""
from __future__ import annotations

from scoreanim.core.animation import (GridTick, OnsetStop, TickRank,
                                      grid_for_system, quantize_beats,
                                      snap_targets)
from scoreanim.core.score.model import MeasureInfo

MEASURES = (MeasureInfo(number=1, start=0.0, quarter_length=2.0),
            MeasureInfo(number=2, start=2.0, quarter_length=2.0))
# events on the downbeats and beat 2 of bar 1; x linear at 100/beat
STOPS = (OnsetStop(0.0, 100.0), OnsetStop(1.0, 200.0),
         OnsetStop(2.0, 300.0))


def test_grid_ranks_and_interpolated_x() -> None:
    ticks = grid_for_system(STOPS, MEASURES, (1, 2), end_x=500.0)
    by_beat = {t.beats: t for t in ticks}
    # bars at 0 and 2, a closing bar at 4
    assert by_beat[0.0].rank is TickRank.BAR
    assert by_beat[2.0].rank is TickRank.BAR
    assert by_beat[4.0].rank is TickRank.BAR
    # quarters are beats, eighths are eighths
    assert by_beat[1.0].rank is TickRank.BEAT
    assert by_beat[3.0].rank is TickRank.BEAT
    assert by_beat[0.5].rank is TickRank.EIGHTH
    assert by_beat[3.5].rank is TickRank.EIGHTH
    # interpolated between events, stretched to the end anchor
    assert by_beat[0.5].x == 150.0
    assert by_beat[3.0].x == 400.0            # between last stop and end_x
    assert by_beat[4.0].x == 500.0
    # sorted and x-monotone, the stops' own invariants
    beats = [t.beats for t in ticks]
    assert beats == sorted(beats)
    xs = [t.x for t in ticks]
    assert xs == sorted(xs)


def test_grid_without_end_anchor_clamps_the_last_bar() -> None:
    ticks = grid_for_system(STOPS, MEASURES, (1, 2))
    by_beat = {t.beats: t for t in ticks}
    assert by_beat[3.0].x == 300.0            # clamped at the last stop
    assert by_beat[4.0].x == 300.0


def test_grid_is_empty_without_stops_or_measures() -> None:
    assert grid_for_system((), MEASURES, (1, 2)) == ()
    assert grid_for_system(STOPS, MEASURES, ()) == ()


def test_snap_targets_merge_events_over_ticks() -> None:
    """The 16th-note case: the ruler shows eighths, but an event on a
    16th stays snappable — and where a tick and an event share a beat,
    the event's exact x wins over the interpolation."""
    ticks = (GridTick(0.0, 99.0, TickRank.BAR),
             GridTick(0.5, 150.0, TickRank.EIGHTH))
    stops = (OnsetStop(0.0, 100.0),            # same beat as the bar tick
             OnsetStop(0.25, 125.0))           # a 16th — no tick shows it
    merged = snap_targets(stops, ticks)
    assert [s.beats for s in merged] == [0.0, 0.25, 0.5]
    assert merged[0].x == 100.0                # the event's x, not 99.0
    assert quantize_beats(merged[1].beats) == quantize_beats(0.25)
