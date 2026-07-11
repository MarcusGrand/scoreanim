"""Swing regions: a beat-domain onset warp per region (PHASES 4.4).

Swing shifts off-beat subdivisions inside a region: ratio 0.5 is straight,
~0.667 is triplet swing. The warp is applied to trigger beats BEFORE
``TempoMap.seconds_at`` (the seam tempo_map.py reserved); TempoMap itself
never changes for it.

Warp math, per quarter inside a region (p = fractional beat):

    p ≤ 0.5 :  p′ = 2·r·p                      # [0, 0.5] → [0, r]
    p > 0.5 :  p′ = r + 2·(1 − r)·(p − 0.5)    # [0.5, 1] → [r, 1]

Whole beats are fixed points, so the warp is continuous across quarters
and at region edges (whole-beat endpoints enforced by validation);
r = 0.5 is the identity; the map is strictly monotone for r < 1. The
off-beat eighth lands exactly at r; sixteenths shift proportionally.

``resolve_seconds`` is THE beats→seconds resolution point for triggers
from Phase 4 on (render/animate.py calls it) — tie-inherited and grace
fractional trigger beats warp consistently for free.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from scoreanim.core.score.identity import Beats
from scoreanim.core.timing.tempo_map import TempoMap


@dataclass(frozen=True)
class SwingRegion:
    span: tuple[Beats, Beats]    # [start, end), whole-beat endpoints
    ratio: float                 # 0.5 straight … <1.0; 0.667 = triplet


def validate_regions(regions: Sequence[SwingRegion]) -> None:
    """Raise ValueError unless every region has whole-beat endpoints,
    positive extent, a sane ratio, and no region overlaps another
    (touching spans are fine)."""
    for r in regions:
        start, end = r.span
        if not (math.isfinite(start) and math.isfinite(end)):
            raise ValueError(f"swing span {r.span} is not finite")
        if start != int(start) or end != int(end):
            raise ValueError(f"swing span {r.span} must start and end on "
                             f"whole beats")
        if not start < end:
            raise ValueError(f"swing span {r.span} is empty or reversed")
        if start < 0:
            raise ValueError(f"swing span {r.span} starts before beat 0")
        if not 0.5 <= r.ratio < 1.0:
            raise ValueError(f"swing ratio {r.ratio} outside [0.5, 1.0)")
    ordered = sorted(regions, key=lambda r: r.span[0])
    for a, b in zip(ordered, ordered[1:]):
        if b.span[0] < a.span[1]:
            raise ValueError(f"swing regions {a.span} and {b.span} overlap")


def swing_warp(beats: Beats, regions: Sequence[SwingRegion]) -> Beats:
    """Warp a beat position through the region containing it (identity
    outside all regions). ``regions`` must satisfy validate_regions."""
    for region in regions:
        if region.span[0] <= beats < region.span[1]:
            quarter = math.floor(beats)
            p = beats - quarter
            if p <= 0.5:
                p = 2.0 * region.ratio * p
            else:
                p = region.ratio + 2.0 * (1.0 - region.ratio) * (p - 0.5)
            return quarter + p
    return beats


def resolve_seconds(beats: Sequence[Beats], tempo_map: TempoMap,
                    regions: Sequence[SwingRegion] = ()) -> list[float]:
    """Trigger beats → score seconds: swing warp, then the tempo map.
    Strictly monotone (both stages are), so sorted trigger schedules
    stay sorted."""
    if not regions:
        return [tempo_map.seconds_at(b) for b in beats]
    return [tempo_map.seconds_at(swing_warp(b, regions)) for b in beats]
