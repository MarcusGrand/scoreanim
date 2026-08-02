"""How far a stem may swell (core/animation/stem_caps.py).

A stem grows out of its notehead towards the beam, and the beam no
longer scales, so an unchecked stem would push straight through it.
Every beamed stem carries a ceiling; a flagged or unbeamed one does not.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation import scale_pivots, stem_scale_caps
from scoreanim.core.animation.scale_groups import (group_key, heads_by_group,
                                                   stem_is_up)
from scoreanim.core.engraving.svg_geom import path_outline
from scoreanim.core.engraving.types import Layout, PageGeometry, Rect
from scoreanim.core.score.identity import ElementId, ElementKind
from tests.test_scale_groups import LAYOUT, _el


def test_a_beamed_stem_stops_at_the_beam() -> None:
    """The stem runs from its pivot on the low head (y 9) up to y -20,
    and the beam's far edge is at y -22, so it may grow 31/29."""
    cap = stem_scale_caps(LAYOUT)[ElementId("stem")]
    assert cap == pytest.approx(31.0 / 29.0)


def _tilted(rise: float) -> Layout:
    """One note under a beam that climbs `rise` units over its 30-unit
    run. The stem sits at the LOW end, where the beam's box reaches far
    above the beam's own ink."""
    top_left, top_right = -22.0, -22.0 - rise
    return Layout(
        pages=(PageGeometry(1, 100.0, 100.0),),
        elements=(
            _el("head", ElementKind.NOTEHEAD, 0.0, Rect(0, 8, 2, 2)),
            _el("stem", ElementKind.STEM, 0.0, Rect(2, -20, 1, 29)),
            _el("beam", ElementKind.BEAM, 0.0, Rect(2, top_right, 30, rise + 2),
                corners=((2, top_left), (32, top_right),
                         (32, top_right + 2), (2, top_left + 2))),
        ))


def test_a_tilted_beam_is_measured_where_the_stem_meets_it() -> None:
    """Marcus, 2026-08-01: an upward-tilted eighth beam let its stems
    grow straight through it. The beam's BOX reaches 20 units higher
    than its ink does over this stem, and a box-shaped answer would let
    the stem grow to 51/29 instead of 31/29."""
    layout = _tilted(20.0)
    cap = stem_scale_caps(layout)[ElementId("stem")]
    assert cap == pytest.approx(31.0 / 29.0)
    # what the box would have said, for the record
    assert cap < (20.0 + 31.0) / 29.0


def test_a_tilt_is_read_across_the_whole_width_of_the_stem() -> None:
    """The stem has width, so its far side reaches a lower part of a
    beam that tilts DOWN to the right — the tightest reading wins, and
    no ink leaves the beam anywhere across the stem."""
    layout = _tilted(-30.0)                  # falls 1 unit per unit of run
    cap = stem_scale_caps(layout)[ElementId("stem")]
    # at the stem's right edge (x 3) the beam's top edge is at y -21
    assert cap == pytest.approx(30.0 / 29.0)


def test_an_unbeamed_stem_has_no_ceiling() -> None:
    caps = stem_scale_caps(LAYOUT)
    assert ElementId("stem-2") not in caps          # flagged
    assert ElementId("orphan-stem") not in caps     # never scales anyway


def test_only_stems_carry_a_ceiling() -> None:
    caps = stem_scale_caps(LAYOUT)
    assert set(caps) == {ElementId("stem")}


def test_a_beam_on_the_staff_above_is_not_this_stem_s_beam() -> None:
    """The near-miss that got through the first time (video_test, 2026-
    08-01): an unbeamed stem points up at the beam of the part above,
    which came within half a stem's length and capped it. A beam is this
    stem's only where the stem's tip is drawn INSIDE it."""
    layout = Layout(
        pages=(PageGeometry(1, 100.0, 100.0),),
        elements=(
            _el("head", ElementKind.NOTEHEAD, 0.0, Rect(0, 8, 2, 2)),
            _el("stem", ElementKind.STEM, 0.0, Rect(2, -20, 1, 29)),
            # 30 units clear of the tip: another staff's beam
            _el("beam", ElementKind.BEAM, 0.0, Rect(2, -60, 30, 9)),
        ))
    assert ElementId("stem") not in stem_scale_caps(layout)


