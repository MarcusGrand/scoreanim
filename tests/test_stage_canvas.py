"""The video canvas on the live stage, offscreen: the frame takes the
user's shape, scale crops at the frame edge, clicks stop at the crop,
and the overlay preview paints the video color behind the ink."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRectF  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.engraving.canvas import canvas_view_rect  # noqa: E402
from scoreanim.core.engraving.systems import system_bands  # noqa: E402
from scoreanim.core.project.stage_config import (  # noqa: E402
    VideoCanvas, default_stage_config, page_content_top)
from scoreanim.render.scene import ScoreScenes  # noqa: E402
from scoreanim.ui.stage_view import _LETTERBOX, StageView  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def scenes(qapp, engraved) -> ScoreScenes:
    # function-scoped: overlay-preview tests toggle scene state
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    return ScoreScenes(engraved.layout, stage)


def _pixel(view: StageView, scene_x: float, scene_y: float) -> QColor | None:
    image = view.viewport().grab().toImage()
    pt: QPoint = view.mapFromScene(QPointF(scene_x, scene_y))
    if not (0 <= pt.x() < image.width() and 0 <= pt.y() < image.height()):
        return None
    return image.pixelColor(pt)


def _view(scene, canvas, size=(500, 880)) -> StageView:
    view = StageView()
    view.resize(*size)
    view.viewport().grab()               # force offscreen layout
    view.set_canvas(canvas)
    view.show_scene(scene)
    return view


def _frame_rect(page: QRectF, canvas: VideoCanvas,
                center_y: float | None = None) -> QRectF:
    r = canvas_view_rect(page.width(), page.height(),
                         canvas.width, canvas.height, canvas.scale,
                         center_y)
    return QRectF(r.x, r.y, r.w, r.h)


def test_the_frame_takes_the_canvas_shape(qapp, scenes) -> None:
    """With a portrait canvas the fitted region is the pure seam's own
    rect: its center maps to the viewport center and its corners land
    inside the viewport."""
    canvas = VideoCanvas(1080, 1920)
    scene = scenes.scene_for_page(1)
    view = _view(scene, canvas)
    frame = _frame_rect(scene.sceneRect(), canvas)

    center = view.mapFromScene(frame.center())
    assert center.x() == pytest.approx(view.viewport().width() / 2, abs=4)
    assert center.y() == pytest.approx(view.viewport().height() / 2, abs=4)
    for corner in (frame.topLeft(), frame.bottomRight()):
        pt = view.mapFromScene(corner)
        assert -4 <= pt.x() <= view.viewport().width() + 4
        assert -4 <= pt.y() <= view.viewport().height() + 4


def test_scale_crops_at_the_frame_edge(qapp, scenes) -> None:
    """At scale 2 the page overflows the frame; overflowing ink reads
    as letterbox (masked) while the frame's center still shows page."""
    canvas = VideoCanvas(1080, 1920, scale=2.0)
    scene = scenes.scene_for_page(1)
    view = _view(scene, canvas)
    page = scene.sceneRect()
    frame = _frame_rect(page, canvas)
    assert frame.left() > page.left()          # the crop is real

    inside = _pixel(view, frame.center().x(), frame.center().y())
    assert inside is not None
    assert inside.name() != _LETTERBOX.name()
    # a point on the page but left of the frame: cropped away
    cropped_x = (page.left() + frame.left()) / 2
    color = _pixel(view, cropped_x, frame.center().y())
    if color is not None:                      # exposed at this aspect
        assert color.name() == _LETTERBOX.name()


def test_clicks_stop_at_the_crop(qapp, scenes) -> None:
    """in_band gates on the visible region, so ink cropped away by the
    canvas cannot be clicked (the system-mode rule, generalized)."""
    canvas = VideoCanvas(1080, 1920, scale=2.0)
    scene = scenes.scene_for_page(1)
    view = _view(scene, canvas)
    page = scene.sceneRect()
    frame = _frame_rect(page, canvas)
    assert view.in_band(frame.center())
    outside = QPointF((page.left() + frame.left()) / 2, frame.center().y())
    assert not view.in_band(outside)


