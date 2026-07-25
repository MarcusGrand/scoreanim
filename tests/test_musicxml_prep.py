"""Credit extraction against the fixture's known credit texts
(verified by raw-XML dump, 2026-07-10), and <part-group> injection
(Phase 8, spikes/NOTES.md "Phase 8 — part-group injection")."""

import xml.etree.ElementTree as ET

import pytest

from scoreanim.core.score.musicxml_prep import (
    CreditText, PartGroupSpec, _drop_redundant_trailing_forwards,
    _repaginate, prepare)
from tests.conftest import BAR_REPEAT_SCORE, TESTSCORE


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


# --- repagination with non-numeric measure numbers -------------------------

def _one_part_root(numbers: list[str]) -> ET.Element:
    """A minimal <score-partwise> with one part whose measures carry the
    given `number` attributes (Dorico uses "X0"/"X1" for split/unnumbered
    bars — cadenzas, mid-bar system starts)."""
    root = ET.Element("score-partwise")
    part = ET.SubElement(root, "part", id="P1")
    for n in numbers:
        ET.SubElement(part, "measure", number=n)
    return root


def test_repaginate_survives_non_numeric_measure_numbers() -> None:
    # break_measures live in the decompose's ordinal-fallback space, so a
    # break "before ordinal 3" must land on the 3rd measure regardless of
    # its non-numeric MusicXML number — and must not crash on "X0".
    root = _one_part_root(["1", "2", "3", "X0"])
    _repaginate(root, break_measures=(4,))
    measures = root.find("part").findall("measure")
    breaks = [m.get("number") for m in measures
              if m.find("print") is not None
              and m.find("print").get("new-page") == "yes"]
    assert breaks == ["X0"]  # the 4th measure by ordinal


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


# -- part-text overrides (Phase 9.3, spikes/NOTES.md "Phase 9") ----------------

def _score_part(prep, part_id: str) -> ET.Element:
    root = ET.fromstring(prep.canonical_xml)
    return next(sp for sp in root.find("part-list").iter("score-part")
                if sp.get("id") == part_id)


def test_part_text_override_rewrites_name_and_display() -> None:
    from scoreanim.core.score.musicxml_prep import PartTextSpec
    prep = prepare(TESTSCORE, texts=(PartTextSpec("P4", name="Trombones"),))
    sp = _score_part(prep, "P4")
    assert sp.findtext("part-name") == "Trombones"
    # Verovio reads the display twin and ignores the plain element —
    # both must carry the override (spike Q1)
    (dt,) = sp.find("part-name-display").findall("display-text")
    assert dt.text == "Trombones"
    # abbreviation untouched (None keeps the score's text)
    assert sp.findtext("part-abbreviation") == "Tbn."


def test_part_text_override_sets_abbreviation_and_clears_print_object() -> None:
    from scoreanim.core.score.musicxml_prep import PartTextSpec
    prep = prepare(TESTSCORE,
                   texts=(PartTextSpec("P1", abbreviation="S.A.T. 1"),))
    sp = _score_part(prep, "P1")
    ab = sp.find("part-abbreviation")
    assert ab.text == "S.A.T. 1"
    # print-object="no" suppresses even non-empty text (spike Q2)
    assert ab.get("print-object") is None
    disp = sp.find("part-abbreviation-display")
    assert disp.get("print-object") is None
    (dt,) = disp.findall("display-text")
    assert dt.text == "S.A.T. 1"


def test_part_text_override_unknown_part_raises() -> None:
    from scoreanim.core.score.musicxml_prep import PartTextSpec
    with pytest.raises(ValueError, match="unknown part"):
        prepare(TESTSCORE, texts=(PartTextSpec("P99", name="X"),))


