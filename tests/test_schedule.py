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
    """Fresh NON-DISPLACED elements: a retimed end-of-system courtesy
    sig (FINDING-4, 2026-07-23) is fresh (its onset IS the retimed
    beat) but drawn on the previous system/page, so a sig whose onset
    is not its own drawn measure's start never drives the page/system
    hint (schedule._displaced_sig exclusion)."""
    import re

    from scoreanim.core.animation.schedule import SIG_KINDS

    def displaced(eid) -> bool:
        ident = identities[eid]
        if ident.kind not in SIG_KINDS:
            return False
        m = re.search(r":m(\d+):", str(eid))
        start = engraved.timeline.starts.get(int(m.group(1))) if m else None
        return (start is not None
                and quantize_beats(start) != quantize_beats(ident.onset))

    pages = {el.identity.element_id: el.page for el in engraved.layout.elements}
    for trigger in schedule.triggers:
        fresh_pages = {pages[eid] for eid in trigger.element_ids
                       if quantize_beats(schedule.beats_by_element[eid])
                       == quantize_beats(identities[eid].onset)
                       and not displaced(eid)}
        if fresh_pages:
            assert len(fresh_pages) == 1
            assert trigger.page == fresh_pages.pop()


def test_trigger_pages_monotone(schedule) -> None:
    pages = [t.page for t in schedule.triggers]
    assert pages == sorted(pages)


# --- synthetic coverage for the group rule (no mixed chords in fixture) ----

def _synthetic(tie_second_head: str | None, tied_as_one: bool = False):
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
    return build_trigger_schedule(layout, mapping, tied_as_one=tied_as_one)


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


# --- tied notes as one (2026-08-10, option) --------------------------------

@pytest.fixture(scope="module")
def schedule_tied(engraved, join_mapping, score_model):
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures, tied_as_one=True)


def test_tied_as_one_off_is_exactly_todays_schedule(engraved, join_mapping,
                                                    score_model,
                                                    schedule) -> None:
    """The flag's default is off, and off is byte-for-byte rule 1 — the
    guard that makes every already-saved project render unchanged."""
    assert build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures,
                                  tied_as_one=False) == schedule


def test_tied_as_one_retimes_every_continuation_to_its_chain_start(
        schedule_tied, engraved, join_mapping) -> None:
    """Option on: all 64 stop/continue heads fire WITH their chain's
    first head, at that head's own notated onset — the deliberate,
    option-scoped reversal of the 2026-07-22 grow-with-playhead rule."""
    from scoreanim.core.animation.tie_chains import tie_chains
    leader, _ = tie_chains(engraved.layout, join_mapping, {})
    assert len(leader) == 64             # every tied head finds its chain
    for eid, head in leader.items():
        assert schedule_tied.beats_by_element[eid] \
            == schedule_tied.beats_by_element[head], eid
        assert schedule_tied.beats_by_element[head] \
            == join_mapping[head].onset, head


def test_tied_as_one_leaves_fresh_noteheads_alone(schedule_tied, schedule,
                                                  join_mapping) -> None:
    for eid, note in join_mapping.items():
        if note.tie not in ("stop", "continue"):
            assert schedule_tied.beats_by_element[eid] \
                == schedule.beats_by_element[eid], eid


def test_tied_as_one_hihat_stop_fires_with_its_m18_start(schedule,
                                                         schedule_tied
                                                         ) -> None:
    """The m18→19 voice-relabel chain: off fires the stop at its own
    m19 downbeat (66.0); on carries it back to the m18 chain start."""
    stop = "P7:m19:s1:v5:note:0"
    assert schedule.beats_by_element[stop] == 66.0
    assert schedule_tied.beats_by_element[stop] < 66.0


