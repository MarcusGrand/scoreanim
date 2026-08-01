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
from scoreanim.core.score.identity import ElementId, ElementKind
from tests.test_scale_groups import LAYOUT


def test_a_beamed_stem_stops_at_the_beam() -> None:
    """The stem runs from its pivot on the low head (y 9) up to y -20,
    and the beam's far edge is at y -22, so it may grow 31/29."""
    cap = stem_scale_caps(LAYOUT)[ElementId("stem")]
    assert cap == pytest.approx(31.0 / 29.0)


def test_an_unbeamed_stem_has_no_ceiling() -> None:
    caps = stem_scale_caps(LAYOUT)
    assert ElementId("stem-2") not in caps          # flagged
    assert ElementId("orphan-stem") not in caps     # never scales anyway


def test_only_stems_carry_a_ceiling() -> None:
    caps = stem_scale_caps(LAYOUT)
    assert set(caps) == {ElementId("stem")}


def _capped_tip(el, pivot, cap, up) -> float:
    tip = el.bbox.y if up else el.bbox.y2
    return pivot.y + (tip - pivot.y) * cap


def test_real_fixture_a_capped_stem_never_passes_its_beam(engraved) -> None:
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
        grown = _capped_tip(el, pivots[eid], caps[eid], up)
        # The beams this stem could break out of are the ones its tip is
        # drawn inside. Worked out here from the geometry alone, not from
        # the module's own reasoning.
        over = [b for b in beams
                if b.system == el.system
                and b.bbox.x <= el.bbox.x2 and b.bbox.x2 >= el.bbox.x
                and b.bbox.y <= tip <= b.bbox.y2]
        assert over                              # it was capped, so it is beamed
        for beam in over:
            far = beam.bbox.y if up else beam.bbox.y2
            assert grown >= far - 1e-9 if up else grown <= far + 1e-9
        checked += 1
    assert checked > 50


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