def test_partinfo_reflects_overrides(engraved) -> None:
    from scoreanim.core.score.musicxml_prep import PartTextSpec
    prep = prepare(TESTSCORE, texts=(
        PartTextSpec("P4", name="Trombones", abbreviation="Trb."),))
    p4 = next(p for p in prep.parts if p.part_id == "P4")
    base = next(p for p in engraved.prepared.parts if p.part_id == "P4")
    assert (p4.name, p4.abbreviation) == ("Trombones", "Trb.")
    assert (p4.part_id, p4.first_staff, p4.staff_count) == \
        (base.part_id, base.first_staff, base.staff_count)
    # every other part untouched
    assert [p for p in prep.parts if p.part_id != "P4"] == \
        [p for p in engraved.prepared.parts if p.part_id != "P4"]


def test_partinfo_reads_abbreviation(engraved) -> None:
    by_id = {p.part_id: p for p in engraved.prepared.parts}
    assert by_id["P4"].abbreviation == "Tbn."
    assert by_id["P1"].abbreviation == ""      # empty in the fixture


# --- redundant trailing <forward> removal (hotfix 2026-07-25) ---------------
# Dorico's <backup>/<forward> harmony positioning can leave a measure's
# final timed element a musically no-op <forward>; Verovio materializes it
# as a trailing <space> that lengthens the engraved measure and corrupts
# the timemap beat authority (rule 12).

def _measure_of(*elements: tuple[str, int]) -> ET.Element:
    """A minimal one-part root whose single measure holds the given
    (tag, duration) sequence; returns the root."""
    root = ET.Element("score-partwise")
    part = ET.SubElement(root, "part", id="P1")
    measure = ET.SubElement(part, "measure", number="1")
    for tag, dur in elements:
        el = ET.SubElement(measure, tag)
        ET.SubElement(el, "duration").text = str(dur)
    return root


def _timed_tags(root: ET.Element) -> list[str]:
    measure = root.find("part").find("measure")
    return [el.tag for el in measure
            if el.tag in ("note", "backup", "forward")]


def test_drop_redundant_trailing_forward() -> None:
    # the grieg shape: last chord symbol on the last note — the closing
    # forward lands exactly at the filled length
    root = _measure_of(("note", 48), ("backup", 48), ("forward", 48))
    assert _drop_redundant_trailing_forwards(root) == 1
    assert _timed_tags(root) == ["note", "backup"]


def test_keep_trailing_forward_past_filled_position() -> None:
    # a forward advancing PAST the filled length is real content — a
    # bar-repeat measure is exactly one such forward (rule 10)
    root = _measure_of(("note", 24), ("forward", 24))
    assert _drop_redundant_trailing_forwards(root) == 0
    assert _timed_tags(root) == ["note", "forward"]


def test_keep_forward_followed_by_note() -> None:
    # not trailing: the forward positions a later note
    root = _measure_of(("forward", 24), ("note", 24))
    assert _drop_redundant_trailing_forwards(root) == 0
    assert _timed_tags(root) == ["forward", "note"]


def test_drop_two_stacked_redundant_forwards() -> None:
    root = _measure_of(("note", 48), ("backup", 48),
                       ("forward", 24), ("forward", 24))
    assert _drop_redundant_trailing_forwards(root) == 2
    assert _timed_tags(root) == ["note", "backup"]


def test_bar_repeat_forwards_survive_prepare() -> None:
    # guard on the prepped XML itself, not just the timeline: the five
    # bar-repeat measures of bar_repeat_min are each exactly one
    # whole-measure <forward>, and every one must survive the pass
    prep = prepare(BAR_REPEAT_SCORE)
    forwards = ET.fromstring(prep.canonical_xml).iter("forward")
    assert len(list(forwards)) == 5


def test_grieg_timeline_is_uncorrupted(engraved_grieg) -> None:
    # regression: without the pass, the phantom trailing <space>s engrave
    # P3 mm.5/7/9/13 as 6 beats instead of 4 and score_end as 58.0
    tl = engraved_grieg.timeline
    assert sorted(tl.durations) == list(range(1, 14))     # 13 measures
    assert all(d == 4.0 for d in tl.durations.values())
    assert tl.score_end == 52.0
