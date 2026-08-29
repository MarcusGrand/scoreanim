"""System-at-a-time stage framing, offscreen.

Phase 7.4 built it; the 2026-08-30 rework (docs/SYSTEMS_MODE_REWORK.md
stage 1) replaced the per-system page window with ONE constant frame the
systems are placed into. What these pin: the frame never changes size or
position, the band is centred in it, there is no paper edge inside it, a
neighbouring system never bleeds in, and clear_band restores paged
behaviour.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRectF  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.engraving.systems import (system_bands,  # noqa: E402
                                              systems_frame)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.render.scene import ScoreScenes  # noqa: E402
from scoreanim.ui.stage_frame import fit_geometry  # noqa: E402
from scoreanim.ui.stage_view import _LETTERBOX, StageView  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def scenes(qapp, engraved) -> ScoreScenes:
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    return ScoreScenes(engraved.layout, stage)


@pytest.fixture(scope="module")
def bands(engraved) -> dict:
    return {b.system: b for b in system_bands(engraved.layout)}


@pytest.fixture(scope="module")
def frame(bands):
    return systems_frame(tuple(bands.values()))


# the page's own background, which is what a frame fills with while the
# overlay preview is off — the stage's default light paper
_FILL = "#ffffff"


def _qrect(rect) -> QRectF:
    return QRectF(rect.x, rect.y, rect.w, rect.h)


def _pixel(view: StageView, scene_x: float, scene_y: float) -> QColor | None:
    """Rendered viewport color at a scene point, None if not exposed."""
    image = view.viewport().grab().toImage()
    pt: QPoint = view.mapFromScene(QPointF(scene_x, scene_y))
    if not (0 <= pt.x() < image.width() and 0 <= pt.y() < image.height()):
        return None
    return image.pixelColor(pt)


def _view(frame, size=(600, 850)) -> StageView:
    view = StageView()
    view.resize(*size)
    view.viewport().grab()               # force offscreen layout/resize
    view.set_systems_frame(frame)        # what ViewRouter.bind does
    return view


def _show(view, scenes, band) -> None:
    view.show_system_band(scenes.scene_for_page(band.page),
                          _qrect(band.rect))


# -- the constant frame ---------------------------------------------------

def _lit_column(view: StageView) -> tuple[int, int]:
    """Where the frame's top and bottom edges are ON SCREEN, read off
    the rendered pixels: scan the middle column from each end for the
    first pixel painted in the frame's fill. Measured the way the user
    sees it, so nothing internal has to be trusted. The fill is safe to
    scan for at both ends because the frame's padding is ink-free by
    construction, and it ignores the transient scroll hint, which paints
    a letterbox-dark pixel at the viewport edge."""
    image = view.viewport().grab().toImage()
    x = image.width() // 2
    rows = range(image.height())
    top = next(y for y in rows
               if image.pixelColor(x, y).name() == _FILL)
    bottom = next(y for y in reversed(rows)
                  if image.pixelColor(x, y).name() == _FILL)
    return top, bottom


def test_the_frame_never_changes_size_or_position(qapp, scenes, bands,
                                                  frame) -> None:
    """Stage 1's whole point, and the headless form of Marcus's own
    check: play across every system and the lit frame occupies exactly
    the same screen pixels each time, however tall the system is.

    Before the rework the lit area was the BAND, so its edges moved by
    the difference in staff count on every switch."""
    heights = {s: round(b.rect.h) for s, b in bands.items()}
    assert len(set(heights.values())) > 1     # bands really differ
    view = _view(frame)
    seen = set()
    for band in bands.values():
        _show(view, scenes, band)
        seen.add(_lit_column(view))
    assert len(seen) == 1, f"the frame moved between systems: {seen}"
    # and it is the FRAME that is lit, not the band: the lit span is the
    # frame's height on screen even for the shortest system, which is
    # 137 px shorter than that here. (+/-4 px for the antialiased edge
    # and the quarter-pixel snap.)
    top, bottom = seen.pop()
    scale = view.transform().m11()
    assert bottom - top == pytest.approx(frame.height * scale, abs=4)
    shortest = min(b.rect.h for b in bands.values())
    assert frame.height * scale - shortest * scale > 100


def test_live_zoom_is_constant_across_systems(qapp, scenes, bands,
                                              frame) -> None:
    """One frame means one fit: the view zoom is IDENTICAL for every
    system however its band height differs — the system is singled out
    and centred, nothing resizes."""
    view = _view(frame)
    zooms = set()
    for band in bands.values():
        _show(view, scenes, band)
        zooms.add(round(view.transform().m11(), 6))
    assert len(zooms) == 1, f"zoom varied across systems: {zooms}"


def test_band_is_centred_in_the_frame(qapp, scenes, bands, frame) -> None:
    """Each system sits in the middle of the frame vertically and keeps
    the horizontal position it was engraved with — so at Fit the band's
    centre is the viewport's centre."""
    view = _view(frame)
    page = scenes.scene_for_page(bands[2].page).sceneRect()
    for band in bands.values():
        _show(view, scenes, band)
        centre = view.mapFromScene(QPointF(page.center().x(),
                                           band.rect.center.y))
        assert centre.x() == pytest.approx(view.viewport().width() / 2,
                                           abs=2)
        assert centre.y() == pytest.approx(view.viewport().height() / 2,
                                           abs=2)


