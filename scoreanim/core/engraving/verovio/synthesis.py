"""Slash and bar-repeat synthesis (CLAUDE.md rule 10): Dorico exports
both region kinds with no notes and Verovio draws nothing for them
(empty <space>), so the adapter synthesizes their elements — one slash
per beat, one % symbol per repeated bar — positioned from the staff-line
geometry _build_elements collected, so they render and animate like
notes.

Inputs: _LoadState + the staff-lines geometry map from _build_elements
(so it runs after element construction; synthetic elements never enter
the post-passes). Outputs: RenderedElements. _LoadState READS: prep
(slash_regions/repeat_regions/parts), measure_start, measure_duration.
WRITES: nothing.
"""

from __future__ import annotations

from scoreanim.core.engraving.svg_geom import path_bbox
from scoreanim.core.engraving.types import (Affine, PathPrimitive, Rect,
                                            RenderedElement,
                                            RenderPrimitive)
from scoreanim.core.engraving.verovio.records import _LoadState
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind)

# ---------------------------------------------------------------------------
# Slash synthesis (CLAUDE.md rule 10, plan D4): Dorico exports slash
# regions as <measure-style><slash/> with no notes; Verovio renders those
# measures empty (MEI <space>). One slash per slash-unit, onsets on the
# beats, positioned on the staff so they render and animate like notes.
# ---------------------------------------------------------------------------

# Slash notehead as a parallelogram with horizontal end caps (approximates
# SMuFL noteheadSlashHorizontalEnds), in staff-space units, y-down, origin
# at the glyph's horizontal center on the middle staff line.
_SLASH_D = "M0.475 -1 L0.675 -1 L-0.475 1 L-0.675 1 Z"


def _synthesize_slashes(st: _LoadState,
                        staff_geo: dict[tuple, tuple[int, int | None, Rect]]
                        ) -> list[RenderedElement]:
    out: list[RenderedElement] = []
    glyph_bbox = path_bbox(_SLASH_D)
    for region in st.prep.slash_regions:
        info = next(p for p in st.prep.parts if p.part_id == region.part)
        for m in range(region.start_measure, region.stop_measure):
            start = st.measure_start[m]
            count = round(st.measure_duration[m] / region.slash_unit_quarters)
            if count <= 0:
                raise ValueError(f"slash region {region.part} m{m}: "
                                 f"non-positive slash count")
            # v1 limitation: slash regions on the part's first staff
            page, system, staff_bbox = staff_geo[(region.part, m, 1)]
            staff_space = staff_bbox.h / 4
            mid_y = staff_bbox.y + staff_bbox.h / 2
            slot_w = staff_bbox.w / count
            for k in range(count):
                cx = staff_bbox.x + (k + 0.5) * slot_w
                onset = start + k * region.slash_unit_quarters
                tf = Affine(a=staff_space, d=staff_space, e=cx, f=mid_y)
                bbox = tf.apply_rect(glyph_bbox)
                identity = ElementIdentity(
                    element_id=ElementId(f"{region.part}:m{m}:slash:{k}"),
                    kind=ElementKind.SLASH,
                    part=region.part, part_name=info.name,
                    staff=1, voice=None, onset=onset,
                )
                out.append(RenderedElement(
                    identity=identity, page=page, x=cx, y=mid_y,
                    bbox=bbox, anchor=bbox.center,
                    glyph=RenderPrimitive(paths=(
                        PathPrimitive(d=_SLASH_D, transform=tf),)),
                    system=system,
                ))
    return out


# Measure-repeat symbol (approximates SMuFL repeat1Bar): a bold oblique
# stroke with a dot in the upper-left and lower-right quadrants, in
# staff-space units, y-down, origin at the glyph's center on the middle
# staff line.
_REPEAT_D = ("M0.25 -1.1 L0.95 -1.1 L-0.25 1.1 L-0.95 1.1 Z "
             "M-0.62 -0.88 L-0.36 -0.62 L-0.62 -0.36 L-0.88 -0.62 Z "
             "M0.62 0.36 L0.88 0.62 L0.62 0.88 L0.36 0.62 Z")


def _synthesize_repeats(st: _LoadState,
                        staff_geo: dict[tuple, tuple[int, int | None, Rect]]
                        ) -> list[RenderedElement]:
    """One % symbol per repeated bar (ruling b — per measure), centered on
    the middle staff line, onset on the bar's downbeat. Verovio draws
    nothing for <measure-repeat> (empty <space>), so this is full
    synthesis in the slash shape (spikes/NOTES.md Phase 12)."""
    out: list[RenderedElement] = []
    glyph_bbox = path_bbox(_REPEAT_D)
    for region in st.prep.repeat_regions:
        info = next(p for p in st.prep.parts if p.part_id == region.part)
        for m in range(region.start_measure, region.stop_measure):
            # v1 limitation: repeat regions on the part's first staff
            page, system, staff_bbox = staff_geo[(region.part, m, 1)]
            staff_space = staff_bbox.h / 4
            cx = staff_bbox.x + staff_bbox.w / 2
            mid_y = staff_bbox.y + staff_bbox.h / 2
            tf = Affine(a=staff_space, d=staff_space, e=cx, f=mid_y)
            bbox = tf.apply_rect(glyph_bbox)
            identity = ElementIdentity(
                element_id=ElementId(f"{region.part}:m{m}:barrepeat"),
                kind=ElementKind.BAR_REPEAT,
                part=region.part, part_name=info.name,
                staff=1, voice=None, onset=st.measure_start[m],
            )
            out.append(RenderedElement(
                identity=identity, page=page, x=cx, y=mid_y,
                bbox=bbox, anchor=bbox.center,
                glyph=RenderPrimitive(paths=(
                    PathPrimitive(d=_REPEAT_D, transform=tf),)),
                system=system,
            ))
    return out
