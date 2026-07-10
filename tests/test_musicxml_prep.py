"""Credit extraction against the fixture's known credit texts
(verified by raw-XML dump, 2026-07-10)."""

import pytest

from scoreanim.core.score.musicxml_prep import CreditText


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
