"""The double-click routing policy (M3.1), headless.

Pure: what a text IS decides which existing command edits it. No Qt, no
scene, no document — synthetic identities, the `test_hit_priority.py`
shape.
"""
from __future__ import annotations

import pytest

from scoreanim.core.editing import TextRoute, route_for
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)

P1 = PartId("P1")


def _identity(kind: ElementKind, eid: str = "P1:m1:s1:v1:text:0",
              part: PartId | None = P1) -> ElementIdentity:
    return ElementIdentity(element_id=ElementId(eid), kind=kind, part=part,
                           part_name="Flute", staff=1, voice=1, onset=0.0)


# -- stage texts: identity=None is the whole discriminator ---------------

def test_stage_text_routes_to_edit_stage_text() -> None:
    """D5 stands: a stage text is unselectable (identity is None) but
    IS editable, and that one field is what tells the two families
    apart here."""
    target = route_for(None, ElementId("stage:title"))
    assert target is not None
    assert target.route is TextRoute.STAGE_TEXT
    assert target.element_id == "stage:title"
    assert target.part is None


def test_a_tempo_overlay_is_a_stage_text_not_an_engraved_one() -> None:
    """Once a tempo mark is overlaid, the thing on screen is the
    replacement — editing it again must NOT try to overlay it twice
    (AddTempoOverlay rejects that outright)."""
    target = route_for(None, ElementId("stage:overlay:P1:m1:s1:v0:text:0"))
    assert target.route is TextRoute.STAGE_TEXT


# -- part labels ---------------------------------------------------------

@pytest.mark.parametrize("text_class,field", [("label", "name"),
                                              ("labelAbbr", "abbreviation")])
def test_part_labels_route_to_the_part_name_override(text_class,
                                                     field) -> None:
    """Both label flavours are the SAME document entry, different field
    — so the editor must say which one it is writing or a rename would
    silently clear the abbreviation."""
    target = route_for(_identity(ElementKind.TEXT), ElementId("eid"),
                       text_class)
    assert target.route is TextRoute.PART_LABEL
    assert target.part == P1
    assert target.field == field


def test_a_label_with_no_part_is_not_editable() -> None:
    """Nothing to name: SetPartText is keyed by part."""
    assert route_for(_identity(ElementKind.TEXT, part=None),
                     ElementId("eid"), "label") is None


# -- the generalized overlay ---------------------------------------------

@pytest.mark.parametrize("text_class", ["tempo", "dir", "reh", None])
def test_other_engraved_text_routes_to_the_overlay_mechanism(
        text_class) -> None:
    """The roadmap's "tempo-overlay mechanism generalized": a system
    text or rehearsal mark takes the same hide-plus-replace path a tempo
    mark does, and AddTempoOverlay needs no change to accept it (it
    never looked at text_class)."""
    target = route_for(_identity(ElementKind.TEXT), ElementId("eid"),
                       text_class)
    assert target.route is TextRoute.ENGRAVED_OVERLAY
    assert target.element_id == "eid"


@pytest.mark.parametrize("text_class", ["mNum", "pgHead", "pgFoot"])
def test_page_furniture_is_not_editable_in_place(text_class) -> None:
    """Measure numbers are navigation; the page header/footer is the
    Dorico title-block simplification (BACKLOG 4), and half-solving it
    here would hide the fix somewhere nobody looks."""
    assert route_for(_identity(ElementKind.TEXT), ElementId("eid"),
                     text_class) is None


# -- everything else -----------------------------------------------------

@pytest.mark.parametrize("kind", [ElementKind.NOTEHEAD, ElementKind.HAIRPIN,
                                  ElementKind.BARLINE, ElementKind.DYNAMIC,
                                  ElementKind.STAFF_LINES, ElementKind.SLUR])
def test_non_text_elements_have_no_edit_route(kind) -> None:
    """Double-clicking a notehead does nothing — this is a text
    affordance, not a general inspector."""
    assert route_for(_identity(kind), ElementId("eid"), None) is None