def test_fit_targets_the_frame_not_the_page(qapp, scenes, bands,
                                            frame) -> None:
    """Fit fits the FRAME. The frame is shorter than the page (tallest
    band plus padding, against a whole page), so system mode shows the
    music bigger than paged mode does, and the two no longer share a
    scale the way the Phase 10R page-sized window did."""
    scene = scenes.scene_for_page(bands[2].page)
    view = _view(frame)
    view.show_scene(scene)
    paged = view.transform().m11()
    _show(view, scenes, bands[2])
    assert view.transform().m11() > paged
    # and it really is the frame that fits: the frame's height fills the
    # viewport (this viewport is taller than the frame's aspect)
    placed = view.mapFromScene(
        _qrect(frame.rect_for(bands[2].rect))).boundingRect()
    assert (placed.width() == pytest.approx(view.viewport().width(), abs=2)
            or placed.height() == pytest.approx(view.viewport().height(),
                                                abs=2))


# -- no page context ------------------------------------------------------

@pytest.mark.parametrize("system", [2, 4])
def test_no_paper_edge_inside_the_frame(qapp, scenes, bands, frame,
                                        system) -> None:
    """Hide all page context: the whole frame is one uniform colour, so
    a short system and a tall one look the same everywhere except where
    the music is. Before the rework the lit area WAS the band, so its
    top and bottom edges jumped on every switch."""
    view = _view(frame)
    band = bands[system]
    _show(view, scenes, band)
    placed = frame.rect_for(band.rect)
    seen = set()
    for x_frac in (0.005, 0.02):          # left margin: no ink at any y
        for y_frac in (0.01, 0.05, 0.2, 0.5, 0.8, 0.95, 0.99):
            color = _pixel(view, placed.x + x_frac * placed.w,
                           placed.y + y_frac * placed.h)
            assert color is not None      # the frame is fitted: all of
            seen.add(color.name())        # it is on screen
    assert seen == {_FILL}, f"the frame is not uniform: {seen}"


@pytest.mark.parametrize("size", [(1920, 400), (400, 1000)])
def test_neighbour_system_never_bleeds(qapp, scenes, bands, frame,
                                       size) -> None:
    """Page 2 carries systems 2 and 3: with system 2 framed, system 3's
    ink must never show — as letterbox where it falls outside the frame,
    as the frame's own fill where it falls inside — at a wide AND a tall
    aspect."""
    assert bands[2].page == bands[3].page == 2
    view = _view(frame, size=size)
    _show(view, scenes, bands[2])
    placed = frame.rect_for(bands[2].rect)

    own = bands[2].rect
    inside = _pixel(view, own.center.x, own.center.y)
    assert inside is not None
    assert inside.name() != _LETTERBOX.name()

    neighbour = bands[3].rect
    exposed_any = False
    # sample a horizontal run through the neighbour band's center line
    for frac in (0.2, 0.35, 0.5, 0.65, 0.8):
        y = neighbour.center.y
        color = _pixel(view, neighbour.x + frac * neighbour.w, y)
        if color is None:
            continue                     # not exposed at this aspect: fine
        exposed_any = True
        want = _FILL if placed.y <= y <= placed.y + placed.h \
            else _LETTERBOX.name()
        assert color.name() == want
    tall = size[1] > size[0]
    if tall:
        # the tall window definitely exposes the scene below the band —
        # the masking must actually have been exercised
        assert exposed_any


def test_clear_band_restores_paged_framing(qapp, scenes, bands,
                                           frame) -> None:
    view = _view(frame, size=(400, 1000))
    _show(view, scenes, bands[2])
    view.clear_band()
    # neighbour ink is visible again (white page, not letterbox)
    neighbour = bands[3].rect
    color = _pixel(view, neighbour.center.x, neighbour.center.y)
    assert color is not None
    assert color.name() != _LETTERBOX.name()


# -- the fit arithmetic, without a window ---------------------------------

def test_fit_geometry_is_the_same_wherever_the_frame_sits() -> None:
    """The reason a switch cannot make the frame wobble: the scale and
    the scroll rect depend on the frame's SIZE only, never on where the
    band put it. (fitInView, which rounds through integer scrollbars,
    moved the canvas edge 1-4 px between systems in 2026-08.)"""
    page = QRectF(0, 0, 2000.0, 3000.0)
    a = fit_geometry(QRectF(0, -175.0, 2000.0, 1700.0), page, 900, 620)
    b = fit_geometry(QRectF(0, 1194.0, 2000.0, 1700.0), page, 900, 620)
    assert a is not None and b is not None
    assert a[0] == b[0]                       # same scale
    assert a[2] == b[2]                       # same scroll rect
    assert a[1].size() == b[1].size()         # same frame size


def test_fit_geometry_snaps_off_the_integer_grid() -> None:
    """Every rounding downstream has to land the same side, so the
    fitted frame's device-pixel corner is nudged a quarter pixel."""
    page = QRectF(0, 0, 2000.0, 3000.0)
    scale, snapped, _ = fit_geometry(QRectF(0, 100.0, 2000.0, 1000.0),
                                     page, 1000, 500)
    assert (snapped.left() * scale) % 1.0 == pytest.approx(0.25)
    assert (snapped.top() * scale) % 1.0 == pytest.approx(0.25)


def test_fit_geometry_has_nothing_to_fit() -> None:
    page = QRectF(0, 0, 2000.0, 3000.0)
    assert fit_geometry(QRectF(0, 0, 100.0, 100.0), page, 0, 500) is None
    assert fit_geometry(QRectF(), page, 900, 620) is None
