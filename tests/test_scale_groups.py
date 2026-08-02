"""Where a scale effect pivots (core/animation/scale_groups.py).

Every notehead swells about its OWN centre, and the ink hanging off it
follows the head it belongs to: a stem stands on the head at its foot, a
flag rides the stem, an accidental or a dot turns around the nearest
head. Beams and ledger lines never scale at all. Synthetic layouts pin
the policy; the real fixture checks it end to end.
"""
from __future__ import annotations

from scoreanim.core.animation import (HEAD_KINDS, NOTE_OWNED_KINDS,
                                      SCALABLE_KINDS, quantize_beats,
                                      scale_pivots)
from scoreanim.core.engraving.svg_geom import polygon_path, rect_path
from scoreanim.core.engraving.types import (Affine, Layout, PageGeometry,
                                            PathPrimitive, Point, Rect,
                                            RenderedElement, RenderPrimitive)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)


def _el(eid: str, kind: ElementKind, onset: float | None,
        box: Rect = Rect(0, 0, 2, 2), voice: int | None = 1,
        corners: tuple[tuple[float, float], ...] | None = None
        ) -> RenderedElement:
    """One element, drawn as its own box unless `corners` gives a shape —
    a tilted beam is a polygon, and stem_caps reads the real ink."""
    ident = ElementIdentity(ElementId(eid), kind, PartId("P1"), "Part",
                            1, voice, onset)
    d = (polygon_path(" ".join(f"{x},{y}" for x, y in corners))
         if corners else rect_path(box.x, box.y, box.w, box.h))
    glyph = RenderPrimitive(paths=(PathPrimitive(d=d, transform=Affine()),))
    return RenderedElement(ident, 1, box.x, box.y, box, box.center, glyph)


# One beamed two-note chord, one flagged note, and the ink that must be
# left alone. Page coordinates, so y grows DOWNWARD: "high" is the
# smaller y. Both stems point up, and their beam sits above their tips.
LAYOUT = Layout(
    pages=(PageGeometry(1, 100.0, 100.0),),
    elements=(
        # the chord at beat 0: heads centred on (1, 1) and (1, 9)
        _el("head-high", ElementKind.NOTEHEAD, 0.0, Rect(0, 0, 2, 2)),
        _el("head-low", ElementKind.NOTEHEAD, 0.0, Rect(0, 8, 2, 2)),
        # up from the low head (y 9) to the beam (y -20)
        _el("stem", ElementKind.STEM, 0.0, Rect(2, -20, 1, 29)),
        _el("beam", ElementKind.BEAM, 0.0, Rect(2, -22, 10, 2)),
        # one accidental per head, and a dot on the low one
        _el("accid-high", ElementKind.ACCIDENTAL, 0.0, Rect(-4, 0, 2, 2)),
        _el("accid-low", ElementKind.ACCIDENTAL, 0.0, Rect(-4, 8, 2, 2)),
        _el("dot", ElementKind.OTHER, 0.0, Rect(4, 8, 1, 1)),
        # ruled at staff size and it stays there (it still fades)
        _el("ledger", ElementKind.LEDGER_LINES, 0.0, Rect(-1, 12, 4, 1)),
        # a flagged note of its own, well clear of the beam
        _el("head-2", ElementKind.NOTEHEAD, 0.5, Rect(20, 0, 2, 2)),
        _el("stem-2", ElementKind.STEM, 0.5, Rect(22, -20, 1, 21)),
        _el("flag-2", ElementKind.FLAG, 0.5, Rect(23, -20, 3, 5)),
        # note-owned ink with no head in its group: never scales
        _el("orphan-beam", ElementKind.BEAM, 3.0, Rect(0, 0, 9, 1)),
        _el("orphan-stem", ElementKind.STEM, 3.0, Rect(0, 0, 1, 9)),
        # stands on its own
        _el("slash", ElementKind.SLASH, 1.0, Rect(6, 6, 4, 4)),
        _el("rest", ElementKind.REST, 2.0, Rect(0, 0, 2, 2)),
        _el("dynam", ElementKind.DYNAMIC, 0.0, Rect(0, 30, 3, 3),
            voice=None),
        _el("barline", ElementKind.BARLINE, None, Rect(50, 0, 1, 40)),
    ))

HIGH = Point(1.0, 1.0)
LOW = Point(1.0, 9.0)


def test_each_notehead_pops_about_its_own_centre() -> None:
    """Marcus, 2026-08-01: a chord's heads used to share one centre, so
    the outer ones slid sideways as they grew."""
    pivots = scale_pivots(LAYOUT)
    assert pivots[ElementId("head-high")] == HIGH
    assert pivots[ElementId("head-low")] == LOW


def test_a_stem_stands_on_the_head_at_its_foot() -> None:
    """The stem points up, so its foot is on the LOW head — it grows out
    of that head towards the beam."""
    assert scale_pivots(LAYOUT)[ElementId("stem")] == LOW


