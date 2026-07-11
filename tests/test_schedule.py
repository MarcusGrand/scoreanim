"""Trigger schedule on the real fixture: tie gating, graces, groups, pages."""
from __future__ import annotations

from collections import defaultdict

import pytest

from scoreanim.core.animation import build_trigger_schedule, is_animated
from scoreanim.core.animation.schedule import _pitch_key, _q
from scoreanim.core.score.identity import ElementKind


@pytest.fixture(scope="module")
def schedule(engraved, join_mapping):
    return build_trigger_schedule(engraved.layout, join_mapping)


@pytest.fixture(scope="module")
def identities(engraved):
    return {el.identity.element_id: el.identity
            for el in engraved.layout.elements}


def test_sorted_and_deterministic(engraved, join_mapping, schedule) -> None:
    assert list(schedule.beat_values) == sorted(schedule.beat_values)
    again = build_trigger_schedule(engraved.layout, join_mapping)
    assert again == schedule


def test_all_slashes_scheduled_on_their_beats(schedule, identities) -> None:
    slashes = [eid for eid, ident in identities.items()
               if ident.kind is ElementKind.SLASH]
    assert len(slashes) == 52
    for eid in slashes:
        assert schedule.beats_by_element[eid] == identities[eid].onset


def test_tie_stops_never_retrigger(schedule, join_mapping) -> None:
    """All 58 stop + 6 continue noteheads fire before their notated onset."""
    gated = {eid: n for eid, n in join_mapping.items()
             if n.tie in ("stop", "continue")}
    assert len(gated) == 64
    for eid, note in gated.items():
        assert schedule.beats_by_element[eid] < note.onset, eid


def test_fresh_noteheads_fire_at_own_onset(schedule, join_mapping,
                                           identities) -> None:
    for eid, note in join_mapping.items():
        if note.tie in ("stop", "continue"):
            continue
        expected = identities[eid].onset if note.grace else note.onset
        assert schedule.beats_by_element[eid] == expected, eid


def test_tied_triggers_are_start_onsets(schedule, join_mapping) -> None:
    """Every gated notehead's trigger is the onset of an actual tie-start
    earlier in its (part, staff, pitch) chain — and chains with
    'continue' links propagate THROUGH them to the true start."""
    chains = defaultdict(list)
    for eid, note in join_mapping.items():
        chains[(note.part, note.staff, _pitch_key(note))].append(note)
    start_onsets = {
        key: {n.onset for n in notes if n.tie == "start"}
        for key, notes in chains.items()}
    continues_passed = 0
    for eid, note in join_mapping.items():
        if note.tie not in ("stop", "continue"):
            continue
        key = (note.part, note.staff, _pitch_key(note))
        trigger = schedule.beats_by_element[eid]
        assert trigger in start_onsets[key], eid
        # multi-link: a 'continue' sits strictly between trigger and onset
        if any(n.tie == "continue" and trigger < n.onset < note.onset
               for n in chains[key]):
            continues_passed += 1
    assert continues_passed > 0        # fixture has 6 'continue' links


def test_hihat_tie_across_voice_relabeling(schedule) -> None:
    """m18→19 drum tie: the start is in an implicit voice (label None),
    the stop in voice '5' — the chain must still connect (this is why
    the chain key excludes the per-measure voice label)."""
    assert schedule.beats_by_element["P7:m19:s1:v5:note:0"] == 65.5


def test_graces_fire_just_before_the_beat(schedule, join_mapping,
                                          identities) -> None:
    graces = {eid: n for eid, n in join_mapping.items() if n.grace}
    assert len(graces) == 3
    for eid, note in graces.items():
        trigger = schedule.beats_by_element[eid]
        assert trigger == identities[eid].onset
        assert trigger < note.onset           # strictly before the principal


def test_grace_stems_share_the_grace_trigger(schedule) -> None:
    # deterministic ElementIds (fixed xmlIdSeed): the m1 grace-note stems
    assert schedule.beats_by_element["P1:m1:s1:v1:stem:0"] == 0.8828125
    assert schedule.beats_by_element["P1:m1:s1:v1:stem:1"] == 0.94140625
    assert schedule.beats_by_element["P5:m1:s1:v1:stem:0"] == 0.94140625


def test_all_tied_chords_inherit_through_their_ink(schedule, join_mapping,
                                                   identities) -> None:
    """Fixture fact: every tied-over chord is tied in ALL its heads (no
    mixed groups exist — pinned here; the mixed 'any fresh' rule is
    covered synthetically below). All-tied groups' stems/attachments
    inherit the chain-start trigger with their heads."""
    heads_by_group = defaultdict(list)
    for eid, note in join_mapping.items():
        ident = identities[eid]
        heads_by_group[(ident.part, ident.staff, ident.voice,
                        _q(ident.onset))].append(eid)
    ink_by_group = defaultdict(list)
    for eid, ident in identities.items():
        if ident.kind in (ElementKind.STEM, ElementKind.FLAG):
            ink_by_group[(ident.part, ident.staff, ident.voice,
                          _q(ident.onset))].append(eid)
    all_tied_groups = 0
    for key, heads in heads_by_group.items():
        tied = [e for e in heads if join_mapping[e].tie in ("stop", "continue")]
        if not tied:
            continue
        assert len(tied) == len(heads), f"mixed tied chord appeared: {key}"
        all_tied_groups += 1
        earliest = min(schedule.beats_by_element[e] for e in tied)
        for ink in ink_by_group.get(key, ()):
            assert schedule.beats_by_element[ink] == earliest, ink
            assert earliest < identities[ink].onset
    assert all_tied_groups > 0


