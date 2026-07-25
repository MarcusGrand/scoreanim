"""Hit-priority policy: which element does a click on the stage select?

POLICY LIVES HERE, never in the view. The UI collects candidates (walk
each hit item up to its ElementItem parent) and hands this module plain
data; everything about *choosing* among overlapping ink is decided by
the pure total order below, so it is testable headless with synthetic
lists and cannot drift into Qt (rule 1).

The roadmap's rule was "smallest bbox wins; animated ink beats scaffold
at equal size — but scaffold IS selectable (barlines are M5's handle)".
The M2.0 census (spikes/hit_census.py, 2026-07-25) measured that rule on
testscore and complex3 and found it picks the wrong element twice, so
the order carries two more keys. Both corrections are DATA — a tier
table and a boolean the caller measures — not branches on a kind name:

1. EXACTNESS first. A click is tested against a small tolerance rect
   (thin ink is unclickable at a bare point), so candidates arrive that
   the user did not actually touch. A stem's authored Rect has w = 0,
   hence area 0, so under area-alone a stem beats the notehead it hangs
   off and clicking a note selects its stem. Ranking ink that genuinely
   CONTAINS the click ahead of mere tolerance neighbours fixes it.

2. STAFF_LINES rank last. A system barline's bbox spans every staff it
   joins, so it is LARGER than one staff's staff lines (complex3:
   15771 vs 9984) — and both are scaffold, so "animated beats scaffold"
   cannot separate them. Area alone therefore hands every barline click
   to the staff, which would leave M5 with no handle. Staff lines are
   the backdrop every other element is drawn on top of; they rank last
   among equals and stay selectable when nothing else is under the
   cursor.

Measured effect (clicking elements on their own ink, complex3):
notehead 37 -> 74%, staff lines 20 -> 90%, hairpin 87 -> 100%, barline
96 -> 100%. Never worse than area-alone on any kind of either score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from scoreanim.core.animation.schedule import STATIC_KINDS
from scoreanim.core.score.identity import ElementId, ElementKind

# The backdrop layer: ink that underlies the whole staff and is exact
# almost everywhere on it. Its own tier so a barline drawn across it
# wins (finding 2 above). A set, not an `if kind is STAFF_LINES`, so the
# policy stays a table like STATIC_KINDS / TINTED_KINDS.
BACKDROP_KINDS = frozenset({ElementKind.STAFF_LINES})

_ANIMATED_TIER = 0        # notes, slurs, dynamics, texts — the ink
_SCAFFOLD_TIER = 1        # barlines, brackets, dividers (rule 6 scaffold)
_BACKDROP_TIER = 2        # staff lines

# The minted-id measure segment. Same shape as schedule.py's private
# _MEASURE_RE; this is the PUBLIC parse (M5 reads a barline's ordinal
# through it too), so it is spelled out here rather than borrowed.
_MEASURE_RE = re.compile(r":m(\d+):")


@dataclass(frozen=True)
class HitCandidate:
    """One element under the click, as the view measured it.

    ``area`` is the ENGRAVED bbox area (w * h in page units), not the
    Qt path bounds: it comes from Verovio and is therefore identical on
    every machine, while childrenBoundingRect() on text depends on the
    font engine. ``exact`` is True when the click point is inside the
    element's own ink, False when it only fell within the tolerance
    rect around it."""

    element_id: ElementId
    kind: ElementKind
    area: float
    exact: bool = False


def tier_of(kind: ElementKind) -> int:
    """Which layer this kind sits in: ink over scaffold over backdrop."""
    if kind in BACKDROP_KINDS:
        return _BACKDROP_TIER
    return _SCAFFOLD_TIER if kind in STATIC_KINDS else _ANIMATED_TIER


def sort_key(candidate: HitCandidate) -> tuple[bool, int, float, str]:
    """The total order. The element_id tail makes the pick
    permutation-independent: two candidates that tie on everything else
    resolve the same way whatever order the scene reported them in."""
    return (not candidate.exact,
            tier_of(candidate.kind),
            candidate.area,
            str(candidate.element_id))


def pick(candidates: Iterable[HitCandidate]) -> ElementId | None:
    """The winning element, or None for "nothing here" (a deselect)."""
    best: HitCandidate | None = None
    best_key: tuple[bool, int, float, str] | None = None
    for candidate in candidates:
        key = sort_key(candidate)
        if best_key is None or key < best_key:
            best, best_key = candidate, key
    return best.element_id if best is not None else None


def measure_ordinal_of(element_id: ElementId) -> int | None:
    """The 1-based document-order measure ordinal carried in a minted id,
    or None for ids that genuinely have no measure.

    ElementIdentity has no `measure` field, but the id grammar does:
    ``{part}:m{ord}:s{staff}:v{voice}:{kind}:{seq}`` for per-staff ink,
    ``score:m{ord}:{kind}:{seq}`` for scaffold, and a continuation
    segment appends ``:seg{k}`` to its source's id — so a broken
    spanner reports its START measure, which is the right answer for a
    spanner. System-scoped (``score:sys{n}:…``) and page-furniture
    (``score:p{n}:…``) ids have no measure and return None.

    The ordinal is NOT the printed number (adapter item 12): Dorico
    exports pickup bars as "X0", so printed numbers are neither unique
    nor consistent. Callers wanting the printed label look the ordinal
    up in the measure table."""
    match = _MEASURE_RE.search(str(element_id))
    return int(match.group(1)) if match else None
