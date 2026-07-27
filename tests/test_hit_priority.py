"""Hit-priority policy (M2.1) — pure, no Qt, no fixture.

Pins the total order the M2.0 census forced out
(spikes/hit_census.py, findings C/D): exactness first so a zero-area
stem cannot steal its own notehead's click, then layer tier so a
barline drawn across the staff beats the staff lines, then area, then
the id as a permutation-independent tail. Plus the public
measure-ordinal parse M5 will reuse.
"""

from __future__ import annotations

import itertools

from scoreanim.core.score.identity import ElementId, ElementKind
from scoreanim.core.selection import (HitCandidate, measure_ordinal_of, pick,
                                      tier_of)


def _c(eid: str, kind: ElementKind, area: float,
       exact: bool = True) -> HitCandidate:
    return HitCandidate(ElementId(eid), kind, area, exact)


# -- the roadmap's own rules -------------------------------------------

def test_smallest_area_wins() -> None:
    note = _c("P1:m1:s1:v1:note:0", ElementKind.NOTEHEAD, 215.1)
    staff = _c("P1:m1:s1:v0:staff_lines:0", ElementKind.STAFF_LINES, 32616.0)
    assert pick([note, staff]) == note.element_id


def test_notehead_beats_barline() -> None:
    note = _c("P1:m1:s1:v1:note:0", ElementKind.NOTEHEAD, 215.1)
    barline = _c("score:m1:barline:0", ElementKind.BARLINE, 13356.1)
    assert pick([note, barline]) == note.element_id


def test_bare_barline_is_selectable() -> None:
    """Scaffold IS selectable — barlines are M5's handle."""
    barline = _c("score:m1:barline:0", ElementKind.BARLINE, 13356.1)
    assert pick([barline]) == barline.element_id


def test_animated_ink_beats_scaffold_at_equal_area() -> None:
    dyn = _c("P1:m4:s1:v0:dynamic:0", ElementKind.DYNAMIC, 900.0)
    barline = _c("score:m4:barline:0", ElementKind.BARLINE, 900.0)
    assert pick([dyn, barline]) == dyn.element_id


def test_empty_candidate_list_is_a_deselect() -> None:
    assert pick([]) is None


def test_pick_is_permutation_independent() -> None:
    cands = [
        _c("P1:m1:s1:v1:note:0", ElementKind.NOTEHEAD, 215.1),
        _c("P1:m1:s1:v1:stem:0", ElementKind.STEM, 0.0, exact=False),
        _c("P1:m1:s1:v0:staff_lines:0", ElementKind.STAFF_LINES, 32616.0),
        _c("score:m1:barline:0", ElementKind.BARLINE, 13356.1),
    ]
    winners = {pick(order) for order in itertools.permutations(cands)}
    assert len(winners) == 1


def test_ties_on_every_key_resolve_by_id() -> None:
    a = _c("P1:m1:s1:v1:note:0", ElementKind.NOTEHEAD, 100.0)
    b = _c("P1:m1:s1:v1:note:1", ElementKind.NOTEHEAD, 100.0)
    assert pick([a, b]) == a.element_id
    assert pick([b, a]) == a.element_id


# -- census finding C: the stem trap -----------------------------------

def test_zero_area_stem_does_not_steal_its_noteheads_click() -> None:
    """A stem's authored Rect has w=0 -> area 0. Under area-alone it
    beats every notehead; clicking a note would select its stem. The
    click is inside the notehead's ink and only NEAR the stem, so
    exactness settles it (spikes/hit_census.py finding C)."""
    note = _c("P10:m1:s1:v1:note:0", ElementKind.NOTEHEAD, 161.6, exact=True)
    stem = _c("P10:m1:s1:v1:stem:0", ElementKind.STEM, 0.0, exact=False)
    assert pick([note, stem]) == note.element_id


def test_a_click_genuinely_on_the_stem_still_selects_the_stem() -> None:
    note = _c("P10:m1:s1:v1:note:0", ElementKind.NOTEHEAD, 161.6, exact=False)
    stem = _c("P10:m1:s1:v1:stem:0", ElementKind.STEM, 0.0, exact=True)
    assert pick([note, stem]) == stem.element_id


def test_exactness_outranks_a_much_smaller_tolerance_neighbour() -> None:
    hairpin = _c("P1:m10:s1:v0:hairpin:0", ElementKind.HAIRPIN, 6574.0,
                 exact=True)
    dynamic = _c("P1:m10:s1:v0:dynamic:0", ElementKind.DYNAMIC, 992.4,
                 exact=False)
    assert pick([hairpin, dynamic]) == hairpin.element_id