def test_fresh_elements_of_a_trigger_share_one_page(schedule, identities,
                                                    engraved) -> None:
    pages = {el.identity.element_id: el.page for el in engraved.layout.elements}
    for trigger in schedule.triggers:
        fresh_pages = {pages[eid] for eid in trigger.element_ids
                       if _q(schedule.beats_by_element[eid])
                       == _q(identities[eid].onset)}
        if fresh_pages:
            assert len(fresh_pages) == 1
            assert trigger.page == fresh_pages.pop()


def test_trigger_pages_monotone(schedule) -> None:
    pages = [t.page for t in schedule.triggers]
    assert pages == sorted(pages)


# --- synthetic coverage for the group rule (no mixed chords in fixture) ----

def _synthetic(tie_second_head: str | None):
    from scoreanim.core.engraving.types import (Layout, PageGeometry, Point,
                                                Rect, RenderedElement,
                                                RenderPrimitive)
    from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                               PartId)
    from scoreanim.core.score.model import ScoreNote

    def el(eid: str, kind: ElementKind, onset: float) -> RenderedElement:
        ident = ElementIdentity(ElementId(eid), kind, PartId("P1"), "Part",
                                1, 1, onset)
        return RenderedElement(ident, 1, 0.0, 0.0, Rect(0, 0, 1, 1),
                               Point(0, 0), RenderPrimitive(paths=()))

    def note(onset: float, step: str, order: int,
             tie: str | None) -> ScoreNote:
        return ScoreNote(part=PartId("P1"), measure=1, staff=1,
                         voice_label=None, onset=onset, grace=False,
                         pitch_step=step, pitch_alter=0.0, octave=4,
                         staff_loc=None, order=order, tie=tie)

    layout = Layout(
        pages=(PageGeometry(1, 100.0, 100.0),),
        elements=(el("c0", ElementKind.NOTEHEAD, 0.0),
                  el("e0", ElementKind.NOTEHEAD, 0.0),
                  el("s0", ElementKind.STEM, 0.0),
                  el("c1", ElementKind.NOTEHEAD, 4.0),
                  el("e1", ElementKind.NOTEHEAD, 4.0),
                  el("s1", ElementKind.STEM, 4.0)))
    mapping = {
        "c0": note(0.0, "C", 0, "start"),
        "e0": note(0.0, "E", 1, "start" if tie_second_head else None),
        "c1": note(4.0, "C", 0, "stop"),
        "e1": note(4.0, "E", 1, tie_second_head),
    }
    return build_trigger_schedule(layout, mapping)


def test_mixed_chord_articulates_at_notated_onset() -> None:
    """One tied head + one fresh head: only the tied head lights early;
    the fresh head AND the shared stem fire at the chord's own onset."""
    sched = _synthetic(tie_second_head=None)
    assert sched.beats_by_element["c1"] == 0.0     # tied head inherits
    assert sched.beats_by_element["e1"] == 4.0     # fresh head at own onset
    assert sched.beats_by_element["s1"] == 4.0     # any-fresh: stem articulates
    assert sched.beats_by_element["s0"] == 0.0


def test_all_tied_chord_inherits_stem() -> None:
    sched = _synthetic(tie_second_head="stop")
    assert sched.beats_by_element["c1"] == 0.0
    assert sched.beats_by_element["e1"] == 0.0
    assert sched.beats_by_element["s1"] == 0.0     # all tied: stem inherits


def test_animated_census(engraved) -> None:
    """Scaffold never animates; note ink always does."""
    static_kinds = {ElementKind.REST, ElementKind.MREST, ElementKind.CLEF,
                    ElementKind.KEY_SIG, ElementKind.METER_SIG,
                    ElementKind.BARLINE, ElementKind.STAFF_LINES,
                    ElementKind.DYNAMIC, ElementKind.TEXT,
                    ElementKind.CHORD_SYMBOL, ElementKind.LYRIC,
                    ElementKind.HAIRPIN}
    for el in engraved.layout.elements:
        ident = el.identity
        if ident.kind in static_kinds:
            assert not is_animated(ident), ident.element_id
        if ident.kind in (ElementKind.NOTEHEAD, ElementKind.SLASH,
                          ElementKind.STEM, ElementKind.BEAM):
            assert is_animated(ident), ident.element_id
