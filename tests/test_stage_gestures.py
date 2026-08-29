"""Stage navigation (2026-07-30), offscreen: pinch and Cmd/Ctrl+wheel
zoom, a bare two-finger scroll moves the view, and the zoom limits hold
at both ends.

A real pinch is a QNativeGestureEvent, whose constructor signature moves
between Qt versions, so the gesture handler is a thin wrapper and these
tests drive `zoom_by` — the same helper it calls — directly.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from scoreanim.ui.stage_scrollbars import (  # noqa: E402
    HORIZONTAL, VERTICAL)
from scoreanim.ui.stage_view import StageView  # noqa: E402
from scoreanim.ui.stage_zoom import (  # noqa: E402
    _ZOOM_MAX, _ZOOM_MIN, clamped_factor)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(qapp) -> StageView:
    """A view over a scene much larger than the window, so there is
    somewhere to scroll to."""
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0, 0, 2000, 2000))
    scene.addRect(QRectF(0, 0, 2000, 2000))
    stage = StageView()
    stage.resize(600, 500)
    stage.show_scene(scene)
    return stage


def _wheel(view: StageView, dx: int, dy: int,
           modifier=Qt.KeyboardModifier.NoModifier) -> QWheelEvent:
    """A trackpad-style wheel event, i.e. one carrying pixelDelta."""
    pos = QPointF(300.0, 250.0)
    return QWheelEvent(pos, view.mapToGlobal(pos.toPoint()).toPointF(),
                       QPoint(dx, dy), QPoint(0, 0),
                       Qt.MouseButton.NoButton, modifier,
                       Qt.ScrollPhase.NoScrollPhase, False)


def _zoom(view: StageView) -> float:
    return view.transform().m11()


# -- the clamp, on its own ----------------------------------------------

def test_a_zoom_in_step_stops_at_the_upper_limit() -> None:
    assert clamped_factor(2.0, _ZOOM_MAX / 1.5) == pytest.approx(1.5)
    assert clamped_factor(2.0, _ZOOM_MAX) == 1.0


def test_a_zoom_out_step_stops_at_the_lower_limit() -> None:
    assert clamped_factor(0.5, _ZOOM_MIN * 2.0) == pytest.approx(0.5)
    assert clamped_factor(0.1, _ZOOM_MIN * 2.0) == pytest.approx(0.5)


def test_zooming_out_from_below_the_limit_holds_instead_of_snapping() -> None:
    """A big score in a small window can be fitted below _ZOOM_MIN.
    Zooming out from there must hold still, never jump back up."""
    assert clamped_factor(0.5, _ZOOM_MIN / 4.0) == 1.0
    # zooming IN from there is still allowed
    assert clamped_factor(1.1, _ZOOM_MIN / 4.0) == pytest.approx(1.1)


# -- zoom ---------------------------------------------------------------

def test_ctrl_wheel_up_zooms_in_and_down_zooms_out(view) -> None:
    view.fit()
    fitted = _zoom(view)
    view.wheelEvent(_wheel(view, 0, 40, Qt.KeyboardModifier.ControlModifier))
    zoomed_in = _zoom(view)
    assert zoomed_in > fitted
    view.wheelEvent(_wheel(view, 0, -40, Qt.KeyboardModifier.ControlModifier))
    assert _zoom(view) < zoomed_in


def test_a_pinch_step_zooms_by_one_plus_its_value(view) -> None:
    """What viewportEvent does with a ZoomNativeGesture: spreading the
    fingers reports a positive value and makes the score bigger."""
    before = _zoom(view)
    view.zoom_by(1.0 + 0.10)                 # fingers apart
    assert _zoom(view) == pytest.approx(before * 1.10)
    view.zoom_by(1.0 - 0.10)                 # fingers together
    assert _zoom(view) == pytest.approx(before * 1.10 * 0.90)


def test_any_zoom_leaves_fit_mode_and_fit_restores_it(view) -> None:
    view.fit()
    assert view._fit_mode
    view.zoom_by(1.5)
    assert not view._fit_mode
    zoomed = _zoom(view)
    view.fit()
    assert view._fit_mode
    assert _zoom(view) != pytest.approx(zoomed)


def test_repeated_zooming_holds_at_both_limits(view) -> None:
    for _ in range(400):
        view.zoom_by(1.2)
    assert _zoom(view) == pytest.approx(_ZOOM_MAX)
    for _ in range(400):
        view.zoom_by(0.8)
    assert _zoom(view) == pytest.approx(_ZOOM_MIN)


# -- scroll -------------------------------------------------------------

def test_a_bare_vertical_scroll_moves_the_view_without_zooming(view) -> None:
    view.zoom_by(4.0)                        # zoom in, so there is slack
    bar = view.verticalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    start, zoom = bar.value(), _zoom(view)
    # fingers up (a negative delta) moves the view further down the page
    view.wheelEvent(_wheel(view, 0, -30))
    assert bar.value() > start
    assert _zoom(view) == pytest.approx(zoom)


def test_a_bare_horizontal_scroll_moves_the_view_sideways(view) -> None:
    view.zoom_by(4.0)
    bar = view.horizontalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    start, zoom = bar.value(), _zoom(view)
    view.wheelEvent(_wheel(view, -30, 0))
    assert bar.value() > start
    assert _zoom(view) == pytest.approx(zoom)


def test_scrolling_in_fit_mode_is_a_harmless_no_op(view) -> None:
    view.fit()
    fitted = _zoom(view)
    view.wheelEvent(_wheel(view, -30, -30))
    assert view.verticalScrollBar().value() == 0
    assert view.horizontalScrollBar().value() == 0
    assert _zoom(view) == pytest.approx(fitted)
    assert view._fit_mode                    # a scroll never leaves fit mode


def test_a_fitted_system_band_cannot_be_scrolled_out_of_frame(view) -> None:
    """System mode is the case where fit mode DOES leave scroll range:
    the scene rect is taller than the framed band on purpose, so the
    overhang letterboxes. A stray scroll must not slide the framed
    system away into it."""
    # a band near the page top, so the page-sized frame overhangs well
    # past the page and the united scene rect is taller than the frame
    band = QRectF(0.0, 0.0, 2000.0, 300.0)
    view.show_system_band(view.scene(), band)
    view.show()
    QApplication.processEvents()              # the range needs a layout pass
    assert view._fit_mode
    bar = view.verticalScrollBar()
    assert bar.maximum() > bar.minimum()      # slack really exists
    before = bar.value()
    view.wheelEvent(_wheel(view, 0, -60))
    assert bar.value() == before

    # once the user zooms, they own the framing and scrolling works again
    view.zoom_by(2.0)
    view.wheelEvent(_wheel(view, 0, -60))
    assert bar.value() != before


def test_a_classic_wheel_without_pixel_deltas_still_works(view) -> None:
    """No pixelDelta (a mouse wheel, not a trackpad): fall back to angle
    notches for both scrolling and Ctrl-zooming."""
    view.zoom_by(4.0)
    bar = view.verticalScrollBar()
    bar.setValue((bar.minimum() + bar.maximum()) // 2)
    start = bar.value()
    pos = QPointF(300.0, 250.0)
    notch = QWheelEvent(pos, view.mapToGlobal(pos.toPoint()).toPointF(),
                        QPoint(0, 0), QPoint(0, -120),
                        Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    view.wheelEvent(notch)
    assert bar.value() > start


# -- the indicators -----------------------------------------------------

def test_the_indicators_wake_on_a_zoom_and_show_one_bar_per_axis(view) -> None:
    bars = view._scrollbars
    assert bars.opacity == 0.0                # nothing has happened yet
    view.zoom_by(4.0)
    assert bars.opacity == 1.0
    assert bars._bar(VERTICAL) is not None
    assert bars._bar(HORIZONTAL) is not None


def test_a_fitted_view_has_no_indicators_to_draw(view) -> None:
    """Fit means the whole page is visible, so there is nothing to hint
    at, however much the bars have been poked."""
    view.fit()
    view._scrollbars.poke()
    assert view._scrollbars._bar(VERTICAL) is None
    assert view._scrollbars._bar(HORIZONTAL) is None


def test_the_indicator_sits_where_the_view_is_looking(view) -> None:
    view.zoom_by(4.0)
    bar = view.verticalScrollBar()
    rect = QRectF(view.viewport().rect())
    bar.setValue(bar.minimum())
    top = view._scrollbars._span(bar, rect.height())
    bar.setValue(bar.maximum())
    bottom = view._scrollbars._span(bar, rect.height())
    assert top is not None and bottom is not None
    assert top[0] == pytest.approx(0.0)                    # flush to the top
    assert bottom[0] == pytest.approx(rect.height() - bottom[1])
    assert top[1] == pytest.approx(bottom[1])              # same thumb length
