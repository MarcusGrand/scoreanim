"""The label→part join, both halves (M7).

The MEI half (`staffdef_labels`) reads which staff carries which label
text. The order half (`staff_for_labels`) pairs a system's drawn labels
against those staves. Both are pure, so both are tested on literal inputs
here; that the join holds on real scores is tested end to end in
test_adapter_label_parts.py.

Measurements behind these cases: spikes/label_part.py.
"""

from scoreanim.core.engraving.verovio.label_parts import staff_for_labels
from scoreanim.core.engraving.verovio.mei_index import staffdef_labels

# Two staves: staff 1 has both label flavours, staff 2 has only the full
# name — the shape a part with no abbreviation makes, and the whole reason
# the join needs a filter.
MEI = """<?xml version="1.0"?>
<mei xmlns="http://www.music-encoding.org/ns/mei">
  <scoreDef>
    <staffGrp>
      <staffDef n="1"><label>Alto Sax</label><labelAbbr>A. Sx.</labelAbbr></staffDef>
      <staffDef n="2"><label>Trumpet</label></staffDef>
      <staffDef><label>No number, skipped</label></staffDef>
    </staffGrp>
  </scoreDef>
</mei>
"""


# -- the MEI half -----------------------------------------------------------

def test_staffdef_labels_reads_both_flavours() -> None:
    assert staffdef_labels(MEI) == {
        (1, "label"): "Alto Sax",
        (1, "labelAbbr"): "A. Sx.",
        (2, "label"): "Trumpet",
    }


def test_a_part_with_no_abbreviation_has_no_labelabbr_entry() -> None:
    """THE filter the join depends on: staff 2 draws nothing after system
    1, so it must not be counted when labelAbbrs are paired."""
    table = staffdef_labels(MEI)
    assert (2, "label") in table
    assert (2, "labelAbbr") not in table


def test_a_staffdef_without_n_is_skipped() -> None:
    """@n IS the join — a staffDef without one names no staff."""
    assert "No number, skipped" not in staffdef_labels(MEI).values()


def test_multi_row_label_text_is_joined() -> None:
    mei = MEI.replace("<label>Trumpet</label>",
                      "<label><rend>Trumpet</rend><lb/><rend>in C</rend></label>")
    assert staffdef_labels(mei)[(2, "label")] == "Trumpetin C"


# -- the order half ---------------------------------------------------------

TABLE = staffdef_labels(MEI)


def test_full_names_pair_in_order() -> None:
    assert staff_for_labels(["Alto Sax", "Trumpet"], [1, 2], TABLE,
                            "label") == [1, 2]


def test_the_unabbreviated_part_is_filtered_out() -> None:
    """System 2 draws ONE label — the alto sax's abbreviation. Naive order
    would pair it against staff 1 too, but only by luck: reverse the parts
    and it would name the trumpet. The filter makes it exact."""
    assert staff_for_labels(["A. Sx."], [1, 2], TABLE, "labelAbbr") == [1]


def test_the_filter_survives_hidden_staves() -> None:
    """Staff 1 hidden on this system: the only visible labelled staff is
    2, which carries no labelAbbr, so nothing is drawn and nothing pairs."""
    assert staff_for_labels([], [2], TABLE, "labelAbbr") == []


def test_a_count_mismatch_refuses_the_whole_system() -> None:
    """Two drawn labels, one labelled staff: order means nothing here, so
    neither label gets a staff. Refusing disables a rename; guessing would
    rename the wrong instrument."""
    assert staff_for_labels(["A. Sx.", "Tpt."], [1, 2], TABLE,
                            "labelAbbr") == [None, None]


def test_a_text_disagreement_refuses_only_that_label() -> None:
    assert staff_for_labels(["Alto Sax", "Piccolo"], [1, 2], TABLE,
                            "label") == [1, None]


def test_whitespace_does_not_count_as_disagreement() -> None:
    """The two sides extract text through different walks (M7.1), so rows
    can join with or without a space. That is not a different instrument."""
    assert staff_for_labels(["AltoSax", "Trum pet"], [1, 2], TABLE,
                            "label") == [1, 2]


def test_no_labels_drawn_pairs_nothing() -> None:
    assert staff_for_labels([], [1, 2], TABLE, "label") == []
