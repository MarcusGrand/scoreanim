"""Selection context (M2.8): the object, and what it carries.

Rule 13's model as a type. Pure and headless — no Qt, no scene, no
fixture load: the whole point of core/selection/context.py is that the
context DERIVES from the element id grammar and the minted identity, so
synthetic identities exercise it completely.
"""
from __future__ import annotations

from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)
from scoreanim.core.selection import Selection


def _ident(eid: str, kind: ElementKind = ElementKind.NOTEHEAD,
           part: str | None = "P1", part_name: str | None = "Flute",
           staff: int | None = 1, voice: int | None = 0,
           onset: float | None = 4.0,
           extent: tuple[float, float] | None = None) -> ElementIdentity:
    return ElementIdentity(ElementId(eid), kind,
                           PartId(part) if part else None, part_name,
                           staff, voice, onset, extent)


# -- the object ----------------------------------------------------------

def test_the_object_is_what_was_picked() -> None:
    obj = _ident("P1:m3:s1:v0:notehead:2")
    sel = Selection(obj)
    assert sel.obj is obj
    assert sel.element_id == obj.element_id
    assert sel.kind is ElementKind.NOTEHEAD


def test_selection_is_frozen_and_compares_by_value() -> None:
    """AppState's no-op guard and the panel's refresh both lean on
    equality, and nothing may mutate a selection in place."""
    a = Selection(_ident("P1:m3:s1:v0:notehead:2"))
    b = Selection(_ident("P1:m3:s1:v0:notehead:2"))
    assert a == b
    assert hash(a) == hash(b)


# -- what it carries -----------------------------------------------------

def test_part_comes_from_the_minted_identity() -> None:
    sel = Selection(_ident("P7:m3:s2:v1:dynamic:0", part="P7",
                           part_name="Horn in F"))
    assert sel.part == PartId("P7")
    assert sel.part_name == "Horn in F"


def test_measure_is_derived_from_the_id_grammar() -> None:
    assert Selection(_ident("P1:m12:s1:v0:notehead:2")).measure_ordinal == 12


def test_scaffold_carries_a_measure_but_no_part() -> None:
    """A barline is score-scoped ink IN a measure — rule 13's case: it
    stays selectable as an object and carries the measure, which is
    exactly the handle M5 will read."""
    sel = Selection(_ident("score:m5:barline:0", kind=ElementKind.BARLINE,
                           part=None, part_name=None, staff=None,
                           voice=None, onset=None))
    assert sel.measure_ordinal == 5
    assert sel.part is None


def test_page_furniture_carries_no_measure() -> None:
    """A part label is minted onset-less and page-scoped; there is no
    measure to carry, and None means "genuinely none", not "unknown"."""
    sel = Selection(_ident("score:p1:text:0", kind=ElementKind.TEXT,
                           part=None, part_name=None, staff=None,
                           voice=None, onset=None))
    assert sel.measure_ordinal is None


def test_a_broken_spanner_carries_its_start_measure() -> None:
    """A continuation segment appends :seg<k> to its source's id, so the
    measure it reports is the spanner's START — the right answer for a
    spanner, and the reason the parse is a search, not a split."""
    sel = Selection(_ident("P1:m9:s1:v0:slur:0:seg1", kind=ElementKind.SLUR,
                           extent=(36.0, 44.0)))
    assert sel.measure_ordinal == 9


def test_context_is_derived_on_read_not_stored() -> None:
    """The type stores exactly one thing. Nothing to keep in step, and
    no way to construct a Selection whose context disagrees with its
    object (rule 13: derived, never stored)."""
    from dataclasses import fields

    assert [f.name for f in fields(Selection)] == ["obj"]
