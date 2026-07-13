"""Part-label overrides through the engraving pipeline (Phase 9.3,
spikes/NOTES.md "Phase 9"): labels update on every system, the score
shifts to fit, and — THE pin — no existing ElementId moves."""

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio_adapter import VerovioEngravingProvider
from scoreanim.core.score.musicxml_prep import PartTextSpec
from tests.conftest import TESTSCORE

RENAME = (PartTextSpec("P4", name="Trombones", abbreviation="Trb."),)


@pytest.fixture(scope="module")
def engraved_renamed():
    return VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), texts=RENAME)


def _texts_of_class(layout, cls):
    return [el for el in layout.elements if el.text_class == cls]


def _content(el) -> str:
    return "".join(r.content for t in el.glyph.texts for r in t.runs)


def test_labels_update_on_all_systems(engraved_renamed) -> None:
    """The full name on page 1 AND the abbreviated labels on every later
    system re-derive from the same override — the PHASES 9.3 sentence."""
    layout = engraved_renamed.layout
    labels = [_content(el) for el in _texts_of_class(layout, "label")]
    assert "Trombones" in labels
    assert "Tbns." not in labels
    abbrs = [(el.page, _content(el))
             for el in _texts_of_class(layout, "labelAbbr")]
    assert [a for a in abbrs if a[1] == "Trb."] == \
        [(2, "Trb."), (2, "Trb."), (3, "Trb."), (3, "Trb.")]
    assert all(a[1] != "Tbn." for a in abbrs)


def test_element_ids_stable_under_part_rename(engraved,
                                              engraved_renamed) -> None:
    """THE pin (the 8.3 template): a rename changes no element counts,
    so the id set must be IDENTICAL — every override, style rule, and
    tempo overlay keyed on an ElementId survives the re-engrave. (The
    accepted limit lives elsewhere: giving P1/P2 a FIRST abbreviation
    ADDS labelAbbr elements — appended seqs on this fixture, spike Q3 —
    and is out of this pin's scope.)"""
    base_ids = {str(e.identity.element_id) for e in engraved.layout.elements}
    renamed = {str(e.identity.element_id)
               for e in engraved_renamed.layout.elements}
    assert renamed == base_ids


def test_kinds_stable_under_part_rename(engraved, engraved_renamed) -> None:
    base = {str(e.identity.element_id): e.identity.kind
            for e in engraved.layout.elements}
    renamed = {str(e.identity.element_id): e.identity.kind
               for e in engraved_renamed.layout.elements}
    assert renamed == base


def test_score_shifts_to_fit(engraved) -> None:
    """Rule 7 made observable: lengthening the longest part name moves
    the staff ink right — the label column re-derives, the score shifts
    (a re-engrave with changed inputs, not window reflow)."""
    from scoreanim.core.score.identity import ElementKind
    long_rename = (PartTextSpec("P4", name="Trombones and Friends Ensemble"),)
    wide = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), texts=long_rename)

    def staff_min_x(layout):
        return min(e.bbox.x for e in layout.elements
                   if e.page == 1
                   and e.identity.kind is ElementKind.STAFF_LINES)

    assert staff_min_x(wide.layout) > staff_min_x(engraved.layout) + 100


def test_identities_carry_effective_part_name(engraved_renamed) -> None:
    """PartInfo reads the overridden name (prep applies overrides before
    extraction), and identities mint part_name from PartInfo — ids stay
    keyed on part_id, so nothing else moves."""
    p4_names = {e.identity.part_name
                for e in engraved_renamed.layout.elements
                if e.identity.part == "P4"}
    assert p4_names == {"Trombones"}
