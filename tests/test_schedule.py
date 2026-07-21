"""Trigger schedule on the real fixture: tie gating, graces, groups, pages."""
from __future__ import annotations

from collections import defaultdict

import pytest

from scoreanim.core.animation import build_trigger_schedule, is_animated
from scoreanim.core.animation.schedule import quantize_beats
from scoreanim.core.score.identity import ElementKind


@pytest.fixture(scope="module")
def schedule(engraved, join_mapping, score_model):
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures)


@pytest.fixture(scope="module")
def identities(engraved):
    return {el.identity.element_id: el.identity
            for el in engraved.layout.elements}


def test_sorted_and_deterministic(engraved, join_mapping, schedule,
                                  score_model) -> None:
    assert list(schedule.beat_values) == sorted(schedule.beat_values)
    again = build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures)
    assert again == schedule


def test_all_slashes_scheduled_on_their_beats(schedule, identities) -> None:
    slashes = [eid for eid, ident in identities.items()
               if ident.kind is ElementKind.SLASH]
    assert len(slashes) == 52
    for eid in slashes:
        assert schedule.beats_by_element[eid] == identities[eid].onset


def test_tie_stops_fire_at_own_onset(schedule, join_mapping) -> None:
    """Grow-with-playhead (ruling A/B revised 2026-07-22): all 58 stop + 6
    continue noteheads fire at their OWN notated onset — a held note fills
    in at each barline rather than the whole span lighting at the chain
    start. (Previously they inherited the chain-start trigger.)"""
    gated = {eid: n for eid, n in join_mapping.items()
             if n.tie in ("stop", "continue")}
    assert len(gated) == 64
    for eid, note in gated.items():
        assert schedule.beats_by_element[eid] == note.onset, eid


def test_fresh_noteheads_fire_at_own_onset(schedule, join_mapping,
                                           identities) -> None:
    for eid, note in join_mapping.items():
        if note.tie in ("stop", "continue"):
            continue
        expected = identities[eid].onset if note.grace else note.onset
        assert schedule.beats_by_element[eid] == expected, eid


def test_every_notehead_fires_at_its_own_onset(schedule, join_mapping,
                                               identities) -> None:
    """The whole point of the grow-with-playhead revision: NO notehead
    (tied or fresh) is retimed — each fires at its own notated onset (a
    grace at its fractional qstamp). So the reveal edge sweeps a held note
    left-to-right with the playhead instead of jumping to the chain end."""
    for eid, note in join_mapping.items():
        expected = identities[eid].onset if note.grace else note.onset
        assert schedule.beats_by_element[eid] == expected, eid


def test_hihat_tie_stop_fires_at_its_own_onset(schedule) -> None:
    """m18→19 drum tie stop (voice '5', its start was the implicit voice in
    m18): with retiming removed it fires at its OWN m19 downbeat (66.0), not
    the m18 chain start — the held hi-hat fills in at the barline."""
    assert schedule.beats_by_element["P7:m19:s1:v5:note:0"] == 66.0


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


def test_tied_chord_ink_fires_at_the_groups_own_onset(schedule, join_mapping,
                                                      identities) -> None:
    """Fixture fact: every tied-over chord is tied in ALL its heads (no
    mixed groups exist — pinned here; the mixed 'any fresh' rule is covered
    synthetically below). With retiming removed, an all-tied group's
    stems/attachments fire at the group's OWN notated onset (with its
    heads), so the whole re-notated chord fills in at its barline."""
    heads_by_group = defaultdict(list)
    for eid, note in join_mapping.items():
        ident = identities[eid]
        heads_by_group[(ident.part, ident.staff, ident.voice,
                        quantize_beats(ident.onset))].append(eid)
    ink_by_group = defaultdict(list)
    for eid, ident in identities.items():
        if ident.kind in (ElementKind.STEM, ElementKind.FLAG):
            ink_by_group[(ident.part, ident.staff, ident.voice,
                          quantize_beats(ident.onset))].append(eid)
    all_tied_groups = 0
    for key, heads in heads_by_group.items():
        tied = [e for e in heads if join_mapping[e].tie in ("stop", "continue")]
        if not tied:
            continue
        assert len(tied) == len(heads), f"mixed tied chord appeared: {key}"
        all_tied_groups += 1
        for ink in ink_by_group.get(key, ()):
            assert schedule.beats_by_element[ink] == identities[ink].onset, ink
    assert all_tied_groups > 0


