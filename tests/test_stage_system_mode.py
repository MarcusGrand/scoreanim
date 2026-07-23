"""System-at-a-time stage framing (Phase 7.4), offscreen: the letterbox
mask hides same-page neighbour systems at any window aspect, and
clear_band restores paged behavior."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRectF  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.engraving.systems import system_bands  # noqa: E402
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.render.scene import ScoreScenes  # noqa: E402
from scoreanim.ui.stage_view import _LETTERBOX, StageView  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def scenes(qapp, engraved) -> ScoreScenes:
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    return ScoreScenes(engraved.layout, stage)


def _qrect(rect) -> QRectF:
    return QRectF(rect.x, rect.y, rect.w, rect.h)


def _pixel(view: StageView, scene_x: float, scene_y: float) -> QColor | None:
    """Rendered viewport color at a scene point, None if not exposed."""
    image = view.viewport().grab().toImage()
    pt: QPoint = view.mapFromScene(QPointF(scene_x, scene_y))
    if not (0 <= pt.x() < image.width() and 0 <= pt.y() < image.height()):
        return None
    return image.pixelColor(pt)


@pytest.mark.parametrize("size", [(1920, 400), (400, 1000)])
def test_neighbour_system_never_bleeds(qapp, engraved, scenes, size) -> None:
    """Page 2 carries systems 2 and 3: with system 2 framed, any exposed
    part of system 3 must read as letterbox, while system 2's own band
    shows page (non-letterbox) pixels — at a wide AND a tall aspect."""
    bands = {b.system: b for b in system_bands(engraved.layout)}
    assert bands[2].page == bands[3].page == 2
    view = StageView()
    view.resize(*size)
    view.show_system_band(scenes.scene_for_page(2), _qrect(bands[2].rect))

    own = bands[2].rect
    inside = _pixel(view, own.center.x, own.center.y)
    assert inside is not None
    assert inside.name() != _LETTERBOX.name()

    neighbour = bands[3].rect
    exposed_any = False
    # sample a horizontal run through the neighbour band's center line
    for frac in (0.2, 0.35, 0.5, 0.65, 0.8):
        color = _pixel(view, neighbour.x + frac * neighbour.w,
                       neighbour.center.y)
        if color is None:
            continue                     # not exposed at this aspect: fine
        exposed_any = True
        assert color.name() == _LETTERBOX.name()
    tall = size[1] > size[0]
    if tall:
        # the tall window definitely exposes the scene below the band —
        # the masking must actually have been exercised
        assert exposed_any


def test_system_frame_is_page_sized_and_band_centered(qapp, engraved,
                                                      scenes) -> None:
    """Phase 10R framing: the fitted region is a PAGE-SIZED window
    centered on the band — the view scale matches fitting the page
    itself (the frame never changes shape between modes) and the band's
    center maps to the viewport center."""
    bands = {b.system: b for b in system_bands(engraved.layout)}
    band = bands[2]
    scene = scenes.scene_for_page(2)
    page = scene.sceneRect()

    view = StageView()
    view.resize(600, 850)                # roughly page-shaped viewport
    view.viewport().grab()               # force offscreen layout/resize
    view.show_scene(scene)               # paged fit
    paged_scale = view.transform().m11()
    view.show_system_band(scene, _qrect(band.rect))
    assert view.transform().m11() == pytest.approx(paged_scale, rel=1e-6)

    # ±4 px: fitInView's internal 2 px margin + integer scroll positions
    center = view.mapFromScene(QPointF(page.center().x(),
                                       band.rect.y + band.rect.h / 2))
    assert center.x() == pytest.approx(view.viewport().width() / 2, abs=4)
    assert center.y() == pytest.approx(view.viewport().height() / 2, abs=4)


def test_live_zoom_is_constant_across_systems(qapp, engraved, scenes) -> None:
    """Phase 10R: the frame keeps the page's size, so the view zoom is
    IDENTICAL for every system however its band height differs — the
    system is just singled out and centered, the canvas never resizes
    (the user's requirement, live side)."""
    bands = {b.system: b for b in system_bands(engraved.layout)}
    heights = {s: round(b.rect.h) for s, b in bands.items()}
    assert len(set(heights.values())) > 1     # bands really differ in height
    view = StageView()
    view.resize(600, 850)
    view.viewport().grab()
    zooms = set()
    for system, band in bands.items():
        view.show_system_band(scenes.scene_for_page(band.page),
                              _qrect(band.rect))
        zooms.add(round(view.transform().m11(), 6))
    assert len(zooms) == 1, f"zoom varied across systems: {zooms}"


def test_clear_band_restores_paged_framing(qapp, engraved, scenes) -> None:
    bands = {b.system: b for b in system_bands(engraved.layout)}
    view = StageView()
    view.resize(400, 1000)
    view.show_system_band(scenes.scene_for_page(2), _qrect(bands[2].rect))
    view.clear_band()
    # neighbour ink is visible again (white page, not letterbox)
    neighbour = bands[3].rect
    color = _pixel(view, neighbour.center.x, neighbour.center.y)
    assert color is not None
    assert color.name() != _LETTERBOX.name()