def test_a_flag_rides_its_stem() -> None:
    pivots = scale_pivots(LAYOUT)
    assert pivots[ElementId("flag-2")] == pivots[ElementId("stem-2")]
    assert pivots[ElementId("flag-2")] == Point(21.0, 1.0)


def test_extras_follow_their_nearest_head() -> None:
    """In a chord an accidental belongs to one head, not to the stack."""
    pivots = scale_pivots(LAYOUT)
    assert pivots[ElementId("accid-high")] == HIGH
    assert pivots[ElementId("accid-low")] == LOW
    assert pivots[ElementId("dot")] == LOW


def test_a_beam_never_scales() -> None:
    """Marcus, 2026-08-01: a beam appears with its note at its engraved
    size. It belongs to several notes at once, so any pivot for it is a
    compromise, and a growing beam drags the eye off the notes."""
    assert ElementKind.BEAM not in SCALABLE_KINDS
    pivots = scale_pivots(LAYOUT)
    for eid in ("beam", "orphan-beam"):
        assert ElementId(eid) not in pivots, eid


def test_note_owned_ink_without_a_head_never_scales() -> None:
    """Scaling a stem about its own middle reads as jitter."""
    assert ElementId("orphan-stem") not in scale_pivots(LAYOUT)


def test_ink_that_stands_alone_keeps_its_own_centre() -> None:
    assert scale_pivots(LAYOUT)[ElementId("slash")] == Point(8.0, 8.0)


def test_unscalable_ink_gets_no_pivot() -> None:
    pivots = scale_pivots(LAYOUT)
    for eid in ("rest", "dynam", "barline"):
        assert ElementId(eid) not in pivots, eid


def test_ledger_lines_never_scale(engraved) -> None:
    """Marcus, 2026-07-31: a ledger line is ruled at staff size and stays
    that size while the note over it drops. Opacity still reaches it —
    that is the applier's other property, not this map's business."""
    assert ElementKind.LEDGER_LINES not in SCALABLE_KINDS
    assert ElementId("ledger") not in scale_pivots(LAYOUT)
    pivots = scale_pivots(engraved.layout)
    dashes = [el for el in engraved.layout.elements
              if el.identity.kind is ElementKind.LEDGER_LINES]
    assert dashes                                    # the fixture has them
    for el in dashes:
        assert el.identity.element_id not in pivots


def test_the_kind_tables_agree() -> None:
    assert ElementKind.NOTEHEAD not in NOTE_OWNED_KINDS
    assert ElementKind.BEAM in NOTE_OWNED_KINDS      # owned, but unscalable
    assert not (HEAD_KINDS & NOTE_OWNED_KINDS)
    assert HEAD_KINDS <= SCALABLE_KINDS


def _heads_by_key(idents) -> dict[tuple, list]:
    by_key: dict[tuple, list] = {}
    for ident in idents:
        if ident.kind is ElementKind.NOTEHEAD and ident.onset is not None:
            key = (ident.part, ident.staff, ident.voice,
                   quantize_beats(ident.onset))
            by_key.setdefault(key, []).append(ident.element_id)
    return by_key


def test_real_fixture_every_head_pops_in_place(engraved) -> None:
    pivots = scale_pivots(engraved.layout)
    heads = [el for el in engraved.layout.elements
             if el.identity.kind is ElementKind.NOTEHEAD]
    assert heads
    for el in heads:
        assert pivots[el.identity.element_id] == el.bbox.center


def test_real_fixture_a_chord_no_longer_shares_one_pivot(engraved) -> None:
    """133 of testscore's 252 note groups are chords — the case that was
    wrong before (2026-08-01)."""
    pivots = scale_pivots(engraved.layout)
    idents = [el.identity for el in engraved.layout.elements]
    chords = [eids for eids in _heads_by_key(idents).values() if len(eids) > 1]
    assert len(chords) > 100
    for eids in chords:
        assert len({pivots[eid] for eid in eids}) == len(eids)


def test_real_fixture_every_stem_pivots_on_one_of_its_heads(engraved) -> None:
    pivots = scale_pivots(engraved.layout)
    idents = [el.identity for el in engraved.layout.elements]
    by_key = _heads_by_key(idents)

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
        assert pivots[ident.element_id] in {pivots[eid] for eid in heads}
    assert covered > 100                              # the ordinary case


def test_real_fixture_no_beam_scales(engraved) -> None:
    pivots = scale_pivots(engraved.layout)
    beams = [el for el in engraved.layout.elements
             if el.identity.kind is ElementKind.BEAM]
    assert beams
    for el in beams:
        assert el.identity.element_id not in pivots


def test_real_fixture_scaffold_is_left_alone(engraved) -> None:
    pivots = scale_pivots(engraved.layout)
    for el in engraved.layout.elements:
        if el.identity.kind in (ElementKind.STAFF_LINES, ElementKind.BARLINE,
                                ElementKind.GROUP_SYMBOL, ElementKind.REST,
                                ElementKind.DYNAMIC, ElementKind.TEXT):
            assert el.identity.element_id not in pivots
