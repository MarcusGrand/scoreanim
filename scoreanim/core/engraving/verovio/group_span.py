"""Which staves a group symbol (bracket/brace) spans, geometrically.

Split out of identity.py (2026-07-29) so the invariant is one small pure
function, testable headless on synthetic staff-center maps — no Verovio
load needed to pin it. identity.py turns the staff span this returns
into a part span via prep.part_for_staff.
"""

from __future__ import annotations

from collections.abc import Mapping

from scoreanim.core.engraving.types import Rect


def covered_staves(centers: Mapping[int, float], bbox: Rect) -> list[int]:
    """The staff numbers a group symbol's bbox spans, in order.

    `centers` is the system's staff y-centers, keyed by staff number —
    only the staves actually DRAWN on this system are in it.

    Contiguity is measured against those VISIBLE staves, not against the
    integers between the ends. Hide-empty-staves (rule 7(b)) drops a
    staff that is empty for a whole system, so a strings bracket
    legitimately covers [7, 10] on a system where Violin II and Viola
    are hidden — that is a well-formed bracket, not a corrupt one.
    Requiring [7, 8, 9, 10] there raised mid-load and, because the
    re-engrave was unguarded, the bracket simply never appeared.

    Raises ValueError when the symbol covers no staff at all, or skips a
    staff that IS drawn on this system (a genuinely torn span).
    """
    visible = sorted(centers)
    covered = sorted(n for n, cy in centers.items()
                     if bbox.y <= cy <= bbox.y + bbox.h)
    if not covered:
        raise ValueError("group symbol spans no staff")
    start = visible.index(covered[0])
    if visible[start:start + len(covered)] != covered:
        raise ValueError(
            f"group symbol spans staves {covered} — expected a contiguous "
            f"run of the staves visible on this system, {visible}")
    return covered


__all__ = ["covered_staves"]