def _ink_span_at(el, x: float) -> tuple[float, float] | None:
    """Where this element's drawn ink starts and ends at this x. Worked
    out from the path data, not from the module's own reasoning."""
    low = high = None
    for path in el.glyph.paths:
        for ring in path_outline(path.d, path.transform):
            for i, (x1, y1) in enumerate(ring):
                x2, y2 = ring[(i + 1) % len(ring)]
                if x1 == x2 or not min(x1, x2) <= x <= max(x1, x2):
                    continue
                y = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
                low = y if low is None else min(low, y)
                high = y if high is None else max(high, y)
    return None if low is None else (low, high)


def test_real_fixture_no_capped_stem_leaves_its_beam(engraved) -> None:
    """The invariant, read off the ink: at every x across a stem, the
    grown tip is still inside every beam the stem is drawn into. A
    beam's BOX would not do — 28 of testscore's 38 beams are tilted, and
    a tilted box reaches well above its own ink."""
    layout = engraved.layout
    pivots = scale_pivots(layout)
    caps = stem_scale_caps(layout)
    heads = heads_by_group(layout)
    beams = [el for el in layout.elements
             if el.identity.kind is ElementKind.BEAM]

    checked = 0
    for el in layout.elements:
        eid = el.identity.element_id
        if el.identity.kind is not ElementKind.STEM or eid not in caps:
            continue
        up = stem_is_up(el, heads[group_key(el.identity)])
        tip = el.bbox.y if up else el.bbox.y2
        pivot = pivots[eid]
        grown = pivot.y + (tip - pivot.y) * caps[eid]
        inside = 0
        for beam in beams:
            if beam.system != el.system:
                continue
            for x in (el.bbox.x, el.bbox.center.x, el.bbox.x2):
                span = _ink_span_at(beam, x)
                if span is None or not span[0] <= tip <= span[1]:
                    continue                     # not a beam this stem is in
                inside += 1
                far = span[0] if up else span[1]
                assert grown >= far - 1e-9 if up else grown <= far + 1e-9
        assert inside                            # capped, so it is beamed
        checked += 1
    assert checked > 50


def test_real_fixture_no_beamed_stem_escapes_a_ceiling(engraved) -> None:
    """The other half: every stem whose tip is drawn inside a beam has a
    cap. A stem that slipped through would pop straight past its beam."""
    layout = engraved.layout
    caps = stem_scale_caps(layout)
    pivots = scale_pivots(layout)
    heads = heads_by_group(layout)
    beams = [el for el in layout.elements
             if el.identity.kind is ElementKind.BEAM]

    beamed = 0
    for el in layout.elements:
        eid = el.identity.element_id
        if (el.identity.kind is not ElementKind.STEM
                or eid not in pivots
                or not heads.get(group_key(el.identity))):
            continue
        up = stem_is_up(el, heads[group_key(el.identity)])
        tip = el.bbox.y if up else el.bbox.y2
        for beam in beams:
            if beam.system != el.system:
                continue
            span = _ink_span_at(beam, el.bbox.center.x)
            if span is not None and span[0] <= tip <= span[1]:
                assert eid in caps, eid
                beamed += 1
                break
    assert beamed > 50


def test_real_fixture_beamed_stems_are_capped_and_flagged_ones_are_not(
        engraved) -> None:
    """testscore has 252 stems; the beamed ones are the ones with a
    ceiling, and every ceiling still lets the stem grow a little."""
    caps = stem_scale_caps(engraved.layout)
    stems = [el for el in engraved.layout.elements
             if el.identity.kind is ElementKind.STEM]
    capped = [el for el in stems if el.identity.element_id in caps]
    assert 50 < len(capped) < len(stems)
    for value in caps.values():
        assert value >= 1.0
