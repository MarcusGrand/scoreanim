"""Swing warp math (PHASES 4.4), headless. Onset positions at ratios
0.5 / 0.6 / 0.667 are the spec's pinned cases."""
from __future__ import annotations

import pytest

from scoreanim.core.timing import (SwingRegion, TempoEvent, TempoMap,
                                   resolve_seconds, swing_warp,
                                   validate_regions)

REGION = (SwingRegion((4.0, 8.0), 0.667),)


@pytest.mark.parametrize("ratio", [0.5, 0.6, 0.667])
def test_offbeat_eighth_lands_exactly_at_ratio(ratio: float) -> None:
    regions = (SwingRegion((0.0, 4.0), ratio),)
    assert swing_warp(1.5, regions) == pytest.approx(1.0 + ratio)


@pytest.mark.parametrize("ratio", [0.5, 0.6, 0.667])
def test_sixteenths_shift_proportionally(ratio: float) -> None:
    regions = (SwingRegion((0.0, 4.0), ratio),)
    # first half of the beat compresses to [0, r], second expands to [r, 1]
    assert swing_warp(2.25, regions) == pytest.approx(2.0 + ratio / 2)
    assert swing_warp(2.75, regions) == pytest.approx(
        2.0 + ratio + (1.0 - ratio) / 2)


def test_ratio_half_is_identity() -> None:
    regions = (SwingRegion((0.0, 8.0), 0.5),)
    for b in (0.0, 0.25, 0.5, 1.5, 3.75, 7.999):
        assert swing_warp(b, regions) == pytest.approx(b)


def test_identity_outside_regions_and_whole_beats_fixed() -> None:
    for b in (0.0, 3.999, 8.0, 10.5):          # outside [4, 8)
        assert swing_warp(b, REGION) == b
    for b in (4.0, 5.0, 6.0, 7.0):             # whole beats are fixed points
        assert swing_warp(b, REGION) == b


def test_continuity_at_region_edges_and_monotonicity() -> None:
    eps = 1e-6
    # continuous at the region start and end (whole-beat endpoints)
    assert swing_warp(4.0 + eps, REGION) == pytest.approx(4.0, abs=1e-5)
    assert swing_warp(8.0 - eps, REGION) == pytest.approx(8.0, abs=1e-5)
    # strictly monotone through the region
    beats = [4.0 + i / 64 for i in range(4 * 64 + 1)]
    warped = [swing_warp(b, REGION) for b in beats]
    assert all(w1 > w0 for w0, w1 in zip(warped, warped[1:]))


def test_resolve_seconds_is_warp_then_tempo_map() -> None:
    m = TempoMap([TempoEvent(0.0, 120.0), TempoEvent(6.0, 90.0)])
    beats = [0.0, 1.5, 4.5, 5.5, 6.5, 9.0]
    got = resolve_seconds(beats, m, REGION)
    expected = [m.seconds_at(swing_warp(b, REGION)) for b in beats]
    assert got == pytest.approx(expected)
    # sorted in, sorted out (strict monotonicity end to end)
    assert got == sorted(got)
    # without regions: plain seconds_at
    assert resolve_seconds(beats, m) == pytest.approx(
        [m.seconds_at(b) for b in beats])


def test_swung_offbeat_delay_is_predictable() -> None:
    """At 120 bpm (0.5 s/beat), ratio 0.667 delays an off-beat eighth by
    (0.667 − 0.5) · 0.5 s = 83.5 ms."""
    m = TempoMap([TempoEvent(0.0, 120.0)])
    straight, = resolve_seconds([4.5], m)
    swung, = resolve_seconds([4.5], m, REGION)
    assert swung - straight == pytest.approx(0.167 * 0.5, abs=1e-9)


def test_validate_regions() -> None:
    validate_regions((SwingRegion((0.0, 4.0), 0.6),
                      SwingRegion((4.0, 8.0), 0.667)))   # touching is fine
    with pytest.raises(ValueError, match="overlap"):
        validate_regions((SwingRegion((0.0, 4.0), 0.6),
                          SwingRegion((3.0, 8.0), 0.6)))
    with pytest.raises(ValueError, match="whole beats"):
        validate_regions((SwingRegion((0.5, 4.0), 0.6),))
    with pytest.raises(ValueError, match="ratio"):
        validate_regions((SwingRegion((0.0, 4.0), 0.45),))
    with pytest.raises(ValueError, match="ratio"):
        validate_regions((SwingRegion((0.0, 4.0), 1.0),))
    with pytest.raises(ValueError, match="empty or reversed"):
        validate_regions((SwingRegion((4.0, 4.0), 0.6),))