def test_fresh_elements_of_a_trigger_share_one_page(schedule, identities,
                                                    engraved) -> None:
    pages = {el.identity.element_id: el.page for el in engraved.layout.elements}
    for trigger in schedule.triggers:
        fresh_pages = {pages[eid] for eid in trigger.element_ids
                       if quantize_beats(schedule.beats_by_element[eid])
                       == quantize_beats(identities[eid].onset)}
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


def test_chord_ink_fires_at_own_onset_tied_or_not() -> None:
    """Grow-with-playhead: retiming removed, so a chord's heads and its
    shared stem all fire at the chord's OWN notated onset whether or not a
    head is tied — the re-notated chord fills in at its barline, it never
    inherits the chain-start trigger."""
    for second in (None, "stop"):
        sched = _synthetic(tie_second_head=second)
        assert sched.beats_by_element["c1"] == 4.0   # (tied) head, own onset
        assert sched.beats_by_element["e1"] == 4.0   # head, own onset
        assert sched.beats_by_element["s1"] == 4.0   # shared stem, own onset
        assert sched.beats_by_element["s0"] == 0.0   # first chord's stem


# Page furniture — TEXT sub-classes the adapter mints onset-less; the
# only static ink outside STATIC_KINDS (ruling 2026-07-20).
_FURNITURE = ("label", "labelAbbr", "pgHead", "pgFoot", "mNum")


def test_animated_census(engraved) -> None:
    """Inverted taxonomy (ruling 2026-07-20): animation is a DENYLIST.
    Everything animates EXCEPT the scaffold (STATIC_KINDS — staff lines,
    barlines, group symbols, system dividers) and page furniture (labels,
    headers, measure numbers, minted onset-less). Clefs and key
    signatures MOVED to animated. Clip-revealed spanners (slur/tie/
    hairpin) animate by growth, not opacity, so is_animated excludes
    them. TINTED_KINDS is unchanged (color scope is untouched)."""
    from scoreanim.core.animation import (REVEALED_KINDS, STATIC_KINDS,
                                          is_revealed)

    assert STATIC_KINDS == {ElementKind.STAFF_LINES, ElementKind.BARLINE,
                            ElementKind.GROUP_SYMBOL,
                            ElementKind.SYSTEM_DIVIDER}
    assert REVEALED_KINDS == {ElementKind.SLUR, ElementKind.TIE,
                              ElementKind.HAIRPIN}
    # clefs and key signatures now animate (the ruling's headline change)
    clefs = [e for e in engraved.layout.elements
             if e.identity.kind in (ElementKind.CLEF, ElementKind.KEY_SIG)]
    assert clefs and all(is_animated(e.identity) for e in clefs)

    for el in engraved.layout.elements:
        ident = el.identity
        if ident.kind in STATIC_KINDS:
            assert not is_animated(ident), ident.element_id
            assert not is_revealed(ident.kind), ident.element_id
        elif ident.kind in REVEALED_KINDS:
            assert not is_animated(ident), ident.element_id     # clip-grown
        else:
            # everything else is animated ink UNLESS it is page furniture
            furniture = (ident.kind is ElementKind.TEXT
                         and el.text_class in _FURNITURE)
            assert is_animated(ident) == (not furniture), ident.element_id