def test_tied_as_one_mixed_chord_still_articulates() -> None:
    """Rule 3's any-fresh rule survives the option: a chord holding one
    tied note still articulates at its own onset, and only an ALL-tied
    group inherits the chain-start trigger (rule 3's else branch, live
    again for the first time since 2026-07-22)."""
    mixed = _synthetic(tie_second_head=None, tied_as_one=True)
    assert mixed.beats_by_element["c1"] == 0.0    # continuation retimed
    assert mixed.beats_by_element["e1"] == 4.0    # fresh head, its own
    assert mixed.beats_by_element["s1"] == 4.0    # any-fresh articulates

    all_tied = _synthetic(tie_second_head="stop", tied_as_one=True)
    assert all_tied.beats_by_element["c1"] == 0.0
    assert all_tied.beats_by_element["e1"] == 0.0
    assert all_tied.beats_by_element["s1"] == 0.0  # the group follows
    assert all_tied.beats_by_element["s0"] == 0.0


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



# --- ink hanging off a rest (2026-08-30) -----------------------------------

def _rest_attachment_layout(dash_voice, rest_voice):
    """A rest on beat 2, a note on beat 3 in the same voice, and a ledger
    dash carrying the rest's onset. The dash has its own id, so it is in
    neither trigger map — it has to find the rest through the group
    table built from the rests."""
    from scoreanim.core.engraving.types import (Layout, PageGeometry, Point,
                                                Rect, RenderedElement,
                                                RenderPrimitive)
    from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                               PartId)
    from scoreanim.core.score.model import ScoreNote

    def el(eid, kind, onset, voice) -> RenderedElement:
        ident = ElementIdentity(ElementId(eid), kind, PartId("P1"), "Part",
                                1, voice, onset)
        return RenderedElement(ident, 1, 0.0, 0.0, Rect(0, 0, 1, 1),
                               Point(0, 0), RenderPrimitive(paths=()))

    layout = Layout(
        pages=(PageGeometry(1, 100.0, 100.0),),
        elements=(el("r0", ElementKind.REST, 2.0, rest_voice),
                  el("dash", ElementKind.LEDGER_LINES, 2.0, dash_voice),
                  el("n0", ElementKind.NOTEHEAD, 3.0, 1)))
    mapping = {"n0": ScoreNote(part=PartId("P1"), measure=1, staff=1,
                               voice_label=None, onset=3.0, grace=False,
                               pitch_step="C", pitch_alter=0.0, octave=4,
                               staff_loc=None, order=0, tie=None)}
    return build_trigger_schedule(layout, mapping)


def test_a_dash_under_a_rest_fires_with_the_rest() -> None:
    """The bug: the dash was in neither trigger map, missed the notehead
    group table, and fell back to its own onset — so it lit on the rest's
    silent beat while the rest itself waited for the next note."""
    sched = _rest_attachment_layout(dash_voice=1, rest_voice=1)
    assert sched.beats_by_element["r0"] == 3.0        # rest: next note
    assert sched.beats_by_element["dash"] == 3.0      # dash: with the rest
    assert sched.beats_by_element["dash"] != 2.0      # not its own onset


def test_a_dash_with_voice_zero_finds_a_rest_with_voice_none() -> None:
    """The adapter's rest tier defaults a missing layer to 0, so a rest
    carrying voice None owns ink carrying voice 0. Both normalise to the
    same key."""
    sched = _rest_attachment_layout(dash_voice=0, rest_voice=None)
    assert sched.beats_by_element["r0"] == 3.0
    assert sched.beats_by_element["dash"] == 3.0


