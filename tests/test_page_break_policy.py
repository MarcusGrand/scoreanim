"""M6.4 — the page-break toggle policy and the coherence rule, headless.

The `tests/test_break_policy.py` shape, which is the
`tests/test_hit_priority.py` shape: pure core logic on hand-built inputs,
no engraving and no Qt. The real measure→page map this policy reads is
pinned end to end in `tests/test_page_breaks.py`; here the question is
only what the policy DOES with one.
"""
from __future__ import annotations

from scoreanim.core.editing import breaks as system_policy
from scoreanim.core.editing.break_coherence import contradicts, normalize
from scoreanim.core.editing.page_breaks import (LAST_MEASURE, NO_MEASURE,
                                                NO_SCORE, NO_SELECTION,
                                                NOT_A_BARLINE,
                                                PageBreakAction,
                                                contradicting_system_entries,
                                                page_starts, resolve,
                                                toggle_mode)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind)
from scoreanim.core.score.musicxml_prep import PageBreak, SystemBreak
from scoreanim.core.selection.context import Selection

# testscore's baseline: 5 systems of 4 on 3 pages starting at m1, m5, m13
SYSTEMS = {m: (m - 1) // 4 + 1 for m in range(1, 20)}
PAGES = {m: (1 if m < 5 else 2 if m < 13 else 3) for m in range(1, 20)}
PAGE_STARTS = {1, 5, 13}


def _barline(measure: int | None) -> Selection:
    """A selected barline. Measure-scoped ids carry an ordinal; the
    system-start (left) barline is page-scoped and carries none."""
    eid = (f"score:m{measure}:barline:0" if measure is not None
           else "score:p1:barline:0")
    return Selection(ElementIdentity(
        element_id=ElementId(eid), kind=ElementKind.BARLINE,
        part=None, part_name=None, staff=None, voice=None, onset=None))


def _notehead(measure: int) -> Selection:
    return Selection(ElementIdentity(
        element_id=ElementId(f"P1:m{measure}:s1:v1:note:0"),
        kind=ElementKind.NOTEHEAD, part=None, part_name=None,
        staff=1, voice=1, onset=0.0))


# ---------------------------------------------------------------------------
# the derivation
# ---------------------------------------------------------------------------

def test_page_starts_are_the_first_measure_of_each_page() -> None:
    assert page_starts(PAGES) == frozenset(PAGE_STARTS)
    assert page_starts({}) == frozenset()


# ---------------------------------------------------------------------------
# the three toggle branches (D5)
# ---------------------------------------------------------------------------

def test_toggle_forces_where_no_page_starts() -> None:
    assert toggle_mode(3, {}, PAGES) is PageBreak.FORCE


def test_toggle_suppresses_where_a_page_already_starts() -> None:
    assert toggle_mode(5, {}, PAGES) is PageBreak.SUPPRESS
    assert toggle_mode(13, {}, PAGES) is PageBreak.SUPPRESS


def test_toggle_clears_an_existing_override_whichever_way_it_points() -> None:
    """Press twice, nothing stored — which is what keeps the doc sparse
    and the gesture perfectly reversible."""
    assert toggle_mode(3, {3: PageBreak.FORCE}, PAGES) is None
    assert toggle_mode(5, {5: PageBreak.SUPPRESS}, PAGES) is None


def test_the_toggle_reads_the_LAYOUT_not_the_encoded_break_set() -> None:
    """D5, and it matters more for pages than it did for systems: after
    a never-clip repagination the page a measure starts is the app's
    choice, not the file's. Here m9 starts a page in the CURRENT layout
    though testscore encodes none there — the toggle must offer to
    remove it, not to add a second one."""
    repaginated = {m: (1 if m < 9 else 2) for m in range(1, 20)}
    assert toggle_mode(9, {}, repaginated) is PageBreak.SUPPRESS
    assert toggle_mode(5, {}, repaginated) is PageBreak.FORCE


# ---------------------------------------------------------------------------
# the five disable cases, each naming WHY (D4 + the standing rider)
# ---------------------------------------------------------------------------

def test_no_score_disables() -> None:
    action = resolve(_barline(4), {}, {}, {})
    assert not action.enabled and action.reason == NO_SCORE


def test_no_selection_disables() -> None:
    action = resolve(None, {}, {}, PAGES)
    assert not action.enabled and action.reason == NO_SELECTION


def test_a_non_barline_disables() -> None:
    action = resolve(_notehead(4), {}, {}, PAGES)
    assert not action.enabled and action.reason == NOT_A_BARLINE


def test_a_system_start_barline_carries_no_measure_and_disables() -> None:
    action = resolve(_barline(None), {}, {}, PAGES)
    assert not action.enabled and action.reason == NO_MEASURE


def test_the_last_measure_disables() -> None:
    action = resolve(_barline(19), {}, {}, PAGES)
    assert not action.enabled and action.reason == LAST_MEASURE


def test_every_disable_reason_is_distinct_and_says_pages() -> None:
    reasons = {NO_SCORE, NO_SELECTION, NOT_A_BARLINE, NO_MEASURE,
               LAST_MEASURE}
    assert len(reasons) == 5
    assert "page break" in NO_SELECTION and "Page breaks" in NOT_A_BARLINE
    assert "page" in LAST_MEASURE


# ---------------------------------------------------------------------------
# the N+1 arithmetic (D2), and the round trip
# ---------------------------------------------------------------------------

def test_the_target_is_the_measure_that_would_start_the_page() -> None:
    """Clicking measure 4's right barline means "the break falls after
    measure 4", and the key is 5."""
    assert resolve(_barline(4), {}, {}, PAGES) == PageBreakAction(
        ordinal=5, mode=PageBreak.SUPPRESS)
    assert resolve(_barline(2), {}, {}, PAGES) == PageBreakAction(
        ordinal=3, mode=PageBreak.FORCE)


def test_force_then_toggle_returns_the_document_to_where_it_started() -> None:
    first = resolve(_barline(2), {}, {}, PAGES)
    assert first.mode is PageBreak.FORCE
    stored = {first.ordinal: first.mode}
    second = resolve(_barline(2), stored, {}, PAGES)
    assert second.ordinal == first.ordinal and second.mode is None


# ---------------------------------------------------------------------------
# the coherence rule (D3), cell by cell against §3.4's table
# ---------------------------------------------------------------------------

def test_exactly_one_pair_contradicts() -> None:
    pairs = [(s, p) for s in (None, SystemBreak.FORCE, SystemBreak.SUPPRESS)
             for p in (None, PageBreak.FORCE, PageBreak.SUPPRESS)]
    bad = [(s, p) for s, p in pairs if contradicts(s, p)]
    assert bad == [(SystemBreak.SUPPRESS, PageBreak.FORCE)]


def test_normalize_passes_every_coherent_pair_through_untouched() -> None:
    for system, page in [
        (None, None),
        (None, PageBreak.FORCE),
        (None, PageBreak.SUPPRESS),
        (SystemBreak.FORCE, None),
        (SystemBreak.FORCE, PageBreak.FORCE),          # §3.4 row 1
        (SystemBreak.FORCE, PageBreak.SUPPRESS),       # §3.4 row 3
        (SystemBreak.SUPPRESS, None),
        (SystemBreak.SUPPRESS, PageBreak.SUPPRESS),    # §3.4 row 4
    ]:
        assert normalize(system, page) == (system, page)


def test_normalize_drops_the_system_suppress_a_page_force_overrules() -> None:
    """§3.4 row 2. Dropping rather than flipping is what keeps the doc
    sparse: toggling the page break off later leaves nothing behind."""
    assert normalize(SystemBreak.SUPPRESS, PageBreak.FORCE) == (
        None, PageBreak.FORCE)


# ---------------------------------------------------------------------------
# prevention: the toggles never author the incoherent pair (D3, part 3)
# ---------------------------------------------------------------------------

def test_a_page_force_clears_a_contradicting_system_suppress() -> None:
    action = resolve(_barline(8), {}, {9: SystemBreak.SUPPRESS},
                     {**PAGES, 9: 2})
    assert action.ordinal == 9 and action.mode is PageBreak.FORCE
    assert action.also_system == ((9, None),)


def test_a_page_gesture_leaves_a_coherent_system_override_alone() -> None:
    for stored in (SystemBreak.FORCE, SystemBreak.SUPPRESS):
        action = resolve(_barline(4), {}, {5: stored}, PAGES)
        assert action.mode is PageBreak.SUPPRESS     # coherent with both
        assert action.also_system == ()
    forced = resolve(_barline(8), {}, {9: SystemBreak.FORCE}, PAGES)
    assert forced.mode is PageBreak.FORCE and forced.also_system == ()


def test_a_page_gesture_with_no_system_override_carries_nothing() -> None:
    assert resolve(_barline(2), {}, {}, PAGES).also_system == ()


def test_the_system_toggle_clears_a_contradicting_page_force() -> None:
    """The mirror. The page FORCE is what goes, not the system SUPPRESS
    the user just pressed — otherwise the toggle would throw away the
    gesture that invoked it."""
    action = system_policy.resolve(_barline(8), {}, SYSTEMS,
                                   {9: PageBreak.FORCE})
    assert action.ordinal == 9 and action.mode is SystemBreak.SUPPRESS
    assert action.also_page == ((9, None),)


def test_the_system_toggle_leaves_a_coherent_page_override_alone() -> None:
    action = system_policy.resolve(_barline(8), {}, SYSTEMS,
                                   {9: PageBreak.SUPPRESS})
    assert action.mode is SystemBreak.SUPPRESS and action.also_page == ()
    forced = system_policy.resolve(_barline(2), {}, SYSTEMS,
                                   {3: PageBreak.FORCE})
    assert forced.mode is SystemBreak.FORCE and forced.also_page == ()


def test_the_system_toggle_without_a_page_map_behaves_as_it_did_in_M5() -> None:
    """The parameter is additive: every M5 call site is unchanged."""
    assert system_policy.resolve(_barline(8), {}, SYSTEMS) == \
        system_policy.BreakAction(ordinal=9, mode=SystemBreak.SUPPRESS)


def test_move_to_previous_system_clears_contradictions_at_both_ordinals() -> None:
    """M5.7's composed gesture writes up to two ordinals, so it checks
    both — still one command, still one undo entry (rule 8)."""
    action = system_policy.resolve_move_up(
        _notehead(10), {}, SYSTEMS,
        {9: PageBreak.FORCE, 11: PageBreak.FORCE})
    assert action.ordinal == 9 and action.mode is SystemBreak.SUPPRESS
    assert action.also == ((11, SystemBreak.FORCE),)
    # only the SUPPRESS half contradicts; the FORCE half is coherent
    assert action.also_page == ((9, None),)


def test_contradicting_system_entries_is_a_no_op_without_a_stored_pair() -> None:
    assert contradicting_system_entries(5, PageBreak.FORCE, {}) == ()
    assert contradicting_system_entries(5, None,
                                        {5: SystemBreak.SUPPRESS}) == ()
