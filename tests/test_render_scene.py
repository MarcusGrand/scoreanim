"""Scene-builder smoke tests, headless via the offscreen Qt platform.

Visual fidelity is judged by eye (PHASES 2); these pin the mechanical
invariants: registry coverage, per-page counts, path geometry agreement
with core, color tracking, and text placement sanity.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.engraving.svg_geom import path_bbox  # noqa: E402
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import ElementKind, PartId  # noqa: E402
from scoreanim.render.qpath import to_qpainter_path  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _stage(engraved):
    return default_stage_config(engraved.prepared,
                                page_content_top(engraved.layout))


@pytest.fixture(scope="session")
def scenes(qapp, engraved) -> ScoreScenes:
    return ScoreScenes(engraved.layout, _stage(engraved))


def test_registry_covers_every_element_and_stage_text(scenes, engraved) -> None:
    layout_ids = {el.identity.element_id for el in engraved.layout.elements}
    stage_ids = {t.element_id
                 for t in _stage(engraved).texts}
    assert set(scenes.items) == layout_ids | stage_ids


def test_per_page_top_level_item_counts(scenes, engraved) -> None:
    stage = _stage(engraved)
    for page in range(1, scenes.page_count + 1):
        top_level = [i for i in scenes.scene_for_page(page).items()
                     if i.parentItem() is None]
        expected = (sum(1 for e in engraved.layout.elements if e.page == page)
                    + sum(1 for t in stage.texts if t.page == page)
                    + 1)                        # the white page rect
        assert len(top_level) == expected


def test_qpainter_path_bbox_matches_core_path_bbox(engraved) -> None:
    sampled = 0
    for el in engraved.layout.elements:
        for prim in el.glyph.paths[:1]:
            core = path_bbox(prim.d)
            qt = to_qpainter_path(prim.d).boundingRect()
            assert qt.x() == pytest.approx(core.x, abs=1e-6)
            assert qt.y() == pytest.approx(core.y, abs=1e-6)
            assert qt.width() == pytest.approx(core.w, abs=1e-6)
            assert qt.height() == pytest.approx(core.h, abs=1e-6)
            sampled += 1
        if sampled >= 200:
            break
    assert sampled >= 100


def test_set_part_color_flips_exactly_that_parts_playing_ink(
        scenes, engraved) -> None:
    """Tint scope (ruling D, 2026-07-12): what plays, tints — minus
    rests and dynamics. Clefs, signatures, texts, rests, dynamics stay
    black even in the tinted part."""
    from scoreanim.core.animation import takes_part_color

    part = PartId("P3")
    red = QColor("#cc2222")
    black = QColor("#000000")
    scenes.set_part_color(part, red)
    try:
        seen_kinds_tinted = set()
        seen_kinds_black = set()
        for el in engraved.layout.elements:
            item = scenes.items[el.identity.element_id]
            if el.identity.part == part and takes_part_color(el.identity):
                assert item.color == red, el.identity.element_id
                seen_kinds_tinted.add(el.identity.kind)
            else:
                assert item.color == black, el.identity.element_id
                if el.identity.part == part:
                    seen_kinds_black.add(el.identity.kind)
        # the rule bites on real elements of this part, both ways
        assert ElementKind.NOTEHEAD in seen_kinds_tinted
        assert ElementKind.TIE in seen_kinds_tinted
        assert ElementKind.CLEF in seen_kinds_black
        assert ElementKind.DYNAMIC in seen_kinds_black
        assert ElementKind.REST in seen_kinds_black
    finally:
        scenes.set_part_color(part, None)
    assert scenes.items[next(
        el.identity.element_id for el in engraved.layout.elements
        if el.identity.part == part
        and el.identity.kind is ElementKind.NOTEHEAD)].color == black


def test_element_text_items_land_near_their_core_bbox(scenes, engraved) -> None:
    checked = 0
    for el in engraved.layout.elements:
        if not el.glyph.texts or el.identity.kind is not ElementKind.TEXT:
            continue
        item = scenes.items[el.identity.element_id]
        rect = item.boundingRect() | item.childrenBoundingRect()
        scene_rect = item.mapRectToScene(rect)
        # core text bboxes are font-metric estimates; this is a transform-
        # order tripwire, not a fidelity check
        assert abs(scene_rect.center().x() - el.bbox.center.x) < 2 * el.bbox.w + 50
        assert abs(scene_rect.center().y() - el.bbox.center.y) < 2 * el.bbox.h + 50
        checked += 1
    assert checked > 10


def test_stage_title_is_centered_near_top(scenes, engraved) -> None:
    geo = engraved.layout.pages[0]
    from scoreanim.core.score.identity import ElementId
    title = scenes.items[ElementId("stage:title")]
    rect = title.mapRectToScene(title.childrenBoundingRect())
    assert rect.center().x() == pytest.approx(geo.width / 2, rel=0.05)
    assert 0 < rect.top() < 0.15 * geo.height
