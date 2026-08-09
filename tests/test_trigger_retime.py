"""Trigger re-timing policy: which elements may carry an override, and
which stored overrides are inert (core/animation/retime.py)."""
from __future__ import annotations

from scoreanim.core.animation import (ANCHOR_KINDS, ANIMATED_KINDS,
                                      RETIMEABLE_KINDS,
                                      inert_trigger_overrides, is_retimeable)
from scoreanim.core.engraving.types import (Layout, PageGeometry, Point, Rect,
                                            RenderedElement, RenderPrimitive)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)


def _el(eid: str, kind: ElementKind,
        onset: float | None) -> RenderedElement:
    ident = ElementIdentity(ElementId(eid), kind, PartId("P1"), "Part",
                            1, 1, onset)
    return RenderedElement(ident, 1, 0.0, 0.0, Rect(0, 0, 1, 1),
                           Point(0, 0), RenderPrimitive(paths=()))


def _layout(*elements: RenderedElement) -> Layout:
    return Layout(pages=(PageGeometry(1, 100.0, 100.0),), elements=elements)


def test_retimeable_kinds_are_derived() -> None:
    """The set is exactly the animated kinds minus the reveal anchors —
    derived, so a new ElementKind is retimeable by default."""
    assert RETIMEABLE_KINDS == ANIMATED_KINDS - ANCHOR_KINDS
    assert RETIMEABLE_KINDS.isdisjoint(ANCHOR_KINDS)


def test_membership_matches_the_ruling() -> None:
    for kind in (ElementKind.DYNAMIC, ElementKind.TEXT, ElementKind.CLEF,
                 ElementKind.STEM, ElementKind.LYRIC, ElementKind.OTHER):
        assert kind in RETIMEABLE_KINDS
    for kind in (ElementKind.NOTEHEAD, ElementKind.REST, ElementKind.MREST,
                 ElementKind.SLASH, ElementKind.BAR_REPEAT,
                 ElementKind.SLUR, ElementKind.TIE, ElementKind.HAIRPIN,
                 ElementKind.BARLINE, ElementKind.STAFF_LINES):
        assert kind not in RETIMEABLE_KINDS


def test_is_retimeable_needs_an_onset() -> None:
    """An onset-less element of a retimeable kind (page furniture) has
    no trigger to move."""
    assert is_retimeable(_el("d0", ElementKind.DYNAMIC, 2.0).identity)
    assert not is_retimeable(_el("d1", ElementKind.DYNAMIC, None).identity)
    assert not is_retimeable(_el("n0", ElementKind.NOTEHEAD, 2.0).identity)


def test_inert_overrides_flag_unknown_anchor_and_onsetless() -> None:
    layout = _layout(_el("d0", ElementKind.DYNAMIC, 2.0),
                     _el("n0", ElementKind.NOTEHEAD, 2.0),
                     _el("t0", ElementKind.TEXT, None))
    overrides = {ElementId("d0"): 4.0,     # fine — not reported
                 ElementId("gone"): 1.0,   # id not in this layout
                 ElementId("n0"): 3.0,     # a reveal anchor
                 ElementId("t0"): 3.0}     # onset-less
    assert inert_trigger_overrides(layout, overrides) == (
        (ElementId("gone"), "no such element"),
        (ElementId("n0"), "cannot be re-timed"),
        (ElementId("t0"), "cannot be re-timed"),
    )


def test_inert_overrides_empty_for_a_clean_map() -> None:
    layout = _layout(_el("d0", ElementKind.DYNAMIC, 2.0))
    assert inert_trigger_overrides(layout, {}) == ()
    assert inert_trigger_overrides(layout, {ElementId("d0"): 8.0}) == ()
