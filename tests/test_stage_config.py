"""default_stage_config maps the fixture's credits to stage text elements
and fits the title block into the band the encoded layout leaves free
above the music (165 page units on the fixture's page 1)."""

import pytest

from scoreanim.core.project.stage_config import (PT_TO_PAGE_UNITS,
                                                 default_stage_config,
                                                 page_content_top)


@pytest.fixture(scope="session")
def content_top(engraved) -> float:
    return page_content_top(engraved.layout)


@pytest.fixture(scope="session")
def stage(engraved, content_top):
    return default_stage_config(engraved.prepared, content_top)


def _one(stage, element_id):
    (el,) = [t for t in stage.texts if t.element_id == element_id]
    return el


def test_front_matter_credits_become_stage_texts(stage) -> None:
    assert {t.element_id for t in stage.texts} == {
        "stage:title", "stage:subtitle", "stage:composer",
        "stage:arranger", "stage:text"}
    assert all(t.page == 1 for t in stage.texts)


def test_page_number_credits_are_skipped(stage) -> None:
    assert all("page" not in t.element_id for t in stage.texts)
    assert all(t.content not in ("2", "3") for t in stage.texts)


def test_block_fits_above_the_top_staff(stage, content_top) -> None:
    # with the header suppressed, Verovio pulls the fixture's top staff
    # to ~138 units: the block must scale down (floored at _MIN_SCALE),
    # preserving relative sizes (title 28pt : subtitle 14pt)
    assert content_top == pytest.approx(138, abs=5)
    title = _one(stage, "stage:title")
    subtitle = _one(stage, "stage:subtitle")
    assert title.font_size < 28 * PT_TO_PAGE_UNITS
    assert title.font_size / subtitle.font_size == pytest.approx(28 / 14)
    for t in stage.texts:
        assert t.y <= content_top + 10     # baselines stay in the band
    assert min(t.y - t.font_size for t in stage.texts) >= 0


def test_full_size_when_room_allows(engraved) -> None:
    stage = default_stage_config(engraved.prepared, content_top=1500.0)
    title = _one(stage, "stage:title")
    assert title.font_size == pytest.approx(28 * PT_TO_PAGE_UNITS)


def test_title_position_and_anchor(stage, engraved) -> None:
    prep = engraved.prepared
    title = _one(stage, "stage:title")
    subtitle = _one(stage, "stage:subtitle")
    assert title.content == "Det var en gang"
    assert title.anchor == "middle"
    assert title.x == pytest.approx(prep.page_width / 2)
    assert subtitle.y > title.y             # subtitle below the title


def test_composer_block_end_anchored(stage, engraved) -> None:
    prep = engraved.prepared
    composer = _one(stage, "stage:composer")
    arranger = _one(stage, "stage:arranger")
    subtitle = _one(stage, "stage:subtitle")
    assert composer.anchor == arranger.anchor == "end"
    assert composer.x == arranger.x
    assert composer.x > 0.9 * prep.page_width
    assert composer.y > subtitle.y          # side block below centered block
    assert arranger.y > composer.y          # arranger sits below composer


def test_left_and_right_columns_share_first_band(stage) -> None:
    # lyricist (left column) and composer (right column) are both first in
    # their column and share a font size, so they land on one baseline
    lyricist = _one(stage, "stage:text")
    composer = _one(stage, "stage:composer")
    assert lyricist.y == pytest.approx(composer.y)


def test_lyricist_keeps_gray(stage) -> None:
    lyricist = _one(stage, "stage:text")
    assert lyricist.content == "Project Lyricist"
    assert lyricist.color == "#C0C0C0"
    assert lyricist.anchor == "start"