def test_a_dotted_rests_dot_fires_with_the_rest() -> None:
    """Not only ledger dashes: anything the adapter hangs off a rest —
    an augmentation dot (kind OTHER), a fermata (ARTICULATION) — carries
    the rest's onset and its own id, so it takes the same path."""
    from scoreanim.core.engraving.types import (Layout, PageGeometry, Point,
                                                Rect, RenderedElement,
                                                RenderPrimitive)
    from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                               PartId)
    from scoreanim.core.score.model import ScoreNote

    def el(eid, kind, onset) -> RenderedElement:
        ident = ElementIdentity(ElementId(eid), kind, PartId("P1"), "Part",
                                1, 1, onset)
        return RenderedElement(ident, 1, 0.0, 0.0, Rect(0, 0, 1, 1),
                               Point(0, 0), RenderPrimitive(paths=()))

    layout = Layout(
        pages=(PageGeometry(1, 100.0, 100.0),),
        elements=(el("r0", ElementKind.REST, 0.0),
                  el("dot", ElementKind.OTHER, 0.0),
                  el("ferm", ElementKind.ARTICULATION, 0.0),
                  el("n0", ElementKind.NOTEHEAD, 1.5)))
    mapping = {"n0": ScoreNote(part=PartId("P1"), measure=1, staff=1,
                               voice_label=None, onset=1.5, grace=False,
                               pitch_step="C", pitch_alter=0.0, octave=4,
                               staff_loc=None, order=0, tie=None)}
    sched = build_trigger_schedule(layout, mapping)
    assert sched.beats_by_element["r0"] == 1.5
    assert sched.beats_by_element["dot"] == 1.5
    assert sched.beats_by_element["ferm"] == 1.5


def test_complex1_mrest_dash_fires_with_its_mrest(engraved_complex1,
                                                  complex1_score_model) -> None:
    """The real case: complex1 p3 m13 staff 8, the two-voice measure
    whose whole-bar rest is displaced above the staff onto a ledger dash
    at x=1277 (tests/test_complex1.py pins the attribution). The dash
    used to light on the mRest's downbeat (48.0) while the mRest waited
    for its barline (52.0)."""
    from scoreanim.core.score.join import join_notes
    mapping = join_notes(complex1_score_model,
                         engraved_complex1.note_records).mapping
    sched = build_trigger_schedule(engraved_complex1.layout, mapping,
                                   complex1_score_model.measures)
    mrests = [e for e in engraved_complex1.layout.elements
              if e.identity.kind is ElementKind.MREST
              and str(e.identity.element_id) == "P8:m13:s1:v1:mrest:0"]
    assert len(mrests) == 1
    mrest = mrests[0].identity.element_id
    # P2 has its own dash at the same x on that page (a notehead's), so
    # the part is part of the address, not the x alone
    dashes = [e for e in engraved_complex1.layout.elements
              if e.identity.kind is ElementKind.LEDGER_LINES
              and e.page == 3 and abs(e.bbox.x - 1277) < 3
              and e.identity.part == mrests[0].identity.part]
    assert len(dashes) == 1
    assert sched.beats_by_element[mrest] == 52.0     # the bar's end
    for d in dashes:
        assert (sched.beats_by_element[d.identity.element_id]
                == sched.beats_by_element[mrest])


def test_every_rest_owned_dash_in_complex1_fires_with_its_rest(
        engraved_complex1, complex1_score_model) -> None:
    """All five of complex1's rest-owned dashes, not just the mRest one:
    a dash that matches no notehead group but does match a rest group
    takes the rest's trigger."""
    from scoreanim.core.score.join import join_notes
    from scoreanim.core.animation.schedule import quantize_beats
    mapping = join_notes(complex1_score_model,
                         engraved_complex1.note_records).mapping
    sched = build_trigger_schedule(engraved_complex1.layout, mapping,
                                   complex1_score_model.measures)
    rest_kinds = (ElementKind.REST, ElementKind.MREST)
    rest_key = {}
    note_keys = set()
    for e in engraved_complex1.layout.elements:
        i = e.identity
        if i.onset is None:
            continue
        if i.kind in rest_kinds:
            rest_key[(i.part, i.staff, 0 if i.voice is None else i.voice,
                      quantize_beats(i.onset))] = i.element_id
        elif i.kind is ElementKind.NOTEHEAD:
            note_keys.add((i.part, i.staff, i.voice, quantize_beats(i.onset)))
    found = 0
    for e in engraved_complex1.layout.elements:
        i = e.identity
        if i.kind is not ElementKind.LEDGER_LINES or i.onset is None:
            continue
        if (i.part, i.staff, i.voice, quantize_beats(i.onset)) in note_keys:
            continue                                  # a notehead's dash
        owner = rest_key.get((i.part, i.staff,
                              0 if i.voice is None else i.voice,
                              quantize_beats(i.onset)))
        assert owner is not None, i.element_id        # attributed to a rest
        found += 1
        assert (sched.beats_by_element[i.element_id]
                == sched.beats_by_element[owner]), i.element_id
        assert sched.beats_by_element[i.element_id] > i.onset
    assert found == 5


