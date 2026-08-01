"""How far a stem may swell before it would cross its beam.

A stem pivots on the head at its foot (`scale_groups.py`), so a scale
grows it out towards the beam. The beam itself no longer scales, so an
unchecked stem would push straight through it and stick out the far
side. This module works out the largest scale each stem may take, as a
plain number the applier clamps to (Marcus, 2026-08-01).

The room is small: measured on `testscore`, a beam's far edge sits about
2% of a stem's length past the stem's tip. So a BEAMED stem barely
lengthens — it thickens with its note and stays put — while a flagged or
unbeamed stem has no beam to cross, gets no entry here, and pops with
its head as before.

There is no stored link between a stem and its beam — the adapter keeps
musical identity, not geometry — so the join is geometric, the same way
ledger dashes find their note (`engraving/verovio/attribution.py`). A
beam counts as this stem's when it is on the same system, overlaps the
stem horizontally, and lies just beyond the stem's tip.
"""
from __future__ import annotations

from scoreanim.core.animation.schedule import is_animated
from scoreanim.core.animation.scale_groups import (group_key, heads_by_group,
                                                   scale_pivots, stem_foot,
                                                   stem_is_up)
from scoreanim.core.engraving.types import Layout, RenderedElement
from scoreanim.core.score.identity import ElementId, ElementKind

# How far past a stem's tip a beam may start and still be its beam, as a
# share of the stem's own length. A beam is drawn right at the tip, so
# this only has to survive rounding and the thickness of a beam or two.
_REACH = 0.5

# Below this the stem is too short to divide by (a grace-note stub whose
# tip has landed on its pivot).
_MIN_LENGTH = 1e-6


def _beams_by_system(layout: Layout) -> dict[int | None, list[RenderedElement]]:
    beams: dict[int | None, list[RenderedElement]] = {}
    for el in layout.elements:
        if el.identity.kind is ElementKind.BEAM:
            beams.setdefault(el.system, []).append(el)
    return beams


def stem_scale_caps(layout: Layout) -> dict[ElementId, float]:
    """The largest scale each beamed stem may take, keyed by element.

    An element absent from the map has no ceiling. A cap is never below
    1.0: a stem that already touches its beam simply does not lengthen.
    """
    heads = heads_by_group(layout)
    pivots = scale_pivots(layout)
    beams = _beams_by_system(layout)

    caps: dict[ElementId, float] = {}
    for el in layout.elements:
        ident = el.identity
        if ident.kind is not ElementKind.STEM or not is_animated(ident):
            continue
        pivot = pivots.get(ident.element_id)
        group_heads = heads.get(group_key(ident))
        if pivot is None or not group_heads:
            continue                          # it does not scale anyway

        up = stem_is_up(el, group_heads)
        grow = -1.0 if up else 1.0            # the way the stem lengthens
        foot = stem_foot(el, group_heads)
        tip = el.bbox.y if up else el.bbox.y2
        reach = abs(foot - tip) * _REACH

        # How far past the tip each beam edge lies, along the stem's own
        # growth direction. The beam is this stem's when it straddles the
        # tip: it neither starts well past it nor ends well short of it.
        beyond = 0.0
        found = False
        for beam in beams.get(el.system, ()):
            box = beam.bbox
            if box.x2 < el.bbox.x or box.x > el.bbox.x2:
                continue                      # not over this stem
            near = ((box.y2 if up else box.y) - tip) * grow
            far = ((box.y if up else box.y2) - tip) * grow
            if near > reach or far < -reach:
                continue
            found = True
            beyond = max(beyond, far)         # a 16th group has two beams
        if not found:
            continue                          # flagged, or unbeamed
        limit = tip + beyond * grow

        span = tip - pivot.y
        if abs(span) < _MIN_LENGTH:
            continue
        caps[ident.element_id] = max(1.0, (limit - pivot.y) / span)
    return caps
