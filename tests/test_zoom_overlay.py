"""The stage's floating zoom controls (D2), offscreen.

Three things are pinned here: the arithmetic behind the percentage, the
percentage against a REAL fit (which is what keeps `FIT_MARGIN` honest —
Qt does not document that margin), and the overlay's one promise, that
it is not there to be clicked unless the pointer is already on the
stage.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QAction, QEnterEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QGraphicsScene, QGraphicsView)

from scoreanim.ui.stage_view import StageView  # noqa: E402
from scoreanim.ui.stage_zoom import (  # noqa: E402
    FIT_MARGIN, fit_scale, percent, percent_text)
from scoreanim.ui.zoom_overlay import ZOOM_STEP, ZoomOverlay  # noqa: E402

PAGE = QRectF(0.0, 0.0, 2095.5, 2966.9)      # a Dorico A4 page, in its
                                             # own units (tenths of a mm)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(qapp) -> StageView:
    """A shown view over one page. Shown matters: a hidden window never
    lays its viewport out, so a resize would not reach the fit."""
    scene = QGraphicsScene()
    scene.setSceneRect(PAGE)
    scene.addRect(PAGE)
    stage = StageView()
    stage.resize(600, 500)
    stage.show()
    QTest.qWaitForWindowExposed(stage)
    stage.show_scene(scene)
    return stage


@pytest.fixture
def overlay(view) -> ZoomOverlay:
    fit_action = QAction("Fit", view)
    fit_action.triggered.connect(view.fit)
    return ZoomOverlay(view, fit_action)


def _enter(widget) -> None:
    pos = QPointF(widget.rect().center())
    QApplication.sendEvent(
        widget, QEnterEvent(pos, pos, widget.mapToGlobal(pos)))


def _leave(widget) -> None:
    QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))


# -- the arithmetic, on its own -----------------------------------------

def test_fit_scale_takes_the_tighter_axis() -> None:
    # a tall page in a wide window: the height decides
    assert fit_scale(1000, 500, 200, 400, margin=0.0) == pytest.approx(1.25)
    # a wide page in a tall window: the width does
    assert fit_scale(500, 1000, 400, 200, margin=0.0) == pytest.approx(1.25)


def test_fit_scale_gives_up_the_margin_on_both_edges() -> None:
    assert fit_scale(504, 1000, 500, 100, margin=2.0) == pytest.approx(1.0)


def test_fit_scale_of_nothing_is_zero() -> None:
    assert fit_scale(600, 500, 0.0, 100.0) == 0.0
    assert fit_scale(600, 500, 100.0, 0.0) == 0.0
    assert fit_scale(3, 500, 100.0, 100.0) == 0.0     # margin eats it all


def test_percent_is_of_the_fitted_size() -> None:
    assert percent(0.2, 0.1) == 200
    assert percent(0.1, 0.1) == 100
    assert percent(0.05, 0.1) == 50
    assert percent(0.1, 0.0) == 0            # nothing to be a percentage of


def test_an_unmeasurable_zoom_reads_as_a_dash() -> None:
    assert percent_text(100) == "100%"
    assert percent_text(0) == "–"


# -- the percentage against a real fit ----------------------------------

def test_the_fit_formula_matches_what_fitinview_actually_does(view) -> None:
    """The pin under FIT_MARGIN: Qt does not document the margin, so if
    a Qt release ever changes it, this is what says so."""
    view.fit()
    assert view.fit_scale() == pytest.approx(view.transform().m11())
    assert FIT_MARGIN == 2.0


def test_a_fitted_view_reads_one_hundred_percent(view) -> None:
    view.fit()
    assert view.zoom_percent() == 100


def test_zooming_moves_the_percentage_and_fit_brings_it_back(view) -> None:
    view.fit()
    view.zoom_by(2.0)
    assert view.zoom_percent() == 200
    view.zoom_by(0.5)
    assert view.zoom_percent() == 100
    view.zoom_by(4.0)
    view.fit()
    assert view.zoom_percent() == 100


def test_a_resize_under_a_zoomed_view_moves_the_percentage(view) -> None:
    """The reason the fit scale is worked out and not remembered: the
    ink did not change size, but 'fitted' did."""
    view.fit()
    view.zoom_by(2.0)
    view.resize(1200, 1000)
    QTest.qWait(1)
    assert view.zoom_percent() < 200


def test_a_resize_under_a_fitted_view_holds_at_one_hundred(view) -> None:
    view.fit()
    view.resize(900, 400)
    QTest.qWait(1)
    assert view.zoom_percent() == 100


def test_the_view_announces_every_size_change(view) -> None:
    seen = []
    view.zoom_changed.connect(lambda: seen.append(view.zoom_percent()))
    view.zoom_by(2.0)
    view.fit()
    assert seen[:2] == [200, 100]


# -- the overlay --------------------------------------------------------

def test_the_controls_are_not_there_until_the_pointer_is(overlay, view):
    assert not overlay.isVisible()
    _enter(view.viewport())
    assert overlay.isVisible()
    _leave(view.viewport())
    assert not overlay.isVisible()


def test_reaching_for_the_controls_does_not_dismiss_them(overlay, view):
    """Moving onto the overlay sends the viewport a Leave, because the
    overlay is one of its children."""
    _enter(view.viewport())
    _enter(overlay)
    _leave(view.viewport())
    assert overlay.isVisible()
    _leave(overlay)
    assert not overlay.isVisible()


def test_an_empty_stage_has_nothing_to_zoom(qapp):
    stage = StageView()
    stage.resize(600, 500)
    stage.show()
    QTest.qWaitForWindowExposed(stage)
    controls = ZoomOverlay(stage, QAction("Fit", stage))
    _enter(stage.viewport())
    assert not controls.isVisible()


def test_the_readout_follows_the_view(overlay, view):
    view.fit()
    assert overlay._readout.text() == "100%"
    view.zoom_by(2.0)
    assert overlay._readout.text() == "200%"


def test_the_buttons_zoom_by_one_step_each(overlay, view):
    view.fit()
    overlay._in.click()
    assert view.zoom_percent() == round(ZOOM_STEP * 100)
    overlay._out.click()
    assert view.zoom_percent() == 100


def test_a_button_zoom_keeps_the_stage_centred(overlay, view):
    """The pointer is on a button in the corner when this fires, so the
    anchor is the middle of the view, not the pointer — and the pinch
    anchor is put back afterwards."""
    view.fit()
    centre = view.mapToScene(view.viewport().rect().center())
    overlay._in.click()
    after = view.mapToScene(view.viewport().rect().center())
    # the tolerance is scene units: the view scrolls in whole pixels,
    # so the centre can land a fraction of a pixel off
    assert after.x() == pytest.approx(centre.x(), abs=10.0)
    assert after.y() == pytest.approx(centre.y(), abs=10.0)
    assert view.transformationAnchor() == \
        QGraphicsView.ViewportAnchor.AnchorUnderMouse


def test_fit_is_the_menus_own_action(overlay, view):
    view.zoom_by(3.0)
    overlay._fit.click()
    assert view.zoom_percent() == 100
    # really fit mode, not just the same number: a resize re-letterboxes
    view.resize(900, 400)
    QTest.qWait(1)
    assert view.zoom_percent() == 100


def test_the_controls_never_take_the_keyboard(overlay):
    for button in (overlay._out, overlay._in, overlay._fit):
        assert button.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_the_controls_sit_in_the_stages_bottom_right(overlay, view):
    _enter(view.viewport())
    area = view.viewport().rect()
    assert area.contains(overlay.geometry())
    assert overlay.geometry().right() > area.center().x()
    assert overlay.geometry().bottom() > area.center().y()


def test_a_click_where_they_sit_reaches_the_score_while_they_are_gone(
        overlay, view):
    """They are hidden, not transparent, when the pointer is away — so
    nothing of theirs is in the way of a click on the score."""
    seen = []
    view.clicked.connect(lambda pos, scene: seen.append(pos))
    assert not overlay.isVisible()
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier,
                     overlay.geometry().center())
    assert len(seen) == 1
