"""TempoMap: exact segment math, invertibility, monotonicity, validation."""
from __future__ import annotations

import random

import pytest

from scoreanim.core.timing import TempoEvent, TempoMap


def test_single_event_is_exact_linear() -> None:
    tm = TempoMap([TempoEvent(0.0, 120.0)])
    for b in (0.0, 1.0, 2.5, 7.0, 100.0):
        assert tm.seconds_at(b) == b * 0.5
        assert tm.beats_at(b * 0.5) == b


def test_two_segments_exact_at_and_around_boundary() -> None:
    tm = TempoMap([TempoEvent(0.0, 120.0), TempoEvent(8.0, 60.0)])
    assert tm.seconds_at(0.0) == 0.0
    assert tm.seconds_at(8.0) == 4.0                    # 8 beats @ 0.5 s/beat
    assert tm.seconds_at(7.5) == 3.75                   # still first segment
    assert tm.seconds_at(9.0) == 5.0                    # 4.0 + 1 beat @ 1 s/beat
    assert tm.seconds_at(16.0) == 12.0
    assert tm.beats_at(4.0) == 8.0
    assert tm.beats_at(3.75) == 7.5
    assert tm.beats_at(5.0) == 9.0
    assert tm.beats_at(12.0) == 16.0


def test_before_first_event_uses_first_bpm() -> None:
    tm = TempoMap([TempoEvent(4.0, 90.0), TempoEvent(8.0, 180.0)])
    spb = 60.0 / 90.0
    assert tm.seconds_at(0.0) == 0.0
    assert tm.seconds_at(3.0) == 3.0 * spb
    assert tm.seconds_at(4.0) == 4.0 * spb
    assert tm.beats_at(2.0 * spb) == pytest.approx(2.0, abs=1e-12)


def test_after_last_event_extends_last_bpm() -> None:
    tm = TempoMap([TempoEvent(0.0, 60.0), TempoEvent(4.0, 120.0)])
    assert tm.seconds_at(4.0) == 4.0
    assert tm.seconds_at(1000.0) == 4.0 + 996.0 * 0.5


def test_unsorted_input_is_sorted() -> None:
    tm = TempoMap([TempoEvent(8.0, 60.0), TempoEvent(0.0, 120.0)])
    assert tm.events[0].position == 0.0
    assert tm.seconds_at(8.0) == 4.0


@pytest.mark.parametrize("events", [
    [],
    [TempoEvent(0.0, 0.0)],
    [TempoEvent(0.0, -10.0)],
    [TempoEvent(0.0, 120.0), TempoEvent(0.0, 60.0)],
])
def test_invalid_events_raise(events: list[TempoEvent]) -> None:
    with pytest.raises(ValueError):
        TempoMap(events)


def _random_map(rng: random.Random) -> TempoMap:
    n = rng.randint(1, 8)
    positions = sorted(rng.sample(range(0, 400), n))
    return TempoMap([TempoEvent(float(p) + rng.random(), rng.uniform(20.0, 300.0))
                     for p in positions])


def test_property_round_trip() -> None:
    rng = random.Random(0)
    for _ in range(200):
        tm = _random_map(rng)
        for _ in range(50):
            b = rng.uniform(-4.0, 500.0)
            assert abs(tm.beats_at(tm.seconds_at(b)) - b) < 1e-9


def test_property_monotone_both_directions() -> None:
    rng = random.Random(1)
    for _ in range(100):
        tm = _random_map(rng)
        beats = sorted(rng.uniform(-4.0, 500.0) for _ in range(50))
        secs = [tm.seconds_at(b) for b in beats]
        assert all(a < b for a, b in zip(secs, secs[1:]))
        back = [tm.beats_at(s) for s in secs]
        assert all(a < b for a, b in zip(back, back[1:]))


def test_property_boundary_continuity() -> None:
    """No jump at segment boundaries: approaching from below converges."""
    rng = random.Random(2)
    for _ in range(50):
        tm = _random_map(rng)
        for ev in tm.events:
            below = tm.seconds_at(ev.position - 1e-9)
            at = tm.seconds_at(ev.position)
            assert abs(at - below) < 1e-6
