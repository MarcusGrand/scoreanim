"""The video canvas on the live stage, offscreen: the frame takes the
user's shape, clicks stop at the frame, and the overlay preview paints
the video color behind the ink."""
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
                         canvas.width, canvas.height, center_y)
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


def test_the_frame_always_holds_the_whole_page(qapp, scenes) -> None:
    """Fitting means containing: whatever the canvas shape, the frame
    covers the full page (the score is never cropped — its SIZE is the
    engraving scale's job), so every point on the page stays clickable.
    The slack beside the page belongs to the BOX: it fills with the
    page's own background, so the canvas reads as one solid rectangle,
    while outside the frame stays letterbox."""
    scene = scenes.scene_for_page(1)
    page = scene.sceneRect()
    for canvas in (VideoCanvas(1920, 1080), VideoCanvas(1080, 1920)):
        view = _view(scene, canvas)
        frame = _frame_rect(page, canvas)
        assert frame.united(page) == frame     # page ⊆ frame
        # corners inset by one device pixel: the stability fit snaps
        # the frame a quarter device pixel, so the mathematical corner
        # can sit in a sub-pixel sliver outside — a real click cannot
        # (it always lands on a whole device pixel)
        inset = 1.0 / view.transform().m11()
        assert view.in_band(QPointF(page.left() + inset,
                                    page.top() + inset))
        assert view.in_band(QPointF(page.right() - inset,
                                    page.bottom() - inset))
        if frame.left() < page.left():         # landscape: side slack
            slack_x = (frame.left() + page.left()) / 2
            color = _pixel(view, slack_x, page.center().y())
            if color is not None:
                assert color.name() == "#ffffff"   # part of the box
        # past the frame: letterbox
        outside_x = frame.left() - frame.width() * 0.05
        color = _pixel(view, outside_x, frame.center().y())
        if color is not None:
            assert color.name() == _LETTERBOX.name()


def test_the_box_is_solid_across_systems(qapp, engraved, scenes) -> None:
    """The report (round 3): in system mode the lit area was band∩frame
    and reshaped with every system. Now a point inside the frame but
    OUTSIDE the band reads the frame's fill — the page background, or
    the preview color when the preview is on — never letterbox, so the
    box is one still rectangle whose content changes."""
    bands = {b.system: b for b in system_bands(engraved.layout)}
    canvas = VideoCanvas(1080, 1920)
    view = StageView()
    view.resize(500, 880)
    view.viewport().grab()
    view.set_canvas(canvas)
    band = bands[2]
    scene = scenes.scene_for_page(band.page)
    view.show_system_band(scene, QRectF(band.rect.x, band.rect.y,
                                        band.rect.w, band.rect.h))
    frame = view._framing.frame
    # inside the frame, well above the band: the box, not letterbox
    probe_y = (frame.top() + band.rect.y) / 2
    probe = (frame.center().x(), probe_y)
    assert _pixel(view, *probe).name() == "#ffffff"

    view.set_overlay_preview(True, QColor("#000000"))
    assert _pixel(view, *probe).name() == "#000000"
    view.set_overlay_preview(False, QColor("#000000"))


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
