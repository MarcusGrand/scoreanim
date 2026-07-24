"""Phase 12.3 — prep-seam condensing + schema v5.

Verovio cannot condense from MusicXML, so condensing is a canonical
rewrite BEFORE engraving: contiguous like parts merge onto the first
part's staff as one voice per source player, with a combined label. v1
is naive (ruling d): shared staff, one voice per player, no a2/divisi.
"""

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.project import (AddCondenseGroup, ApplyScoreSetup,
                                    CommandError, CondenseGroup,
                                    EditCondenseGroup, ProjectDoc,
                                    RemoveCondenseGroup, StaffGroup, UndoStack,
                                    from_dict, to_dict)
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.model import build_score_model
from scoreanim.core.score.musicxml_prep import PartCondenseSpec, prepare

from .conftest import CONDENSE_SCORE

_SPEC = PartCondenseSpec(parts=("P1", "P2"), name="Flute 1.2",
                         abbreviation="Fl. 1.2")
_ORDER = ("P1", "P2", "P3", "P4")


# --- prep-seam merge -------------------------------------------------------

def test_merge_collapses_to_one_labelled_part():
    plain = prepare(CONDENSE_SCORE)
    merged = prepare(CONDENSE_SCORE, condense=(_SPEC,))
    assert [p.part_id for p in plain.parts] == ["P1", "P2"]
    assert [p.part_id for p in merged.parts] == ["P1"]         # P2 absorbed
    kept = merged.parts[0]
    assert kept.name == "Flute 1.2" and kept.abbreviation == "Fl. 1.2"


def test_merge_appends_absorbed_part_as_a_second_voice():
    merged = prepare(CONDENSE_SCORE, condense=(_SPEC,))
    import xml.etree.ElementTree as ET
    root = ET.fromstring(merged.canonical_xml)
    parts = root.findall("part")
    assert len(parts) == 1                                     # single staff
    voices = {v.text for v in parts[0].iter("voice")}
    assert voices == {"1", "2"}                                # two players
    # every note now sits on staff 1 (shared staff)
    assert {s.text for s in parts[0].iter("staff")} == {"1"}


def test_empty_name_keeps_the_first_parts_label():
    merged = prepare(CONDENSE_SCORE,
                     condense=(PartCondenseSpec(parts=("P1", "P2"), name=""),))
    assert merged.parts[0].name == "Flute 1"                   # unchanged


def test_condensed_part_engraves_and_joins_completely():
    eng = VerovioEngravingProvider().load_detailed(
        CONDENSE_SCORE, EngravingParams(), condense=(_SPEC,))
    p1 = [r for r in eng.note_records if r.part == "P1"]
    assert sorted({r.voice for r in p1}) == [1, 2]
    assert len(p1) == 72                                       # 36 + 36
    assert not any(r.part == "P2" for r in eng.note_records)
    model = build_score_model(eng.prepared, eng.timeline)
    report = join_notes(model, eng.note_records)
    assert report.is_complete


@pytest.mark.parametrize("spec", [
    PartCondenseSpec(parts=("P1",), name="x"),          # < 2 parts
    PartCondenseSpec(parts=("P1", "P9"), name="x"),     # unknown part
])
def test_bad_condense_specs_raise(spec):
    with pytest.raises(ValueError):
        prepare(CONDENSE_SCORE, condense=(spec,))


# --- document + commands ---------------------------------------------------

def test_add_edit_remove_condense_group_round_trips():
    stack = UndoStack()
    doc = ProjectDoc()
    g1 = CondenseGroup(parts=("P1", "P2"), name="Flute 1.2")
    doc = stack.execute(AddCondenseGroup(g1, _ORDER), doc)
    assert doc.condense_groups == (g1,)
    g2 = CondenseGroup(parts=("P1", "P2"), name="Flutes")
    doc = stack.execute(EditCondenseGroup(0, g2, _ORDER), doc)
    assert doc.condense_groups[0].name == "Flutes"
    doc = stack.execute(RemoveCondenseGroup(0), doc)
    assert doc.condense_groups == ()
    doc = stack.undo()                          # restore the edit
    assert doc.condense_groups == (g2,)
    doc = stack.undo(); doc = stack.undo()
    assert doc.condense_groups == ()            # back to empty


@pytest.mark.parametrize("group, match", [
    (CondenseGroup(parts=("P1",), name="x"), ">= 2"),
    (CondenseGroup(parts=("P1", "P1"), name="x"), "duplicate"),
    (CondenseGroup(parts=("P1", "P3"), name="x"), "contiguous"),
    (CondenseGroup(parts=("P1", "PX"), name="x"), "unknown part"),
])
def test_condense_group_validation(group, match):
    with pytest.raises(CommandError, match=match):
        AddCondenseGroup(group, _ORDER).apply(ProjectDoc())


def test_a_part_cannot_be_in_two_condense_groups():
    doc = AddCondenseGroup(CondenseGroup(parts=("P1", "P2"), name="a"),
                           _ORDER).apply(ProjectDoc())
    with pytest.raises(CommandError, match="already in"):
        AddCondenseGroup(CondenseGroup(parts=("P2", "P3"), name="b"),
                         _ORDER).apply(doc)


# --- schema v5 -------------------------------------------------------------

def test_condense_groups_round_trip_v5():
    doc = ProjectDoc(condense_groups=(
        CondenseGroup(parts=("P1", "P2"), name="Flute 1.2",
                      abbreviation="Fl. 1.2"),))
    payload = to_dict(doc)
    assert payload["version"] >= 5           # the field arrived at v5
    back = from_dict(payload)
    assert back.condense_groups == doc.condense_groups


def test_pre_v5_files_load_without_condensing():
    """A v4 file predates condensing — a missing key defaults to () (no
    condensing is the correct look for older documents)."""
    assert from_dict({"version": 4}).condense_groups == ()


# --- 12.4 batch setup command ----------------------------------------------

def test_apply_score_setup_is_one_undo_step():
    """Condense + staff groups + hide-empty change together in ONE step
    (ruling c), so the slow re-engrave runs once and one undo reverts all."""
    stack = UndoStack()
    doc = ProjectDoc(hide_empty_staves=True)   # a fresh-doc default
    cg = CondenseGroup(parts=("P1", "P2"), name="Flute 1.2")
    sg = StaffGroup(parts=("P3", "P4"), symbol="bracket")
    doc = stack.execute(
        ApplyScoreSetup((cg,), (sg,), False, _ORDER), doc)
    assert doc.condense_groups == (cg,)
    assert doc.staff_groups == (sg,)
    assert doc.hide_empty_staves is False
    reverted = stack.undo()
    assert reverted.condense_groups == () and reverted.staff_groups == ()
    assert reverted.hide_empty_staves is True


def test_apply_score_setup_validates_both_group_sets():
    with pytest.raises(CommandError):        # non-contiguous condense
        ApplyScoreSetup((CondenseGroup(parts=("P1", "P3"), name="x"),),
                        (), False, _ORDER).apply(ProjectDoc())
    with pytest.raises(CommandError):        # overlapping staff group
        ApplyScoreSetup((), (StaffGroup(parts=("P9",)),),
                        False, _ORDER).apply(ProjectDoc())


def test_default_condense_name():
    from scoreanim.ui.score_setup_dialog import default_condense_name
    assert default_condense_name(("Flute 1", "Flute 2")) == "Flute 1.2"
    assert default_condense_name(("Horn (F) 1", "Horn (F) 2",
                                  "Horn (F) 3")) == "Horn (F) 1.2.3"
    assert default_condense_name(("Oboe", "Cor Anglais")) == "Oboe"
