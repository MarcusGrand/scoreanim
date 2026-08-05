"""Which ink glows, whose halo it is, and how long it burns
(core/animation/glow_scope.py).

Only note ink glows — noteheads, the accidental in front of one, the
syllable under one, the tie between two, and the slash or bar-repeat
sign that stands in for one. Rests, dynamics, clefs, signatures, texts
and slurs are dark whatever the effect says.

A tied note is ONE note: every notehead of a chain and every tie between
them shares the first head's halo, and that halo lasts the whole chain.
Synthetic layouts pin the policy; the real fixtures check it end to end.
"""
from __future__ import annotations

from scoreanim.core.animation import (GLOWING_KINDS, glow_scope,
                                      resolve_durations)
from scoreanim.core.engraving.svg_geom import rect_path
from scoreanim.core.engraving.types import (Affine, Layout, PageGeometry,
                                            PathPrimitive, Rect,
                                            RenderedElement, RenderPrimitive)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)
from scoreanim.core.score.model import ScoreNote


def _el(eid: str, kind: ElementKind, onset: float | None,
        box: Rect = Rect(0, 0, 2, 2), voice: int | None = 1
        ) -> RenderedElement:
    ident = ElementIdentity(ElementId(eid), kind, PartId("P1"), "Part",
                            1, voice, onset)
    glyph = RenderPrimitive(paths=(PathPrimitive(
        d=rect_path(box.x, box.y, box.w, box.h), transform=Affine()),))
    return RenderedElement(ident, 1, box.x, box.y, box, box.center, glyph)


def _note(onset: float, tie: str | None, order: int = 0,
          step: str = "C", octave: int = 4) -> ScoreNote:
    return ScoreNote(part=PartId("P1"), measure=1, staff=1, voice_label="1",
                     onset=onset, grace=False, pitch_step=step,
                     pitch_alter=0.0, octave=octave, staff_loc=None,
                     order=order, tie=tie)


# A whole note held over a barline into a half note, with an accidental
# on the first head and the tie ink between them — plus a rest, a
# dynamic and a slur that must all stay dark.
LAYOUT = Layout(
    pages=(PageGeometry(1, 100.0, 100.0),),
    elements=(
        _el("head-1", ElementKind.NOTEHEAD, 0.0, Rect(0, 0, 2, 2)),
        _el("accid-1", ElementKind.ACCIDENTAL, 0.0, Rect(-4, 0, 2, 2)),
        _el("lyric-1", ElementKind.LYRIC, 0.0, Rect(0, 20, 6, 3)),
        _el("tie", ElementKind.TIE, 0.0, Rect(2, 2, 20, 1)),
        _el("head-2", ElementKind.NOTEHEAD, 4.0, Rect(24, 0, 2, 2)),
        _el("rest", ElementKind.REST, 6.0, Rect(40, 0, 2, 2)),
        _el("dynamic", ElementKind.DYNAMIC, 0.0, Rect(0, 30, 4, 3)),
        _el("slur", ElementKind.SLUR, 0.0, Rect(2, -6, 20, 1)),
        _el("meter", ElementKind.METER_SIG, 0.0, Rect(-10, 0, 2, 6)),
    ),
)
MAPPING = {ElementId("head-1"): _note(0.0, "start"),
           ElementId("head-2"): _note(4.0, "stop")}
DURATIONS = {ElementId("head-1"): 4.0, ElementId("head-2"): 2.0}


# -- the gate ---------------------------------------------------------------

def test_only_note_ink_is_in_the_glowing_list() -> None:
    assert GLOWING_KINDS == {
        ElementKind.NOTEHEAD, ElementKind.SLASH, ElementKind.BAR_REPEAT,
        ElementKind.ACCIDENTAL, ElementKind.LYRIC, ElementKind.TIE}


def test_the_page_furniture_a_note_is_not_stays_out() -> None:
    for kind in (ElementKind.REST, ElementKind.MREST, ElementKind.DYNAMIC,
                 ElementKind.CLEF, ElementKind.KEY_SIG,
                 ElementKind.METER_SIG, ElementKind.TEXT,
                 ElementKind.CHORD_SYMBOL, ElementKind.SLUR,
                 ElementKind.HAIRPIN, ElementKind.BARLINE,
                 ElementKind.STAFF_LINES, ElementKind.GROUP_SYMBOL):
        assert kind not in GLOWING_KINDS


def test_a_slur_is_dark_where_a_tie_glows() -> None:
    # both are clip-revealed spanners; only one of them is a note
    assert ElementKind.TIE in GLOWING_KINDS
    assert ElementKind.SLUR not in GLOWING_KINDS


# -- the shared halo --------------------------------------------------------

def test_attached_ink_takes_the_halo_of_the_head_beside_it() -> None:
    scope = glow_scope(LAYOUT, MAPPING, DURATIONS)
    assert scope.owner[ElementId("accid-1")] == ElementId("head-1")
    assert scope.owner[ElementId("lyric-1")] == ElementId("head-1")


def test_a_tied_chain_follows_its_first_notehead() -> None:
    scope = glow_scope(LAYOUT, MAPPING, DURATIONS)
    assert scope.owner[ElementId("head-2")] == ElementId("head-1")
    assert scope.owner[ElementId("tie")] == ElementId("head-1")
    # the head leading the chain owns its own halo
    assert ElementId("head-1") not in scope.owner


def test_the_leader_burns_for_the_whole_chain() -> None:
    scope = glow_scope(LAYOUT, MAPPING, DURATIONS)
    # 4 beats of its own + a 2-beat continuation
    assert scope.span[ElementId("head-1")] == 6.0