def test_complex3_dotted_rest_dots_fire_with_their_rests(
        engraved_complex3_hidden) -> None:
    """The dot case on a real score: complex3 has four dotted rests
    whose augmentation dot (kind OTHER) carries the rest's onset. Each
    dot used to light 3.5 beats early, on the rest's own silent beat."""
    from scoreanim.core.score.join import join_notes
    from scoreanim.core.score.model import build_score_model
    eng = engraved_complex3_hidden
    model = build_score_model(eng.prepared, eng.timeline)
    mapping = join_notes(model, eng.note_records).mapping
    sched = build_trigger_schedule(eng.layout, mapping, model.measures)
    t = sched.beats_by_element
    onsets = {e.identity.element_id: e.identity.onset
              for e in eng.layout.elements}
    for dot, rest in (("P1:m19:s1:v1:dots:0", "P1:m19:s1:v1:rest:0"),
                      ("P5:m19:s1:v1:dots:0", "P5:m19:s1:v1:rest:0"),
                      ("P17:m49:s1:v1:dots:0", "P17:m49:s1:v1:rest:0"),
                      ("P1:m57:s1:v1:dots:0", "P1:m57:s1:v1:rest:0")):
        assert t[dot] == t[rest], dot
        assert t[dot] > onsets[dot], dot          # never on its own beat

# --- trigger overrides (2026-08-08) ----------------------------------------

def _override_setup():
    """Two pages, two systems. P1's noteheads sit where the hint tests
    need them; d0 is the movable dynamic."""
    from scoreanim.core.engraving.types import (Layout, PageGeometry, Point,
                                                Rect, RenderedElement,
                                                RenderPrimitive)
    from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                               PartId)
    from scoreanim.core.score.model import ScoreNote

    def el(eid: str, kind: ElementKind, onset: float,
           page: int, system: int) -> RenderedElement:
        ident = ElementIdentity(ElementId(eid), kind, PartId("P1"), "Part",
                                1, 1, onset)
        return RenderedElement(ident, page, 0.0, 0.0, Rect(0, 0, 1, 1),
                               Point(0, 0), RenderPrimitive(paths=()),
                               system=system)

    def note(onset: float, step: str, order: int) -> ScoreNote:
        return ScoreNote(part=PartId("P1"), measure=1, staff=1,
                         voice_label=None, onset=onset, grace=False,
                         pitch_step=step, pitch_alter=0.0, octave=4,
                         staff_loc=None, order=order, tie=None)

    layout = Layout(
        pages=(PageGeometry(1, 100.0, 100.0), PageGeometry(2, 100.0, 100.0)),
        # n0 deliberately on page 2 so the own-onset case is observable:
        # a fresh d0 (page 1) would DRAG row 0's min() hint to 1
        elements=(el("n0", ElementKind.NOTEHEAD, 0.0, 2, 2),
                  el("d0", ElementKind.DYNAMIC, 0.0, 1, 1),
                  el("n1", ElementKind.NOTEHEAD, 4.0, 2, 2),
                  el("n2", ElementKind.NOTEHEAD, 8.0, 2, 2)))
    mapping = {ElementId("n0"): note(0.0, "C", 0),
               ElementId("n1"): note(4.0, "D", 1),
               ElementId("n2"): note(8.0, "E", 2)}
    return layout, mapping


