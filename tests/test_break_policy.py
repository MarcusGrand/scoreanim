"""M5.3 — the break-toggle policy, headless on synthetic maps.

The `tests/test_hit_priority.py` shape: pure core logic exercised on
hand-built inputs, no engraving and no Qt. The real measure→system map
this policy reads is pinned end to end in `tests/test_system_breaks.py`;
here the question is only what the policy DOES with one.
"""
from __future__ import annotations

from scoreanim.core.editing.breaks import (LAST_MEASURE, NO_MEASURE,
                                           NO_SCORE, NO_SELECTION,
                                           NOT_A_BARLINE, BreakAction,
                                           resolve, system_starts,
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
    assert BreakAction(ordinal=4, mode=SystemBreak.FORCE).enabled
