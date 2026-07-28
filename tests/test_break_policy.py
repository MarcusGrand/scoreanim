"""M5.3 — the break-toggle policy, headless on synthetic maps.

The `tests/test_hit_priority.py` shape: pure core logic exercised on
hand-built inputs, no engraving and no Qt. The real measure→system map
this policy reads is pinned end to end in `tests/test_system_breaks.py`;
here the question is only what the policy DOES with one.
"""
from __future__ import annotations

from scoreanim.core.editing.breaks import (FIRST_SYSTEM, LAST_MEASURE,
                                           MOVE_NO_MEASURE,
                                           MOVE_NO_SELECTION, NO_EFFECT,
                                           NO_MEASURE, NO_SCORE,
                                           NO_SELECTION, NOT_A_BARLINE,
                                           UNKNOWN_MEASURE, BreakAction,
                                           move_up_entries, resolve,
                                           resolve_move_up, system_starts,
                                           toggle_mode)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind)
from scoreanim.core.score.musicxml_prep import SystemBreak
from scoreanim.core.selection.context import Selection

# testscore's baseline: 5 systems of 4, 4, 4, 4, 3 measures (spike §3.1)
SYSTEMS = {m: (m - 1) // 4 + 1 for m in range(1, 20)}
STARTS = {1, 5, 9, 13, 17}


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


def test_system_starts_are_the_first_measure_of_each_system() -> None:
    assert system_starts(SYSTEMS) == STARTS
    assert system_starts({}) == frozenset()


# ---------------------------------------------------------------------------
# D2 — "here" means after this measure, and the key is the next one
# ---------------------------------------------------------------------------

def test_the_target_is_the_measure_that_would_start_the_system() -> None:
    """Clicking m3's (right) barline means "break after m3", which is
    "m4 starts a system" — the key `<print new-system>` and _repaginate
    both already use."""
    action = resolve(_barline(3), {}, SYSTEMS)
    assert action.enabled
    assert action.ordinal == 4
    assert action.mode is SystemBreak.FORCE


# ---------------------------------------------------------------------------
# D4 — the three-step toggle sense
# ---------------------------------------------------------------------------

def test_toggle_forces_where_no_system_starts() -> None:
    assert toggle_mode(4, {}, SYSTEMS) is SystemBreak.FORCE


def test_toggle_suppresses_where_a_system_already_starts() -> None:
    """Read off the CURRENT layout, not the encoded break set."""
    for target in sorted(STARTS):
        assert toggle_mode(target, {}, SYSTEMS) is SystemBreak.SUPPRESS


def test_an_existing_override_clears_first() -> None:
    """Step 1 wins over both others, in both directions — which is what
    makes the gesture reversible and keeps the doc sparse."""
    assert toggle_mode(4, {4: SystemBreak.FORCE}, SYSTEMS) is None
    assert toggle_mode(9, {9: SystemBreak.SUPPRESS}, SYSTEMS) is None
    # and an override on a DIFFERENT measure does not interfere
    assert toggle_mode(4, {9: SystemBreak.SUPPRESS}, SYSTEMS) \
        is SystemBreak.FORCE


def test_force_then_toggle_again_returns_to_the_original_document() -> None:
    """The round-trip the brief asks for, as the UI would run it: the
    policy's own output fed back through the command."""
    from scoreanim.core.project import ProjectDoc, SetSystemBreak

    doc = ProjectDoc()
    first = resolve(_barline(3), doc.system_break_overrides, SYSTEMS)
    assert first.mode is SystemBreak.FORCE
    forced = SetSystemBreak(first.ordinal, first.mode).apply(doc)
    assert forced.system_break_overrides == {4: SystemBreak.FORCE}

    # the layout now starts a system at m4; toggling the same barline
    # again clears the override rather than writing SUPPRESS
    after = {m: (1 if m <= 2 else SYSTEMS[m] + 1) for m in SYSTEMS}
    second = resolve(_barline(3), forced.system_break_overrides, after)
    assert second.ordinal == 4 and second.mode is None
    assert SetSystemBreak(second.ordinal, second.mode).apply(forced) == doc


# ---------------------------------------------------------------------------
# the disable cases — each naming why (D1 rider)
# ---------------------------------------------------------------------------

def test_disabled_with_nothing_selected() -> None:
    action = resolve(None, {}, SYSTEMS)
    assert not action.enabled and action.reason == NO_SELECTION
    assert action.ordinal is None


def test_disabled_with_no_score_loaded() -> None:
    assert resolve(_barline(3), {}, {}).reason == NO_SCORE


def test_disabled_on_a_system_start_barline() -> None:
    """D3: the page-scoped left barline carries no measure. The Selection
    panel already shows "—" for it, so a disabled action is consistent
    with what the user is being told."""
    action = resolve(_barline(None), {}, SYSTEMS)
    assert not action.enabled and action.reason == NO_MEASURE


def test_disabled_on_the_last_measures_barline() -> None:
    """D6: there is no music after it to start a system. Note the case
    this does NOT cover — forcing a break AT the last measure, targeted
    from m18's barline, stays allowed."""
    assert resolve(_barline(19), {}, SYSTEMS).reason == LAST_MEASURE
    allowed = resolve(_barline(18), {}, SYSTEMS)
    assert allowed.enabled and allowed.ordinal == 19


def test_disabled_on_a_stale_ordinal_past_the_end() -> None:
    assert resolve(_barline(40), {}, SYSTEMS).reason == LAST_MEASURE


def test_disabled_on_anything_that_is_not_a_barline() -> None:
    """Rule 13 names the barline as M5's only handle: a notehead sits in
    a measure but not at a break position."""
    action = resolve(_notehead(3), {}, SYSTEMS)
    assert not action.enabled and action.reason == NOT_A_BARLINE


def test_every_disabled_reason_is_a_sentence_for_the_status_bar() -> None:
    for reason in (NO_SELECTION, NOT_A_BARLINE, NO_MEASURE, LAST_MEASURE,
                   NO_SCORE):
        assert reason and reason[0].isupper() and not reason.endswith(".")


def test_break_action_defaults_to_enabled() -> None:
    action = BreakAction(ordinal=4, mode=SystemBreak.FORCE)
    assert action.enabled and action.also == ()


# ---------------------------------------------------------------------------
# M5.7 — move to previous system (D11: the entry set)
# ---------------------------------------------------------------------------

def test_move_up_suppresses_this_system_and_forces_the_remainder() -> None:
    """The composition, on the row measured in brief §M5.7.2: moving m6
    up merges system 2 into system 1 and splits m7-8 off as their own."""
    assert move_up_entries(6, {}, SYSTEMS) == ((5, SystemBreak.SUPPRESS),
                                               (7, SystemBreak.FORCE))


def test_move_up_from_a_systems_first_measure_is_allowed() -> None:
    """Moving a system START up one system is the commonest use, not a
    disable case: m5 goes up alone and m6-8 stay behind."""
    assert move_up_entries(5, {}, SYSTEMS) == ((5, SystemBreak.SUPPRESS),
                                               (6, SystemBreak.FORCE))
    assert resolve_move_up(_notehead(5), {}, SYSTEMS).enabled


def test_move_up_of_a_systems_last_measure_writes_only_the_merge() -> None:
    """No remainder, so no split half — and writing one anyway would
    rewrite an encoded break with itself and trip D10's inert warning
    for a gesture that worked (measured, §M5.7.2 M1)."""
    assert move_up_entries(8, {}, SYSTEMS) == ((5, SystemBreak.SUPPRESS),)


def test_move_up_of_the_scores_last_measure_writes_only_the_merge() -> None:
    """m19 is the last measure of the score, so N+1 is not in the layout
    at all — the same 'no remainder' branch, not a special case."""
    assert move_up_entries(19, {}, SYSTEMS) == ((17, SystemBreak.SUPPRESS),)


def test_move_up_clears_a_force_rather_than_suppressing_over_it() -> None:
    """When the break at S is the user's own FORCE, clearing it removes
    the break AND keeps the doc sparse; writing SUPPRESS would leave an
    entry the seam has nothing to suppress with (inert, and warned)."""
    assert move_up_entries(6, {5: SystemBreak.FORCE}, SYSTEMS) \
        == ((5, None), (7, SystemBreak.FORCE))


def test_move_up_clears_a_suppression_rather_than_forcing_over_it() -> None:
    """Symmetrically on the split half: restoring the encoded break is
    enough to make N+1 start a system again."""
    assert move_up_entries(6, {7: SystemBreak.SUPPRESS}, SYSTEMS) \
        == ((5, SystemBreak.SUPPRESS), (7, None))


def test_move_up_drops_an_entry_the_document_already_holds() -> None:
    """Defensive (§M5.7.2 M2 says break-respect does not produce it):
    a system starting where a SUPPRESS override already sits."""
    assert move_up_entries(6, {5: SystemBreak.SUPPRESS}, SYSTEMS) \
        == ((7, SystemBreak.FORCE),)


def test_move_up_is_one_gesture_over_the_two_primitives() -> None:
    """The whole point of the composition: what it writes is exactly what
    two plain toggles would have written, in one entry."""
    action = resolve_move_up(_notehead(6), {}, SYSTEMS)
    assert action.enabled
    assert action.ordinal == 5 and action.mode is SystemBreak.SUPPRESS
    assert action.also == ((7, SystemBreak.FORCE),)
    # the merge half is the LOWEST ordinal, which is what the view
    # re-anchors to (D14)
    assert action.ordinal == min(o for o, _ in
                                 ((action.ordinal, action.mode),
                                  *action.also))


def test_move_up_reads_any_object_not_just_a_barline() -> None:
    """Rule 13: selecting an object carries its measure. The barline is
    the handle for the raw toggle only."""
    for selection in (_notehead(6), _barline(6)):
        action = resolve_move_up(selection, {}, SYSTEMS)
        assert action.enabled and action.ordinal == 5


def test_move_up_applies_as_a_single_command() -> None:
    """End of the policy's contract: BreakAction's three fields ARE
    SetSystemBreak's three arguments."""
    from scoreanim.core.project import (ProjectDoc, SetSystemBreak,
                                        UndoStack)

    doc = ProjectDoc()
    action = resolve_move_up(_notehead(6), doc.system_break_overrides,
                             SYSTEMS)
    stack = UndoStack()
    moved = stack.execute(
        SetSystemBreak(action.ordinal, action.mode, action.also), doc)
    assert moved.system_break_overrides == {5: SystemBreak.SUPPRESS,
                                            7: SystemBreak.FORCE}
    assert stack.undo() == doc                   # ONE undo, both halves


# -- the disable cases, each naming why (D1 rider) --------------------------

def test_move_up_disabled_in_the_first_system() -> None:
    for measure in (1, 2, 3, 4):
        assert resolve_move_up(_notehead(measure), {}, SYSTEMS).reason \
            == FIRST_SYSTEM


def test_move_up_disabled_with_nothing_selected_or_no_score() -> None:
    assert resolve_move_up(None, {}, SYSTEMS).reason == MOVE_NO_SELECTION
    assert resolve_move_up(_notehead(6), {}, {}).reason == NO_SCORE


def test_move_up_disabled_for_an_object_carrying_no_measure() -> None:
    assert resolve_move_up(_barline(None), {}, SYSTEMS).reason \
        == MOVE_NO_MEASURE


def test_move_up_disabled_for_a_measure_the_layout_lacks() -> None:
    assert resolve_move_up(_notehead(40), {}, SYSTEMS).reason \
        == UNKNOWN_MEASURE


def test_move_up_disabled_when_it_would_write_nothing() -> None:
    """Both halves already in the document — unreachable in practice,
    disabled rather than half-firing if it ever is not."""
    one_system = {m: 1 for m in range(1, 5)}
    one_system.update({m: 2 for m in range(5, 9)})
    assert resolve_move_up(_notehead(8), {5: SystemBreak.SUPPRESS},
                           one_system).reason == NO_EFFECT


def test_every_move_up_reason_is_a_sentence_for_the_status_bar() -> None:
    for reason in (MOVE_NO_SELECTION, MOVE_NO_MEASURE, FIRST_SYSTEM,
                   UNKNOWN_MEASURE, NO_EFFECT):
        assert reason and reason[0].isupper() and not reason.endswith(".")
