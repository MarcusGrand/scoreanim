"""Credit extraction against the fixture's known credit texts
(verified by raw-XML dump, 2026-07-10), and <part-group> injection
(Phase 8, spikes/NOTES.md "Phase 8 — part-group injection")."""

import xml.etree.ElementTree as ET

import pytest

from scoreanim.core.score.musicxml_prep import (CreditText, PartGroupSpec,
                                                prepare)
from tests.conftest import TESTSCORE


def _by_type(credits: tuple[CreditText, ...], ctype: str | None,
             page: int = 1) -> list[CreditText]:
    return [c for c in credits if c.credit_type == ctype and c.page == page]


def test_fixture_has_all_nine_credit_words(engraved) -> None:
    assert len(engraved.prepared.credits) == 9


def test_title_credit(engraved) -> None:
    (title,) = _by_type(engraved.prepared.credits, "title")
    assert title.text == "Det var en gang"
    assert title.font_size_pt == 28
    assert title.justify == "center"
    assert title.color is None


def test_composer_and_arranger_are_right_justified(engraved) -> None:
    (composer,) = _by_type(engraved.prepared.credits, "composer")
    (arranger,) = _by_type(engraved.prepared.credits, "arranger")
    assert composer.text == "Edvard Grieg"
    assert arranger.text == "Arr. Marcus Grand"
    assert composer.justify == arranger.justify == "right"
    assert composer.font_size_pt == arranger.font_size_pt == 10


def test_untyped_lyricist_keeps_gray_color(engraved) -> None:
    (lyricist,) = _by_type(engraved.prepared.credits, None)
    assert lyricist.text == "Project Lyricist"
    assert lyricist.color == "#C0C0C0"
    assert lyricist.justify == "left"


def test_page_number_credits_carry_their_page(engraved) -> None:
    pages = {c.page for c in engraved.prepared.credits
             if c.credit_type == "page number"}
    assert pages == {2, 3}


def test_units_per_tenth_matches_page_geometry(engraved) -> None:
    prep = engraved.prepared
    # fixture <defaults>: 5.99722 mm = 40 tenths, page-width 1397.65 tenths
    assert prep.units_per_tenth == pytest.approx(5.99722 / 40 * 10)
    assert prep.page_width == pytest.approx(1397.65 * prep.units_per_tenth)


# --- <part-group> injection (Phase 8) ---------------------------------------

def _part_list_shape(canonical_xml: str) -> list[tuple[str, str]]:
    """[(tag, id-or-number), ...] for the part-list children, in order."""
    part_list = ET.fromstring(canonical_xml).find("part-list")
    return [(el.tag, el.get("id") or el.get("number") or "")
            for el in part_list]


def test_prepare_without_groups_injects_nothing(engraved) -> None:
    assert "part-group" not in engraved.prepared.canonical_xml


def test_single_group_start_stop_placement() -> None:
    prep = prepare(TESTSCORE, (PartGroupSpec(parts=("P1", "P2")),))
    shape = _part_list_shape(prep.canonical_xml)
    assert shape[:4] == [("part-group", "1"), ("score-part", "P1"),
                         ("score-part", "P2"), ("part-group", "1")]
    assert [t for t, _ in shape].count("part-group") == 2

    start = ET.fromstring(prep.canonical_xml).find(
        "./part-list/part-group[@type='start']")
    assert start.findtext("group-symbol") == "bracket"
    assert start.findtext("group-barline") == "yes"


def test_two_groups_numbered_distinctly() -> None:
    prep = prepare(TESTSCORE, (PartGroupSpec(parts=("P1", "P2")),
                               PartGroupSpec(parts=("P5", "P6"),
                                             symbol="square")))
    groups = ET.fromstring(prep.canonical_xml).findall(
        "./part-list/part-group[@type='start']")
    assert [g.get("number") for g in groups] == ["1", "2"]
    assert [g.findtext("group-symbol") for g in groups] == \
        ["bracket", "square"]


def test_join_barlines_false_writes_no() -> None:
    prep = prepare(TESTSCORE, (PartGroupSpec(parts=("P3", "P4"),
                                             join_barlines=False),))
    start = ET.fromstring(prep.canonical_xml).find(
        "./part-list/part-group[@type='start']")
    assert start.findtext("group-barline") == "no"


def test_injection_leaves_part_extraction_untouched(engraved) -> None:
    prep = prepare(TESTSCORE, (PartGroupSpec(parts=("P1", "P2")),))
    assert prep.parts == engraved.prepared.parts


def test_inject_rejects_unknown_part() -> None:
    with pytest.raises(ValueError, match="unknown part"):
        prepare(TESTSCORE, (PartGroupSpec(parts=("P1", "P99")),))


def test_inject_rejects_noncontiguous_parts() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        prepare(TESTSCORE, (PartGroupSpec(parts=("P1", "P3")),))
    with pytest.raises(ValueError, match="contiguous"):
        prepare(TESTSCORE, (PartGroupSpec(parts=("P2", "P1")),))