def test_override_moves_an_element_between_rows() -> None:
    """The override lands d0 in a NEW row at its beat and takes it out
    of its old one; beats_by_element reports the new time; rows stay
    sorted."""
    layout, mapping = _override_setup()
    moved = build_trigger_schedule(layout, mapping,
                                   trigger_overrides={"d0": 2.5})
    beats = {t.beats: t for t in moved.triggers}
    assert set(beats) == {0.0, 2.5, 4.0, 8.0}
    assert beats[2.5].element_ids == ("d0",)
    assert "d0" not in beats[0.0].element_ids
    assert moved.beats_by_element["d0"] == 2.5
    assert list(moved.beat_values) == sorted(moved.beat_values)


def test_override_merges_into_an_existing_row() -> None:
    layout, mapping = _override_setup()
    moved = build_trigger_schedule(layout, mapping,
                                   trigger_overrides={"d0": 4.0})
    beats = {t.beats: t for t in moved.triggers}
    assert set(beats) == {0.0, 4.0, 8.0}
    assert set(beats[4.0].element_ids) == {"n1", "d0"}
    assert moved.beats_by_element["d0"] == 4.0


def test_overridden_element_never_drives_the_hints() -> None:
    """The displaced-courtesy-sig rule reused: d0 (drawn page 1,
    system 1) moved onto n2's row must not drag that row's min() hints
    off page 2 / system 2."""
    layout, mapping = _override_setup()
    moved = build_trigger_schedule(layout, mapping,
                                   trigger_overrides={"d0": 8.0})
    row = {t.beats: t for t in moved.triggers}[8.0]
    assert set(row.element_ids) == {"n2", "d0"}
    assert row.page == 2
    assert row.system == 2


def test_override_equal_to_own_onset_is_still_not_fresh() -> None:
    """An override that lands exactly on the element's own onset still
    never counts as fresh — the exclusion is explicit, not
    trigger != own."""
    layout, mapping = _override_setup()
    moved = build_trigger_schedule(layout, mapping,
                                   trigger_overrides={"d0": 0.0})
    row = {t.beats: t for t in moved.triggers}[0.0]
    assert set(row.element_ids) == {"n0", "d0"}
    # only n0 is fresh, so the hint is its page 2 — a fresh d0 would
    # have dragged the min() to page 1
    assert row.page == 2
    assert row.system == 2


def test_anchor_kind_and_unknown_id_overrides_are_ignored() -> None:
    layout, mapping = _override_setup()
    plain = build_trigger_schedule(layout, mapping)
    assert build_trigger_schedule(
        layout, mapping, trigger_overrides={"n0": 6.0}) == plain
    assert build_trigger_schedule(
        layout, mapping, trigger_overrides={"ghost": 6.0}) == plain


def test_override_schedules_are_deterministic() -> None:
    layout, mapping = _override_setup()
    overrides = {"d0": 2.5}
    assert (build_trigger_schedule(layout, mapping,
                                   trigger_overrides=overrides)
            == build_trigger_schedule(layout, mapping,
                                      trigger_overrides=overrides))


def test_override_moves_a_real_dynamic(engraved, join_mapping, score_model,
                                       identities, schedule) -> None:
    """On the real fixture: a dynamic moved to another row's beat joins
    that row, and every other element keeps its trigger."""
    dynamic = next(eid for eid, ident in identities.items()
                   if ident.kind is ElementKind.DYNAMIC
                   and ident.onset is not None)
    target = next(b for b in schedule.beat_values
                  if quantize_beats(b)
                  != quantize_beats(schedule.beats_by_element[dynamic]))
    moved = build_trigger_schedule(engraved.layout, join_mapping,
                                   score_model.measures,
                                   trigger_overrides={dynamic: target})
    assert moved.beats_by_element[dynamic] == target
    row = {quantize_beats(t.beats): t for t in moved.triggers}[
        quantize_beats(target)]
    assert dynamic in row.element_ids
    others = {eid: b for eid, b in schedule.beats_by_element.items()
              if eid != dynamic}
    assert {eid: b for eid, b in moved.beats_by_element.items()
            if eid != dynamic} == others
