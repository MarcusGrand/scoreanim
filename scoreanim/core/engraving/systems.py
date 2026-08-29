"""Per-system band geometry over a Layout (Phase 7.3) — pure, no Qt.

System-at-a-time presentation consumes the existing Layout: every
element already carries its score-wide system index (engraving-derived,
like page), so a system's band is just the union bbox of its elements,
widened to the full page width. Derived data — computed on demand,
never persisted (rule 5).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

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


# How much air the systems-mode frame leaves above and below the tallest
# system, as a fraction of that system's own height. Marcus's call
# (2026-08-30): 6 % is about 91 page units on testscore, which is the
# same gap the engraver itself leaves between two systems, and being a
# fraction it looks the same on a big orchestral page.
SYSTEM_FRAME_PAD = 0.06


@dataclass(frozen=True)
class SystemsFrame:
    """The one fixed window systems mode shows every system in.

    Systems mode is a piece of glass the systems are placed into, not a
    camera moving over the paper (docs/SYSTEMS_MODE_REWORK.md). So the
    frame is computed once per load and never changes: page width, so
    systems keep the page margins they were engraved with and stay
    left-aligned with each other, and one height that the tallest system
    fits in with room to spare. Every system is then centred in it, and
    a system with fewer staves simply has more air around it.

    Derived from the Layout, re-computed on every load, never stored
    (rule 5)."""

    width: float
    height: float

    def rect_for(self, band: Rect) -> Rect:
        """Where the frame sits, in page coordinates, so that `band` is
        vertically centred in it. x is the page's own left edge, so the
        system's horizontal position is exactly where it was engraved."""
        return Rect(0.0, band.center.y - self.height / 2,
                    self.width, self.height)


def systems_frame(bands: tuple[SystemBand, ...],
                  pad: float = SYSTEM_FRAME_PAD) -> SystemsFrame | None:
    """The constant systems-mode frame for one load: page width by
    tallest band plus `pad` of that height above and below.

    None when there are no systems to frame — an empty layout, which the
    view reads as "no frame, behave as before"."""
    if not bands:
        return None
    tallest = max(b.rect.h for b in bands)
    return SystemsFrame(width=max(b.rect.w for b in bands),
                        height=tallest * (1.0 + 2.0 * pad))


def page_of_measure(bands: tuple[SystemBand, ...],
                    system_of_measure: Mapping[int, int]) -> dict[int, int]:
    """Measure ordinal → 1-based page, derived from data every load
    already produces (M6, §1.2). The page twin of `system_of_measure`
    needs NO adapter change and no new `EngravedScore` field: a band
    knows its page, a measure knows its system, and that composes.

    Derived on demand, never stored (rule 5) — the page a measure lands
    on is a consequence of the engraving, not intent."""
    page_by_system = {b.system: b.page for b in bands}
    return {measure: page_by_system[system]
            for measure, system in system_of_measure.items()
            if system in page_by_system}


def page_starts(page_of_measure: Mapping[int, int]) -> frozenset[int]:
    """The measure ordinals that START a page — the set a page-break
    override map is a delta on, and what D5's toggle reads to decide
    between suppressing and forcing."""
    first: dict[int, int] = {}
    for measure, page in page_of_measure.items():
        if measure < first.get(page, 1 << 30):
            first[page] = measure
    return frozenset(first.values())


def plan_page_breaks(bands: tuple[SystemBand, ...], page_height: float,
                     first_measure_by_system: Mapping[int, int],
                     forced: frozenset[int] | set[int] = frozenset(),
                     ) -> tuple[int, ...]:
    """Greedy repagination plan (Phase 10R, rule-7 amendment): measure
    numbers whose systems should start a NEW page so that no system
    overflows the page. Used when the encoded page breaks cannot hold
    their systems (e.g. Dorico breaks computed assuming hidden staves).
    Margins are derived from the measured first pass: top margin = the
    smallest first-of-page band top, inter-system gap = the median
    same-page gap. A 2% safety pad absorbs the placement drift between
    the measured pass and the re-engraved one (observed ~0.5% on the
    Phase 10R fixture — never-clip beats an occasional extra page).
    Pure and deterministic — the plan is derived data, re-computed on
    every load, never stored (rule 5).

    `forced` is the user's authored page intent (M6, D1), and this is the
    ONE place it meets never-clip. `_repaginate` strips every encoded
    page break before asserting this plan, so a FORCE written at the prep
    seam is destroyed exactly when the guard engages — measured, and
    measured to fail RARELY and SILENTLY, which is the worst failure
    shape available (§3.2 B1/B3). Layering intent over the plan instead
    would put the user above never-clip, which rule 7 does not permit. So
    the FORCE is an INPUT: forced ordinals join the plan, and the planner
    still owns what it packs around them.

    A forced ordinal is honored only where it is a real system start.
    That is not a restriction in practice — the seam has already written
    `new-system="yes"` there, so the measured pass that produced these
    bands already breaks the system — but it keeps the plan well-formed
    if an override is stale (rule 5) or names a measure that no longer
    exists.

    **A SUPPRESS is deliberately NOT a parameter**, and that is the
    ruling ("a suppressed one is overridden, and warned, whenever
    honoring it would clip ink"), not an omission. The suppression is
    applied at the prep seam, so the `bands` measured here ALREADY honor
    it: this planner is looking at the piled-up layout the suppression
    produced and deciding, from scratch, where pages must fall. Every
    break it emits is one it needed. Subtracting the suppressed ordinals
    from that plan would therefore remove breaks that never-clip
    requires, and measurement says the cost is real — bigband1 with its
    two page breaks suppressed drops from a 4-page plan to a 2-page one
    and is then rescued by scale-to-fit at **40%**, and testscore at
    **51%**. Legal, unclipped, and a much worse score than the extra
    page the planner asked for.

    So a suppression is honored wherever the planner does not need that
    break — which is every case the spike measured, since there
    `plan ∩ suppressed` was empty — and overruled where it does, with
    the caller reporting exactly that (D8's `page-break-repaginated`).
    The page count stays owned (rule 7)."""
    if not bands:
        return ()
    limit = page_height * 0.98
    tops = [b.rect.y for b in bands
            if b.system == min(x.system for x in bands if x.page == b.page)]
    top_margin = max(min(tops), 0.0)
    gaps = sorted(
        after.rect.y - (before.rect.y + before.rect.h)
        for before, after in zip(bands, bands[1:])
        if before.page == after.page
        and after.rect.y > before.rect.y + before.rect.h)
    gap = gaps[len(gaps) // 2] if gaps else top_margin
    breaks: list[int] = []
    y = top_margin
    for i, band in enumerate(bands):
        h = band.rect.h
        if i > 0 and y + h > limit:
            breaks.append(first_measure_by_system[band.system])
            y = top_margin
        y += h + gap
    if not forced:
        return tuple(breaks)
    starts = set(first_measure_by_system.values())
    return tuple(sorted(set(breaks) | (set(forced) & starts)))


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
