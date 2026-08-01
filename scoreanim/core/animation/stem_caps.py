"""How far a stem may swell before it would cross its beam.

A stem pivots on the head at its foot (`scale_groups.py`), so a scale
grows it out towards the beam. The beam itself no longer scales, so an
unchecked stem would push straight through it and stick out the far
side. This module works out the largest scale each stem may take, as a
plain number the applier clamps to (Marcus, 2026-08-01).

The room is small: measured on `testscore`, a beam's far edge sits about
3% of a stem's length past the stem's tip. So a BEAMED stem barely
lengthens — it thickens with its note and stays put — while a flagged or
unbeamed stem has no beam to cross, gets no entry here, and pops with
its head as before.

**A beam is measured where the stem meets it, never by its box.** A
tilted beam's box reaches far above its own ink at the low end of the
slant, and a box-shaped answer let those stems grow through it (Marcus,
2026-08-01, after seeing it happen on an upward-tilted eighth beam). So
the beam's edge is read off its drawn outline at the stem's own x, at
both sides of the stem and in the middle, and the tightest of those
readings wins — no ink of a stem may leave the beam anywhere across its
width.

There is no stored link between a stem and its beam — the adapter keeps
musical identity, not geometry — so the join is geometric, the same way
ledger dashes find their note (`engraving/verovio/attribution.py`). A
beam counts as this stem's when it is on the same system and its ink
straddles the stem's tip.
"""
from __future__ import annotations

from scoreanim.core.animation.schedule import is_animated
from scoreanim.core.animation.scale_groups import (group_key, heads_by_group,
                                                   scale_pivots, stem_is_up)
from scoreanim.core.engraving.svg_geom import Ring, path_outline
from scoreanim.core.engraving.types import Layout, RenderedElement
from scoreanim.core.score.identity import ElementId, ElementKind

# A stem's tip is drawn INSIDE its beam, so that is the test: the ink at
# the stem's x must straddle the tip. The slack, as a multiple of the
# beam's own thickness there, only covers a stem drawn a little short or
# a little long. Measured in stem lengths instead, a beam one staff up
# came within reach on video_test and a stem grew into it.
_SLACK = 1.0

# ...and never less than this many page units, so a beam drawn as a hair
# line (no thickness to take a share of) still claims its stem. A staff
# space is 18 units here, so this cannot reach the staff above.
_MIN_SLACK = 2.0

# Below this the stem is too short to divide by (a grace-note stub whose
# tip has landed on its pivot).
_MIN_LENGTH = 1e-6

_EPS = 1e-9


def _outline(el: RenderedElement) -> tuple[Ring, ...]:
    """Every ring of an element's drawn ink, in page coordinates."""
    rings: list[Ring] = []
    for path in el.glyph.paths:
        rings.extend(path_outline(path.d, path.transform))
    return tuple(rings)


def _span_at(rings: tuple[Ring, ...], x: float) -> tuple[float, float] | None:
    """How far the ink reaches up and down the page at this x, or None
    where there is no ink. Every edge of every ring is cut by the
    vertical line at x — which is exact for a polygon, and a beam is
    one."""
    low = high = None
    for ring in rings:
        for i, (x1, y1) in enumerate(ring):
            x2, y2 = ring[(i + 1) % len(ring)]
            if abs(x2 - x1) < _EPS:               # a vertical edge
                if abs(x1 - x) > _EPS:
                    continue
                ys = (y1, y2)
            elif min(x1, x2) <= x <= max(x1, x2):
                ys = (y1 + (y2 - y1) * (x - x1) / (x2 - x1),)
            else:
                continue
            for y in ys:
                low = y if low is None else min(low, y)
                high = y if high is None else max(high, y)
    return None if low is None else (low, high)


def _beam_reach(beam: RenderedElement, stem: RenderedElement, tip: float,
                grow: float) -> float | None:
    """How far past the stem's tip this beam's far edge lies, measured
    along the stem's growth direction — or None if the beam is not this
    stem's. The tightest reading across the stem's width wins."""
    rings = _outline(beam)
    box = stem.bbox
    tightest: float | None = None
    for x in (box.x, box.center.x, box.x2):
        span = _span_at(rings, x)
        if span is None:
            continue                              # no beam ink over here
        near = ((span[1] if grow < 0 else span[0]) - tip) * grow
        far = ((span[0] if grow < 0 else span[1]) - tip) * grow
        slack = max((span[1] - span[0]) * _SLACK, _MIN_SLACK)
        if near > slack or far < -slack:
            return None                           # the tip is not in it
        tightest = far if tightest is None else min(tightest, far)
    return tightest


def stem_scale_caps(layout: Layout) -> dict[ElementId, float]:
    """The largest scale each beamed stem may take, keyed by element.

    An element absent from the map has no ceiling. A cap is never below
    1.0: a stem that already touches its beam simply does not lengthen.
    """
    heads = heads_by_group(layout)
    pivots = scale_pivots(layout)
    beams: dict[int | None, list[RenderedElement]] = {}
    for el in layout.elements:
        if el.identity.kind is ElementKind.BEAM:
            beams.setdefault(el.system, []).append(el)

    caps: dict[ElementId, float] = {}
    for el in layout.elements:
        ident = el.identity
        if ident.kind is not ElementKind.STEM or not is_animated(ident):
            continue
        pivot = pivots.get(ident.element_id)
        group_heads = heads.get(group_key(ident))
        if pivot is None or not group_heads:
            continue                              # it does not scale anyway

        up = stem_is_up(el, group_heads)
        grow = -1.0 if up else 1.0                # the way the stem lengthens
        tip = el.bbox.y if up else el.bbox.y2

        beyond: float | None = None
        for beam in beams.get(el.system, ()):
            if beam.bbox.x2 < el.bbox.x or beam.bbox.x > el.bbox.x2:
                continue                          # nowhere near this stem
            room = _beam_reach(beam, el, tip, grow)
            if room is None:
                continue
            # Every beam over the tip binds, so the tightest one wins. A
            # 16th group's two beams are one element, and _span_at reads
            # them as one thickness, so this is not the way to the outer
            # edge of a stack — it is the guard against a second beam.
            beyond = room if beyond is None else min(beyond, room)
        if beyond is None:
            continue                              # flagged, or unbeamed

        span = tip - pivot.y
        if abs(span) < _MIN_LENGTH:
            continue
        limit = tip + max(0.0, beyond) * grow
        caps[ident.element_id] = max(1.0, (limit - pivot.y) / span)
    return caps
