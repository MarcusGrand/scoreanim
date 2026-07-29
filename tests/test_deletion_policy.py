"""The delete policy, headless on synthetic selections and doc maps.

The `tests/test_break_policy.py` shape: pure core logic on hand-built
inputs, no engraving and no Qt. What the policy DOES with a selection
is the question here; that hiding actually removes ink is pinned in
tests/test_render_scene.py and tests/test_delete_action.py.

The load-bearing case is the last section: an engraved text hidden
BEHIND a stage overlay is not a deleted element, and must never reach
the readout — restoring it would put the engraved mark back underneath
the replacement text.
"""
from __future__ import annotations

import pytest

from scoreanim.core.editing.deletion import (ALREADY_DELETED, MUSIC_INK,
                                             NO_SELECTION, NOT_DELETABLE,
                                             SCAFFOLD_INK, DELETABLE_KINDS,
                                             deleted_families, deleted_ids,
                                             describe, is_deletable,
                                             overlaid_ids, resolve)
from scoreanim.core.project.document import LayoutOverride
from scoreanim.core.project.stage_config import OVERLAY_PREFIX
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind)
from scoreanim.core.selection.context import Selection


def _selection(kind: ElementKind, eid: str = "P1:m4:s1:v1:hairpin:0"
               ) -> Selection:
    return Selection(ElementIdentity(
        element_id=ElementId(eid), kind=kind, part=None, part_name=None,
        staff=1, voice=1, onset=0.0))


def _hidden(*eids: str) -> dict:
    return {ElementId(e): LayoutOverride(hidden=True) for e in eids}


# -- what may be deleted ----------------------------------------------------

@pytest.mark.parametrize("kind", sorted(DELETABLE_KINDS, key=str))
def test_deletable_kinds_resolve_to_the_selected_id(kind):
    action = resolve(_selection(kind))
    assert action.enabled
    assert action.reason is None
    assert action.element_id == ElementId("P1:m4:s1:v1:hairpin:0")


def test_the_deletable_set_is_exactly_the_four_ruled_kinds():
    """A kind added here without the ruling behind it is the failure
    this pin exists to catch (see the module docstring in
    core/editing/deletion.py)."""
    assert DELETABLE_KINDS == {ElementKind.TEXT, ElementKind.SLUR,
                               ElementKind.HAIRPIN, ElementKind.DYNAMIC}


@pytest.mark.parametrize("kind", [
    ElementKind.NOTEHEAD, ElementKind.STEM, ElementKind.BEAM,
    ElementKind.FLAG, ElementKind.ACCIDENTAL, ElementKind.LEDGER_LINES,
    ElementKind.REST, ElementKind.MREST, ElementKind.TIE,
    ElementKind.SLASH, ElementKind.BAR_REPEAT, ElementKind.ARTICULATION,
])
def test_music_ink_is_never_deletable(kind):
    action = resolve(_selection(kind))
    assert not action.enabled
    assert action.reason == MUSIC_INK
    assert not is_deletable(kind)


@pytest.mark.parametrize("kind", [
    ElementKind.STAFF_LINES, ElementKind.BARLINE,
    ElementKind.GROUP_SYMBOL, ElementKind.SYSTEM_DIVIDER,
])
def test_scaffold_is_never_deletable(kind):
    action = resolve(_selection(kind))
    assert not action.enabled
    assert action.reason == SCAFFOLD_INK


@pytest.mark.parametrize("kind", [
    ElementKind.CLEF, ElementKind.KEY_SIG, ElementKind.METER_SIG,
    ElementKind.LYRIC, ElementKind.CHORD_SYMBOL, ElementKind.OTHER,
])
def test_everything_else_is_not_deletable_in_v1(kind):
    assert resolve(_selection(kind)).reason == NOT_DELETABLE


def test_no_selection_says_what_to_select():
    action = resolve(None)
    assert not action.enabled
    assert action.reason == NO_SELECTION


def test_deleting_the_same_thing_twice_is_refused_by_name():
    selection = _selection(ElementKind.HAIRPIN)
    action = resolve(selection, {ElementId("P1:m4:s1:v1:hairpin:0")})
    assert action.reason == ALREADY_DELETED


# -- what has been deleted --------------------------------------------------

def test_one_family_is_one_entry():
    """A hairpin broken over three systems is ONE deleted object."""
    overrides = _hidden("P1:m4:s1:v1:hairpin:0",
                        "P1:m4:s1:v1:hairpin:0:seg1",
                        "P1:m4:s1:v1:hairpin:0:seg2")
    families = deleted_families(overrides)
    assert len(families) == 1
    assert families[0] == (ElementId("P1:m4:s1:v1:hairpin:0"),
                           ElementId("P1:m4:s1:v1:hairpin:0:seg1"),
                           ElementId("P1:m4:s1:v1:hairpin:0:seg2"))
    assert len(deleted_ids(overrides)) == 3


def test_entries_are_in_score_order_with_furniture_last():
    overrides = _hidden("P2:m9:s1:v1:dynamic:0", "score:p1:text:0",
                        "P1:m2:s1:v1:text:0")
    assert [f[0] for f in deleted_families(overrides)] == [
        ElementId("P1:m2:s1:v1:text:0"),
        ElementId("P2:m9:s1:v1:dynamic:0"),
        ElementId("score:p1:text:0"),
    ]


def test_a_visible_override_is_not_a_deletion():
    overrides = {ElementId("P1:m2:s1:v1:text:0"): LayoutOverride(dx=3.0),
                 ElementId("P1:m4:s1:v1:slur:0"): LayoutOverride(hidden=True)}
    assert deleted_ids(overrides) == (ElementId("P1:m4:s1:v1:slur:0"),)


def test_a_text_hidden_behind_an_overlay_is_replaced_not_deleted():
    """The one subtlety: restoring an overlaid text would leave the
    engraved mark AND its replacement on screen at once."""
    engraved = "P1:m1:s1:v1:text:0"
    overrides = _hidden(engraved, "P1:m4:s1:v1:hairpin:0")
    stage_ids = [OVERLAY_PREFIX + engraved, "stage:title"]
    assert overlaid_ids(stage_ids) == {ElementId(engraved)}
    assert deleted_ids(overrides, stage_ids) == (
        ElementId("P1:m4:s1:v1:hairpin:0"),)
    # ... and it IS listed once the overlay is gone
    assert ElementId(engraved) in deleted_ids(overrides, [])


def test_a_deleted_element_that_is_also_nudged_still_lists():
    overrides = {ElementId("P1:m4:s1:v1:hairpin:0"):
                 LayoutOverride(dx=2.0, dy=-1.0, hidden=True)}
    assert deleted_ids(overrides) == (ElementId("P1:m4:s1:v1:hairpin:0"),)


# -- how a row reads --------------------------------------------------------

@pytest.mark.parametrize("eid,text", [
    ("P1:m12:s1:v1:hairpin:0", "m12: hairpin (P1)"),
    ("P1:m12:s1:v1:hairpin:0:seg1", "m12: hairpin (P1)"),
    ("P2:m1:s1:v1:dynamic:3", "m1: dynamic (P2)"),
    ("score:m3:barline:0", "m3: barline"),
    ("score:p1:text:0", "page 1: text"),
    ("score:sys3:text:1", "text"),
    ("P1:m2:s1:v1:key_sig:0", "m2: key sig (P1)"),
])
def test_describe_reads_the_id_grammar(eid, text):
    assert describe(ElementId(eid)) == text