# -- census finding C: staff lines are the backdrop --------------------

def test_barline_beats_staff_lines_despite_being_larger() -> None:
    """A system barline's bbox spans the staves it joins, so it is
    LARGER than one staff's staff lines and both are scaffold — area
    alone would hand every barline click to the staff, leaving M5 with
    no handle (complex3 numbers)."""
    barline = _c("score:m1:barline:0", ElementKind.BARLINE, 15770.8)
    staff = _c("P11:m1:s1:v0:staff_lines:0", ElementKind.STAFF_LINES, 9984.1)
    assert pick([barline, staff]) == barline.element_id


def test_staff_lines_alone_deselect() -> None:
    """M2.8 ruling: the backdrop is not a selection winner. A click whose
    only ink is staff lines is a click on empty staff space, and empty
    staff space is paper — the same deselect the margin already gave.
    Exact or not: a rule that turned on sub-pixel aim would be worse than
    either answer."""
    staff = _c("P1:m1:s1:v0:staff_lines:0", ElementKind.STAFF_LINES, 9984.1)
    assert pick([staff]) is None
    assert pick([_c("P1:m1:s1:v0:staff_lines:0", ElementKind.STAFF_LINES,
                    9984.1, exact=False)]) is None


def test_backdrop_never_wins_even_over_a_worse_ranked_object() -> None:
    """The filter runs BEFORE the order, so an exact backdrop hit still
    loses to a merely-tolerated object — the object is the only
    candidate there is."""
    staff = _c("P1:m1:s1:v0:staff_lines:0", ElementKind.STAFF_LINES, 9984.1,
               exact=True)
    note = _c("P1:m1:s1:v1:note:0", ElementKind.NOTEHEAD, 161.6, exact=False)
    assert pick([staff, note]) == note.element_id


def test_selectability_is_a_table_not_a_kind_check() -> None:
    """Scaffold stays selectable — a barline is an object IN a measure
    and is M5's only handle (rule 13). Only the backdrop is excluded."""
    from scoreanim.core.selection import BACKDROP_KINDS, is_selectable

    assert not is_selectable(ElementKind.STAFF_LINES)
    for kind in (ElementKind.BARLINE, ElementKind.GROUP_SYMBOL,
                 ElementKind.SYSTEM_DIVIDER, ElementKind.NOTEHEAD,
                 ElementKind.TEXT):
        assert is_selectable(kind), kind
    assert {k for k in ElementKind if not is_selectable(k)} == BACKDROP_KINDS


def test_tier_table() -> None:
    assert tier_of(ElementKind.NOTEHEAD) == 0
    assert tier_of(ElementKind.SLUR) == 0
    assert tier_of(ElementKind.TEXT) == 0
    assert tier_of(ElementKind.BARLINE) == 1
    assert tier_of(ElementKind.GROUP_SYMBOL) == 1
    assert tier_of(ElementKind.SYSTEM_DIVIDER) == 1
    assert tier_of(ElementKind.STAFF_LINES) == 2


def test_inexact_backdrop_loses_to_inexact_ink() -> None:
    staff = _c("P1:m1:s1:v0:staff_lines:0", ElementKind.STAFF_LINES, 9984.1,
               exact=False)
    note = _c("P1:m1:s1:v1:note:0", ElementKind.NOTEHEAD, 161.6, exact=False)
    assert pick([staff, note]) == note.element_id


# -- measure_ordinal_of ------------------------------------------------

def test_measure_ordinal_of_per_staff_id() -> None:
    assert measure_ordinal_of(ElementId("P1:m1:s1:v1:note:0")) == 1
    assert measure_ordinal_of(ElementId("P14:m78:s2:v1:accidental:3")) == 78


def test_measure_ordinal_of_scaffold_id() -> None:
    assert measure_ordinal_of(ElementId("score:m3:barline:0")) == 3


def test_measure_ordinal_of_continuation_segment_is_the_start_measure() -> None:
    """A :seg id appends to its SOURCE's id, so the ordinal is where the
    spanner starts — the right answer for a broken slur."""
    assert measure_ordinal_of(
        ElementId("P1:m8:s1:v1:slur:0:seg1")) == 8


def test_measure_ordinal_of_system_and_page_ids_is_none() -> None:
    assert measure_ordinal_of(ElementId("score:sys2:grpsym:P1-P2")) is None
    assert measure_ordinal_of(ElementId("score:sys2:systemdivider:0")) is None
    assert measure_ordinal_of(ElementId("score:p1:text:0")) is None