def test_an_untied_note_carries_no_span_at_all() -> None:
    mapping = {ElementId("head-1"): _note(0.0, None),
               ElementId("head-2"): _note(4.0, None)}
    scope = glow_scope(LAYOUT, mapping, DURATIONS)
    assert scope.span == {}
    assert ElementId("head-2") not in scope.owner
    assert ElementId("tie") in scope.owner       # still its head's halo


def test_a_three_link_chain_reaches_the_last_note() -> None:
    layout = Layout(
        pages=LAYOUT.pages,
        elements=LAYOUT.elements + (
            _el("head-3", ElementKind.NOTEHEAD, 6.0, Rect(48, 0, 2, 2)),))
    mapping = {**MAPPING, ElementId("head-2"): _note(4.0, "continue"),
               ElementId("head-3"): _note(6.0, "stop")}
    durations = {**DURATIONS, ElementId("head-3"): 1.0}
    scope = glow_scope(layout, mapping, durations)
    assert scope.owner[ElementId("head-3")] == ElementId("head-1")
    assert scope.span[ElementId("head-1")] == 7.0


def test_one_held_note_in_a_chord_does_not_drag_the_others() -> None:
    """A chord where the top note holds and the bottom one moves on: the
    tie is the top note's alone, matched by pitch the way MusicXML means
    it."""
    layout = Layout(
        pages=LAYOUT.pages,
        elements=LAYOUT.elements + (
            _el("low-1", ElementKind.NOTEHEAD, 0.0, Rect(0, 8, 2, 2)),))
    mapping = {**MAPPING,
               ElementId("low-1"): _note(0.0, None, order=1, octave=3)}
    scope = glow_scope(layout, mapping, {**DURATIONS,
                                         ElementId("low-1"): 4.0})
    assert ElementId("low-1") not in scope.owner
    assert scope.owner[ElementId("head-2")] == ElementId("head-1")


def test_the_nearest_head_wins_in_a_chord() -> None:
    layout = Layout(
        pages=LAYOUT.pages,
        elements=LAYOUT.elements + (
            _el("low-1", ElementKind.NOTEHEAD, 0.0, Rect(0, 8, 2, 2)),
            _el("accid-low", ElementKind.ACCIDENTAL, 0.0, Rect(-4, 8, 2, 2)),
        ))
    mapping = {**MAPPING,
               ElementId("low-1"): _note(0.0, None, order=1, octave=3)}
    scope = glow_scope(layout, mapping, {**DURATIONS,
                                         ElementId("low-1"): 4.0})
    assert scope.owner[ElementId("accid-low")] == ElementId("low-1")
    assert scope.owner[ElementId("accid-1")] == ElementId("head-1")


def test_an_accidental_on_a_continuation_head_follows_the_chain() -> None:
    layout = Layout(
        pages=LAYOUT.pages,
        elements=LAYOUT.elements + (
            _el("accid-2", ElementKind.ACCIDENTAL, 4.0, Rect(20, 0, 2, 2)),))
    scope = glow_scope(layout, MAPPING, DURATIONS)
    # through head-2, not to it: the halo belongs to the chain's start
    assert scope.owner[ElementId("accid-2")] == ElementId("head-1")


def test_ink_with_no_head_of_its_own_keeps_its_halo() -> None:
    layout = Layout(pages=LAYOUT.pages,
                    elements=(_el("lonely", ElementKind.TIE, 9.0),))
    assert glow_scope(layout, {}, {}).owner == {}


def test_followers_reads_the_map_the_other_way() -> None:
    scope = glow_scope(LAYOUT, MAPPING, DURATIONS)
    crew = scope.followers()[ElementId("head-1")]
    assert set(crew) == {ElementId("accid-1"), ElementId("lyric-1"),
                         ElementId("tie"), ElementId("head-2")}


def test_an_empty_scope_says_nothing_about_anything() -> None:
    from scoreanim.core.animation import GlowScope
    assert GlowScope().owner == {}
    assert GlowScope().span == {}
    assert GlowScope().followers() == {}


# -- the real fixtures ------------------------------------------------------

def test_every_tie_on_the_fixture_finds_a_note_to_glow_with(
        engraved, join_mapping, score_model) -> None:
    durations = resolve_durations(engraved.layout, join_mapping,
                                  engraved.note_durations,
                                  score_model.measures)
    scope = glow_scope(engraved.layout, join_mapping, durations)
    ties = [el.identity.element_id for el in engraved.layout.elements
            if el.identity.kind is ElementKind.TIE]
    assert ties, "the fixture is meant to have ties"
    assert all(eid in scope.owner for eid in ties)


def test_a_chain_on_the_fixture_outlasts_its_own_notehead(
        engraved, join_mapping, score_model) -> None:
    durations = resolve_durations(engraved.layout, join_mapping,
                                  engraved.note_durations,
                                  score_model.measures)
    scope = glow_scope(engraved.layout, join_mapping, durations)
    assert scope.span, "the fixture is meant to hold notes over barlines"
    for eid, span in scope.span.items():
        assert span > durations.get(eid, 0.0)


def test_the_fixture_lights_notes_and_leaves_the_rest_dark(
        engraved, join_mapping, score_model) -> None:
    kinds = {el.identity.kind for el in engraved.layout.elements
             if el.identity.kind in GLOWING_KINDS}
    assert ElementKind.NOTEHEAD in kinds
    assert ElementKind.REST not in kinds
    assert ElementKind.METER_SIG not in kinds
