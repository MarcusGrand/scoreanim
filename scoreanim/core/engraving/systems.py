"""Per-system band geometry over a Layout (Phase 7.3) — pure, no Qt.

System-at-a-time presentation consumes the existing Layout: every
element already carries its score-wide system index (engraving-derived,
like page), so a system's band is just the union bbox of its elements,
widened to the full page width. Derived data — computed on demand,
never persisted (rule 5).
"""
from __future__ import annotations

from dataclasses import dataclass

from scoreanim.core.engraving.types import Layout, Rect


@dataclass(frozen=True)
class SystemBand:
    system: int          # 1-based, score-wide document order
    page: int            # 1-based
    rect: Rect           # full page width; y-span = union of element bboxes


def system_bands(layout: Layout) -> tuple[SystemBand, ...]:
    """One band per system index present in the layout, sorted by
    system. Elements outside any system (page-header texts) are
    skipped. Exact y-union, no padding: element bboxes already cover
    overhanging ink (verified on the fixture at scoping); x spans the
    full page so left-margin scaffold (labels, brackets) is always in
    frame."""
    hulls: dict[int, Rect] = {}
    pages: dict[int, int] = {}
    for el in layout.elements:
        if el.system is None:
            continue
        seen = hulls.get(el.system)
        hulls[el.system] = el.bbox if seen is None else seen.union(el.bbox)
        page = pages.setdefault(el.system, el.page)
        if page != el.page:
            raise ValueError(f"system {el.system} spans pages "
                             f"{page} and {el.page}")
    bands = []
    for system in sorted(hulls):
        geo = layout.pages[pages[system] - 1]
        hull = hulls[system]
        bands.append(SystemBand(
            system=system, page=pages[system],
            rect=Rect(0.0, hull.y, geo.width, hull.h)))
    return tuple(bands)


def centered_fit(inner_w: float, inner_h: float,
                 outer_w: float, outer_h: float) -> Rect:
    """The rect (in outer coordinates) that scales inner to fit WITHIN
    outer preserving inner's aspect, centered on both axes — the ruled
    system-mode export composite, and the shape fitInView produces
    live."""
    if inner_w <= 0 or inner_h <= 0 or outer_w <= 0 or outer_h <= 0:
        raise ValueError(f"bad fit {inner_w}x{inner_h} in "
                         f"{outer_w}x{outer_h}")
    scale = min(outer_w / inner_w, outer_h / inner_h)
    w = inner_w * scale
    h = inner_h * scale
    return Rect((outer_w - w) / 2, (outer_h - h) / 2, w, h)