def test_no_kind_outside_the_denylist_sits_static(engraved, engraved_video,
                                                   engraved_complex1) -> None:
    """The census invariant across three real fixtures: an element is
    static ONLY if it is scaffold (STATIC_KINDS) or page furniture; every
    other element carries an onset and animates. This is what makes the
    denylist correct — no kind ships static-by-omission (ruling
    2026-07-20)."""
    from scoreanim.core.animation import REVEALED_KINDS, STATIC_KINDS
    for score in (engraved, engraved_video, engraved_complex1):
        for el in score.layout.elements:
            ident = el.identity
            if ident.kind in REVEALED_KINDS or is_animated(ident):
                continue
            # the only permitted static ink:
            allowed = (ident.kind in STATIC_KINDS
                       or (ident.kind is ElementKind.TEXT
                           and el.text_class in _FURNITURE))
            assert allowed, (ident.element_id, ident.kind, el.text_class)


def test_tinted_kinds_unchanged_by_the_animate_everything_ruling() -> None:
    """Animation scope widened; COLOR scope did not (ruling 2026-07-20).
    Clefs/keysigs animate but stay black; TINTED_KINDS is exactly the
    Phase 5 playing ink plus the clip-revealed spanners — and BAR_REPEAT,
    which is synthesized playing ink and tints like SLASH (Phase 12.2)."""
    from scoreanim.core.animation import TINTED_KINDS
    assert TINTED_KINDS == {
        ElementKind.NOTEHEAD, ElementKind.SLASH, ElementKind.BAR_REPEAT,
        ElementKind.STEM, ElementKind.FLAG, ElementKind.BEAM,
        ElementKind.ACCIDENTAL, ElementKind.ARTICULATION,
        ElementKind.LEDGER_LINES,
        ElementKind.SLUR, ElementKind.TIE, ElementKind.HAIRPIN}
    assert ElementKind.CLEF not in TINTED_KINDS
    assert ElementKind.KEY_SIG not in TINTED_KINDS


def test_dynamics_trigger_at_their_attach_point(schedule,
                                                identities) -> None:
    """Ruling B (2026-07-12): the fixture's m1 dynamics attach to the
    tutti chord at 1.0 quarters, not the measure start."""
    dynamics = [eid for eid, ident in identities.items()
                if ident.kind is ElementKind.DYNAMIC]
    assert len(dynamics) == 16
    for eid in dynamics:
        assert schedule.beats_by_element[eid] == identities[eid].onset, eid
    m1 = [eid for eid in dynamics if ":m1:" in str(eid)]
    assert len(m1) == 6
    assert all(schedule.beats_by_element[eid] == 1.0 for eid in m1)


def test_rests_trigger_when_their_silence_resolves(schedule, identities,
                                                   score_model) -> None:
    """Rest rule (2026-07-12, second session): a rest appears at the
    next note or at the end of its own bar, whichever comes first —
    never on its own silent beat. Fixture pins:
    - P1's opening rest shows with the GRACE note (fractional trigger
      0.8828125 — 'when the next note shows'), not at beat 0;
    - whole-bar rests complete at their own barline (m2 4/4 → beat 8,
      m5 2/4 → beat 18);
    - m12's two rests both cap at the next note (45.0), before the
      barline (46.0)."""
    rests = {str(eid): eid for eid, ident in identities.items()
             if ident.kind in (ElementKind.REST, ElementKind.MREST)}
    assert len(rests) == 114
    t = schedule.beats_by_element
    assert t[rests["P1:m1:s1:v1:rest:0"]] == 0.8828125
    assert t[rests["P1:m2:s1:v1:mrest:0"]] == 8.0
    assert t[rests["P1:m5:s1:v1:mrest:0"]] == 18.0
    assert t[rests["P1:m12:s1:v1:rest:0"]] == 45.0
    assert t[rests["P1:m12:s1:v1:rest:1"]] == 45.0
    # the general shape: never before the rest's own beat, never past
    # its own barline
    for eid in rests.values():
        onset = identities[eid].onset
        assert t[eid] > onset, eid                 # never on the beat
        measure = next(m for m in score_model.measures
                       if m.start <= onset < m.start + m.quarter_length)
        assert t[eid] <= measure.start + measure.quarter_length, eid
