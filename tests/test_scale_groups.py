"""Where a scale effect pivots (core/animation/scale_groups.py).

A note scales as one object: head, stem, flag, beam, ledger dashes,
accidental, dots and articulations all pivot on the centre of the
noteheads in their rule-3 group. Synthetic layouts pin the policy; the
real fixture checks it end to end, including that a beamed group's beam
belongs to the FIRST note.
"""
from __future__ import annotations

from scoreanim.core.animation import (NOTE_OWNED_KINDS, SCALABLE_KINDS,
                                      quantize_beats, scale_pivots)
from scoreanim.core.engraving.types import (Layout, PageGeometry, Point, Rect,
                                            RenderedElement, RenderPrimitive)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)


def _el(eid: str, kind: ElementKind, onset: float | None,
        box: Rect = Rect(0, 0, 2, 2), voice: int | None = 1
        ) -> RenderedElement:
    ident = ElementIdentity(ElementId(eid), kind, PartId("P1"), "Part",
                            1, voice, onset)
    return RenderedElement(ident, 1, box.x, box.y, box, box.center,
                           RenderPrimitive(paths=()))


def _synthetic() -> dict[ElementId, Point]:
    layout = Layout(
        pages=(PageGeometry(1, 100.0, 100.0),),
        elements=(
            # a two-note chord at beat 0: heads at y 0-2 and y 8-10, so
            # their shared centre sits at (1, 5)
            _el("head-low", ElementKind.NOTEHEAD, 0.0, Rect(0, 0, 2, 2)),
            _el("head-high", ElementKind.NOTEHEAD, 0.0, Rect(0, 8, 2, 2)),
            _el("stem", ElementKind.STEM, 0.0, Rect(2, 0, 1, 10)),
            _el("accid", ElementKind.ACCIDENTAL, 0.0, Rect(-4, 0, 2, 2)),
            _el("dot", ElementKind.OTHER, 0.0, Rect(4, 0, 1, 1)),
            _el("beam", ElementKind.BEAM, 0.0, Rect(2, 20, 30, 1)),
            # ruled at staff size and it stays there (it still fades)
            _el("ledger", ElementKind.LEDGER_LINES, 0.0, Rect(-1, 12, 4, 1)),
            # the next note of the beamed group: its own pivot
            _el("head-2", ElementKind.NOTEHEAD, 0.5, Rect(20, 0, 2, 2)),
            _el("stem-2", ElementKind.STEM, 0.5, Rect(22, 0, 1, 10)),
            # note-owned ink with no head in its group: never scales
            _el("orphan-beam", ElementKind.BEAM, 3.0, Rect(0, 0, 9, 1)),
            # stands on its own
            _el("slash", ElementKind.SLASH, 1.0, Rect(6, 6, 4, 4)),
            _el("rest", ElementKind.REST, 2.0, Rect(0, 0, 2, 2)),
            _el("dynam", ElementKind.DYNAMIC, 0.0, Rect(0, 30, 3, 3),
                voice=None),
            _el("barline", ElementKind.BARLINE, None, Rect(50, 0, 1, 40)),
        ))
    return scale_pivots(layout)


def test_a_note_scales_about_its_heads_centre() -> None:
    pivots = _synthetic()
    centre = Point(1.0, 5.0)               # the chord's two heads together
    for eid in ("head-low", "head-high", "stem", "accid", "dot"):
        assert pivots[ElementId(eid)] == centre, eid


def test_the_beam_pivots_on_the_first_note_of_its_group() -> None:
    """A beam's onset is its group's first note, so it drops with that
    note; the notes after it keep their own pivots."""
    pivots = _synthetic()
    assert pivots[ElementId("beam")] == Point(1.0, 5.0)
    assert pivots[ElementId("head-2")] == Point(21.0, 1.0)
    assert pivots[ElementId("stem-2")] == Point(21.0, 1.0)


def test_note_owned_ink_without_a_head_never_scales() -> None:
    """Scaling a beam about its own middle reads as jitter."""
    assert ElementId("orphan-beam") not in _synthetic()


def test_ink_that_stands_alone_keeps_its_own_centre() -> None:
    pivots = _synthetic()
    assert pivots[ElementId("slash")] == Point(8.0, 8.0)


def test_unscalable_ink_gets_no_pivot() -> None:
    pivots = _synthetic()
    for eid in ("rest", "dynam", "barline"):
        assert ElementId(eid) not in pivots, eid


def test_ledger_lines_never_scale(engraved) -> None:
    """Marcus, 2026-07-31: a ledger line is ruled at staff size and stays
    that size while the note over it drops. Opacity still reaches it —
    that is the applier's other property, not this map's business."""
    assert ElementKind.LEDGER_LINES not in SCALABLE_KINDS
    assert ElementId("ledger") not in _synthetic()
    pivots = scale_pivots(engraved.layout)
    dashes = [el for el in engraved.layout.elements
              if el.identity.kind is ElementKind.LEDGER_LINES]
    assert dashes                                    # the fixture has them
    for el in dashes:
        assert el.identity.element_id not in pivots


def test_the_two_kind_tables_agree() -> None:
    assert NOTE_OWNED_KINDS <= SCALABLE_KINDS
    assert ElementKind.NOTEHEAD not in NOTE_OWNED_KINDS


def test_real_fixture_every_stem_pivots_on_its_head(engraved) -> None:
    pivots = scale_pivots(engraved.layout)
    idents = [el.identity for el in engraved.layout.elements]
    by_key: dict[tuple, list] = {}
    for ident in idents:
        if ident.kind is ElementKind.NOTEHEAD and ident.onset is not None:
            key = (ident.part, ident.staff, ident.voice,
                   quantize_beats(ident.onset))
            by_key.setdefault(key, []).append(ident.element_id)

    stems = [i for i in idents if i.kind is ElementKind.STEM]
    assert stems
    covered = 0
    for ident in stems:
        key = (ident.part, ident.staff, ident.voice,
               quantize_beats(ident.onset))
        heads = by_key.get(key)
        if not heads:
            assert ident.element_id not in pivots     # nothing to scale about
            continue
        covered += 1
        # the stem shares its heads' pivot exactly
        assert pivots[ident.element_id] == pivots[heads[0]]
    assert covered > 100                              # the ordinary case


def test_real_fixture_beams_join_their_first_note(engraved) -> None:
    pivots = scale_pivots(engraved.layout)
    beams = [el for el in engraved.layout.elements
             if el.identity.kind is ElementKind.BEAM]
    assert beams
    placed = [el for el in beams if el.identity.element_id in pivots]
    assert placed                                     # beams do scale now
    for el in placed:
        # the pivot is a notehead group's centre, not the beam's own
        # middle — a long beam pivots well to the left of itself
        assert pivots[el.identity.element_id] != el.anchor


def test_real_fixture_scaffold_is_left_alone(engraved) -> None:
    pivots = scale_pivots(engraved.layout)
    for el in engraved.layout.elements:
        if el.identity.kind in (ElementKind.STAFF_LINES, ElementKind.BARLINE,
                                ElementKind.GROUP_SYMBOL, ElementKind.REST,
                                ElementKind.DYNAMIC, ElementKind.TEXT):
            assert el.identity.element_id not in pivots