def test_no_canvas_is_todays_behavior(qapp, scenes) -> None:
    """set_canvas(None) after a canvas restores the paged fit exactly:
    same transform as a view that never had one."""
    scene = scenes.scene_for_page(1)
    plain = StageView()
    plain.resize(500, 880)
    plain.viewport().grab()
    plain.show_scene(scene)

    view = _view(scene, VideoCanvas(1080, 1920))
    assert view.transform().m11() != pytest.approx(
        plain.transform().m11(), rel=1e-6)     # the canvas changed the fit
    view.set_canvas(None)
    assert view.transform().m11() == pytest.approx(
        plain.transform().m11(), rel=1e-6)
    assert view.in_band(QPointF(scene.sceneRect().left() + 1.0, 1.0))


def test_system_band_centers_in_the_canvas(qapp, engraved, scenes) -> None:
    """System mode with a canvas: one frame shape for both modes — the
    band's center maps to the viewport center and the zoom is the same
    for every system (the 10R constancy, with the user's shape)."""
    bands = {b.system: b for b in system_bands(engraved.layout)}
    canvas = VideoCanvas(1080, 1920)
    view = StageView()
    view.resize(500, 880)
    view.viewport().grab()
    view.set_canvas(canvas)
    zooms = set()
    for band in bands.values():
        scene = scenes.scene_for_page(band.page)
        view.show_system_band(scene,
                              QRectF(band.rect.x, band.rect.y,
                                     band.rect.w, band.rect.h))
        center = view.mapFromScene(
            QPointF(scene.sceneRect().center().x(),
                    band.rect.y + band.rect.h / 2))
        assert center.y() == pytest.approx(view.viewport().height() / 2,
                                           abs=4)
        zooms.add(round(view.transform().m11(), 6))
    assert len(zooms) == 1, f"zoom varied across systems: {zooms}"


def test_overlay_preview_paints_the_video_color(qapp, scenes) -> None:
    """Preview on + paper hidden: a point inside the frame reads the
    chosen color, so the ink composites the way the overlay will over
    footage. Off restores the white paper."""
    canvas = VideoCanvas(1080, 1920)
    scene = scenes.scene_for_page(1)
    view = _view(scene, canvas)
    frame = _frame_rect(scene.sceneRect(), canvas)
    # a spot inside the frame with no ink: just left of page center,
    # at the frame's own center height, works on the fixture
    probe = (frame.center().x() - frame.width() * 0.4,
             frame.center().y())

    scenes.set_page_background_visible(False)      # the window's half
    view.set_overlay_preview(True, QColor("#000000"))
    assert _pixel(view, *probe).name() == "#000000"

    view.set_overlay_preview(False, QColor("#000000"))
    scenes.set_page_background_visible(True)
    assert _pixel(view, *probe).name() == "#ffffff"


def test_the_canvas_never_moves_between_units(qapp, engraved,
                                              scenes) -> None:
    """The reported bug (2026-08-06): the canvas edge jumped 1-4 px
    between systems during playback, because fitInView rounds through
    the integer scrollbars position-dependently. The canvas fit pins
    it: the frame's viewport corners are IDENTICAL for every page and
    every system, in both modes."""
    canvas = VideoCanvas(1080, 1920)
    view = StageView()
    view.resize(500, 880)
    view.viewport().grab()
    view.set_canvas(canvas)

    def corners():
        f = view._framing.frame
        tl = view.mapFromScene(f.topLeft())
        br = view.mapFromScene(f.bottomRight())
        return (tl.x(), tl.y(), br.x(), br.y())

    seen = set()
    for page in range(1, scenes.page_count + 1):
        view.show_scene(scenes.scene_for_page(page))
        seen.add(corners())
    for band in system_bands(engraved.layout):
        view.show_system_band(scenes.scene_for_page(band.page),
                              QRectF(band.rect.x, band.rect.y,
                                     band.rect.w, band.rect.h))
        seen.add(corners())
    assert len(seen) == 1, f"the canvas moved: {sorted(seen)}"
