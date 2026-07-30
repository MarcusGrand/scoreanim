"""The label→part join, both halves (M7).

The MEI half (`staff_labels`) reads which staves carry which label text.
The order half (`staff_for_labels`) pairs a system's drawn labels against
those staves. Both are pure, so both are tested on literal inputs here;
that the join holds on real scores is tested end to end in
test_adapter_label_parts.py.

Measurements behind these cases: spikes/label_part.py (the join) and
spikes/label_group.py (group labels drawn first).
"""

from scoreanim.core.engraving.verovio.label_parts import staff_for_labels
from scoreanim.core.engraving.verovio.mei_index import StaffLabel, staff_labels

# Two ordinary parts: staff 1 has both label flavours, staff 2 has only the
# full name — the shape a part with no abbreviation makes, and the whole
# reason the join needs a filter.
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

# The video_test shape: a multi-staff Piano (staves 3-4) whose label hangs
# on the staffGrp around them, between two ordinary parts.
MEI_PIANO = """<?xml version="1.0"?>
<mei xmlns="http://www.music-encoding.org/ns/mei">
  <scoreDef>
    <staffGrp>
      <staffDef n="1"><label>Flute</label><labelAbbr>Fl.</labelAbbr></staffDef>
      <staffDef n="2"><label>Oboe</label><labelAbbr>Ob.</labelAbbr></staffDef>
      <staffGrp>
        <label>Piano</label><labelAbbr>Pno.</labelAbbr>
        <staffDef n="3"/>
        <staffDef n="4"/>
      </staffGrp>
      <staffDef n="5"><label>Bass</label><labelAbbr>Bs.</labelAbbr></staffDef>
    </staffGrp>
  </scoreDef>
</mei>
"""

TABLE = staff_labels(MEI)["label"]
ABBR = staff_labels(MEI)["labelAbbr"]
PIANO = staff_labels(MEI_PIANO)["label"]


# -- the MEI half -----------------------------------------------------------

def test_staff_labels_reads_both_flavours() -> None:
    assert staff_labels(MEI) == {
        "label": (StaffLabel("Alto Sax", (1,), False),
                  StaffLabel("Trumpet", (2,), False)),
        "labelAbbr": (StaffLabel("A. Sx.", (1,), False),)}


def test_a_part_with_no_abbreviation_is_absent_from_the_abbr_list() -> None:
    """THE filter the join depends on: staff 2 draws nothing after system
    1, so it must not be counted when abbreviations are paired."""
    assert [label.text for label in TABLE] == ["Alto Sax", "Trumpet"]
    assert [label.text for label in ABBR] == ["A. Sx."]


def test_a_staffdef_without_n_is_skipped() -> None:
    """@n IS the join — a staffDef without one names no staff."""
    assert all("skipped" not in label.text for label in TABLE)


def test_a_multi_staff_part_hangs_its_label_on_the_group() -> None:
    """The video_test Piano: the label covers both its staves, and it is
    marked as group-hosted because Verovio draws it out of staff order."""
    assert PIANO == (StaffLabel("Flute", (1,), False),
                     StaffLabel("Oboe", (2,), False),
                     StaffLabel("Piano", (3, 4), True),
                     StaffLabel("Bass", (5,), False))


def test_the_outer_group_carries_no_label_of_its_own() -> None:
    """Only groups with a label of their own appear — the outer staffGrp
    that holds the whole score has none, so it contributes nothing."""
    assert sum(1 for label in PIANO if label.on_group) == 1


def test_multi_row_label_text_is_joined() -> None:
    mei = MEI.replace("<label>Trumpet</label>",
                      "<label><rend>Trumpet</rend><lb/><rend>in C</rend></label>")
    assert staff_labels(mei)["label"][1].text == "Trumpetin C"


# -- the order half, ordinary parts -----------------------------------------

def test_full_names_pair_in_order() -> None:
    assert staff_for_labels(["Alto Sax", "Trumpet"], {1, 2}, TABLE) == [1, 2]


def test_the_unabbreviated_part_is_filtered_out() -> None:
    """System 2 draws ONE label — the alto sax's abbreviation. Naive order
    would pair it against staff 1 too, but only by luck: reverse the parts
    and it would name the trumpet. The filter makes it exact."""
    assert staff_for_labels(["A. Sx."], {1, 2}, ABBR) == [1]


def test_a_hidden_staff_drops_its_label_from_the_expected_set() -> None:
    assert staff_for_labels(["Trumpet"], {2}, TABLE) == [2]


def test_a_count_mismatch_refuses_the_whole_system() -> None:
    """Two drawn labels, one labelled staff: order means nothing here, so
    neither label gets a staff. Refusing disables a rename; guessing would
    rename the wrong instrument."""
    assert staff_for_labels(["A. Sx.", "Tpt."], {1, 2}, ABBR) == [None, None]


def test_a_text_disagreement_refuses_only_that_label() -> None:
    assert staff_for_labels(["Alto Sax", "Piccolo"], {1, 2}, TABLE) == [1, None]


def test_whitespace_does_not_count_as_disagreement() -> None:
    """The two sides extract text through different walks (M7.1), so rows
    can join with or without a space. That is not a different instrument."""
    assert staff_for_labels(["AltoSax", "Trum pet"], {1, 2}, TABLE) == [1, 2]


def test_no_labels_drawn_pairs_nothing() -> None:
    assert staff_for_labels([], {1, 2}, TABLE) == []


# -- the order half, a multi-staff part -------------------------------------

def test_a_group_label_is_expected_first() -> None:
    """Measured: Verovio draws every group label ahead of the staff labels,
    41/41 systems (spikes/label_group.py). Plain staff order would put
    'Piano' third and mis-attribute all four."""
    assert staff_for_labels(["Piano", "Flute", "Oboe", "Bass"],
                            {1, 2, 3, 4, 5}, PIANO) == [3, 1, 2, 5]


def test_a_group_label_takes_its_first_visible_staff() -> None:
    """Hiding the piano's upper staff does not unname the part: the label
    still draws, and staff 4 reaches the same part as staff 3."""
    assert staff_for_labels(["Piano", "Flute", "Bass"],
                            {1, 4, 5}, PIANO) == [4, 1, 5]


def test_a_hidden_multi_staff_part_drops_out_entirely() -> None:
    assert staff_for_labels(["Flute", "Oboe", "Bass"],
                            {1, 2, 5}, PIANO) == [1, 2, 5]


def test_staff_order_is_accepted_when_the_texts_confirm_it() -> None:
    """Both candidate orders are checked, so if a future Verovio drew group
    labels in place instead, the texts would say so and the join would
    follow rather than refuse."""
    assert staff_for_labels(["Flute", "Oboe", "Piano", "Bass"],
                            {1, 2, 3, 4, 5}, PIANO) == [1, 2, 3, 5]


def test_neither_order_confirmed_refuses_the_system() -> None:
    """With a group label present, order alone cannot be trusted, so a
    partial match is not good enough — nothing is attributed."""
    assert staff_for_labels(["Piano", "Flute", "Oboe", "Cello"],
                            {1, 2, 3, 4, 5}, PIANO) == [None] * 4
