"""The stage's scroll indicators, offscreen: they show themselves when
the pointer reaches for them, and they scroll when it grabs them.

They were feedback-only until 2026-08-29 — the reasoning was that they
were gone before you could reach for one, which turned out to be the
problem rather than the excuse. These tests are the pin on the other
answer: reachable, grabbable, and never in the way of a click on the
score they are drawn over.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from scoreanim.ui.stage_scrollbars import (  # noqa: E402
    _FILL, _FILL_HELD, _FILL_READY, _GRAB, _READY_THICKNESS, _THICKNESS,
    HORIZONTAL, VERTICAL)
from scoreanim.ui.stage_view import StageView  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(qapp) -> StageView:
    """A view zoomed in far enough that both axes have somewhere to
    scroll to, so both bars exist."""
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0, 0, 2000, 2000))
    scene.addRect(QRectF(0, 0, 2000, 2000))
    stage = StageView()
    stage.resize(600, 500)
    stage.show()
    stage.show_scene(scene)
    stage.zoom_by(4.0)
    return stage


def _bars(view):
    return view._scrollbars


def _edge(view, axis: str, along: float) -> QPointF:
    """A point on the edge a bar lives on, `along` pixels down (or
    across) its track."""
    rect = view.viewport().rect()
    if axis == VERTICAL:
        return QPointF(rect.right() - 5.0, along)
    return QPointF(along, rect.bottom() - 5.0)


def _press(view, pos: QPointF) -> None:
    view.mousePressEvent(QMouseEvent(
        QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


def _move(view, pos: QPointF, held: bool = True) -> None:
    button = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
    view.mouseMoveEvent(QMouseEvent(
        QEvent.Type.MouseMove, pos, Qt.MouseButton.NoButton, button,
        Qt.KeyboardModifier.NoModifier))


def _thickness(bars, axis: str) -> float:
    bar = bars._bar(axis)
    return bar.width() if axis == VERTICAL else bar.height()


def _release(view, pos: QPointF) -> None:
    view.mouseReleaseEvent(QMouseEvent(
        QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))


# -- being there to be grabbed ------------------------------------------

def test_a_fitted_view_has_no_bars_at_all(qapp):
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0, 0, 2000, 2000))
    stage = StageView()
    stage.resize(600, 500)
    stage.show()
    stage.show_scene(scene)          # fitted: nothing hidden either way
    assert _bars(stage)._bar(VERTICAL) is None
    assert _bars(stage)._bar(HORIZONTAL) is None


def test_both_bars_exist_once_there_is_somewhere_to_scroll(view):
    assert _bars(view)._bar(VERTICAL) is not None
    assert _bars(view)._bar(HORIZONTAL) is not None


def test_reaching_for_an_edge_brings_its_bar_up(view):
    bars = _bars(view)
    bars._set_opacity(0.0)
    _move(view, _edge(view, VERTICAL, 200.0), held=False)
    assert bars._opacity == 1.0
    assert bars._reaching == VERTICAL


def test_the_middle_of_the_stage_brings_nothing_up(view):
    bars = _bars(view)
    bars._set_opacity(0.0)
    _move(view, QPointF(300.0, 250.0), held=False)
    assert bars._opacity == 0.0
    assert bars._reaching is None


def test_a_bar_under_the_pointer_does_not_fade_out_from_under_it(view):
    """The hold running out is where a bar would normally start to go."""
    bars = _bars(view)
    _move(view, _edge(view, VERTICAL, 200.0), held=False)
    bars._start_fade()                       # what the hold timer does
    assert bars._opacity == 1.0


def test_leaving_the_stage_lets_them_fade_again(view):
    """The viewport's Leave, not the view's: the zoom controls sit over
    the viewport, so moving onto them leaves it while the view still
    has the pointer."""
    bars = _bars(view)
    _move(view, _edge(view, VERTICAL, 200.0), held=False)
    QApplication.sendEvent(view.viewport(), QEvent(QEvent.Type.Leave))
    assert bars._reaching is None
    bars._start_fade()
    assert bars._fade.state() != bars._fade.State.Stopped


# -- dragging one --------------------------------------------------------

def test_dragging_the_vertical_bar_scrolls_the_view(view):
    bars = _bars(view)
    bars.poke()
    start = view.verticalScrollBar().value()
    handle = bars._bar(VERTICAL)
    _press(view, _edge(view, VERTICAL, handle.center().y()))
    _move(view, _edge(view, VERTICAL, handle.center().y() + 80.0))
    _release(view, _edge(view, VERTICAL, handle.center().y() + 80.0))
    assert view.verticalScrollBar().value() > start


def test_dragging_the_horizontal_bar_scrolls_the_view(view):
    bars = _bars(view)
    bars.poke()
    start = view.horizontalScrollBar().value()
    handle = bars._bar(HORIZONTAL)
    _press(view, _edge(view, HORIZONTAL, handle.center().x()))
    _move(view, _edge(view, HORIZONTAL, handle.center().x() + 90.0))
    _release(view, _edge(view, HORIZONTAL, handle.center().x() + 90.0))
    assert view.horizontalScrollBar().value() > start


def test_the_bar_follows_the_pointer_rather_than_running_ahead(view):
    """Travel along the track is the bar's travel: half the remaining
    track under the hand is half the remaining scroll."""
    bars = _bars(view)
    bars.poke()
    scrollbar = view.verticalScrollBar()
    scrollbar.setValue(scrollbar.minimum())
    handle = bars._bar(VERTICAL)
    travel = bars._travel(VERTICAL)
    _press(view, _edge(view, VERTICAL, handle.center().y()))
    _move(view, _edge(view, VERTICAL, handle.center().y() + travel / 2.0))
    span = scrollbar.maximum() - scrollbar.minimum()
    assert scrollbar.value() == pytest.approx(
        scrollbar.minimum() + span / 2.0, rel=0.02)
    _release(view, _edge(view, VERTICAL, handle.center().y()))


def test_a_press_on_the_track_jumps_the_bar_to_the_pointer(view):
    bars = _bars(view)
    bars.poke()
    scrollbar = view.verticalScrollBar()
    scrollbar.setValue(scrollbar.minimum())
    track = view.viewport().rect().height()
    _press(view, _edge(view, VERTICAL, track * 0.75))   # below the bar
    assert scrollbar.value() > scrollbar.minimum()
    _release(view, _edge(view, VERTICAL, track * 0.75))


def test_a_drag_on_a_bar_is_never_a_click_on_the_score(view):
    seen = []
    view.clicked.connect(lambda pos, scene: seen.append(pos))
    view.deselect_requested.connect(lambda: seen.append("deselect"))
    bars = _bars(view)
    bars.poke()
    handle = bars._bar(VERTICAL)
    spot = _edge(view, VERTICAL, handle.center().y())
    _press(view, spot)
    _move(view, spot)
    _release(view, spot)
    assert seen == []


def test_an_invisible_bar_is_not_in_the_way_of_a_click(view):
    """Faded out, the bars take no press at all — the score under them
    is still what a click lands on."""
    bars = _bars(view)
    bars._set_opacity(0.0)
    handle = bars._bar(VERTICAL)
    spot = _edge(view, VERTICAL, handle.center().y())
    assert not bars.press(spot)
    seen = []
    view.clicked.connect(lambda pos, scene: seen.append(pos))
    _press(view, spot)
    _release(view, spot)
    assert len(seen) == 1


def test_a_press_in_the_middle_of_the_stage_still_selects(view):
    seen = []
    view.clicked.connect(lambda pos, scene: seen.append(pos))
    _bars(view).poke()                    # bars up, but nowhere near
    spot = QPointF(300.0, 250.0)
    _press(view, spot)
    _release(view, spot)
    assert len(seen) == 1


def test_letting_go_ends_the_drag(view):
    bars = _bars(view)
    bars.poke()
    handle = bars._bar(VERTICAL)
    spot = _edge(view, VERTICAL, handle.center().y())
    _press(view, spot)
    assert bars._drag is not None
    _release(view, spot)
    assert bars._drag is None
    assert not bars.drag(QPointF(spot.x(), spot.y() + 50.0))


# -- saying whether it can be grabbed ------------------------------------

def test_a_bar_out_of_reach_stays_thin(view):
    bars = _bars(view)
    bars.poke()
    _move(view, QPointF(300.0, 250.0), held=False)
    assert _thickness(bars, VERTICAL) == _THICKNESS
    assert not bars._grabbable(VERTICAL)


def test_a_bar_widens_once_the_pointer_can_grab_it(view):
    bars = _bars(view)
    bars.poke()
    _move(view, _edge(view, VERTICAL, 200.0), held=False)
    assert _thickness(bars, VERTICAL) == _READY_THICKNESS
    assert bars._grabbable(VERTICAL)


def test_the_bar_widens_inward_so_it_does_not_move_out_from_under_you(view):
    """The outer edge holds still: the pointer that made it fatten is
    still on it afterwards."""
    bars = _bars(view)
    bars.poke()
    thin = bars._bar(VERTICAL)
    _move(view, _edge(view, VERTICAL, 200.0), held=False)
    wide = bars._bar(VERTICAL)
    assert wide.right() == thin.right()
    assert wide.left() < thin.left()


def test_wide_means_grabbable_and_thin_means_not(view):
    """The look is a promise, so it has to match what a press does at
    every distance from the edge, not just the two obvious ones."""
    bars = _bars(view)
    rect = view.viewport().rect()
    for offset in (2.0, 8.0, 14.0, 20.0, 40.0, 120.0):
        bars.poke()
        spot = QPointF(rect.right() - offset, 200.0)
        _move(view, spot, held=False)
        wide = _thickness(bars, VERTICAL) == _READY_THICKNESS
        assert wide == bars.press(spot), offset
        bars.release(spot)


def test_the_reach_that_wakes_a_bar_is_wider_than_the_one_that_takes_it(view):
    """The bar arrives first and fattens as the hand keeps coming."""
    bars = _bars(view)
    bars._set_opacity(0.0)
    spot = QPointF(view.viewport().rect().right() - (_GRAB + 8.0), 200.0)
    _move(view, spot, held=False)
    assert bars._opacity == 1.0                    # it came up
    assert _thickness(bars, VERTICAL) == _THICKNESS  # but is not promising


def test_a_bar_in_the_hand_goes_light(view):
    bars = _bars(view)
    bars.poke()
    handle = bars._bar(VERTICAL)
    spot = _edge(view, VERTICAL, handle.center().y())
    _move(view, spot, held=False)
    assert bars._grabbable(VERTICAL) and not bars._held(VERTICAL)
    _press(view, spot)
    assert bars._held(VERTICAL)
    # grabbable is the same dark bar, more solid; in the hand it is
    # lighter, which no amount of black can be mistaken for
    assert _FILL_READY.alpha() > _FILL.alpha()
    assert _FILL_HELD.lightness() > _FILL_READY.lightness()
    # and it stays wide while it is held, wherever the hand wanders
    _move(view, QPointF(120.0, 400.0))
    assert _thickness(bars, VERTICAL) == _READY_THICKNESS
    _release(view, QPointF(120.0, 400.0))
    assert _thickness(bars, VERTICAL) == _THICKNESS   # hand gone, bar rests


def test_leaving_the_stage_puts_a_bar_back_to_resting(view):
    bars = _bars(view)
    bars.poke()
    _move(view, _edge(view, VERTICAL, 200.0), held=False)
    QApplication.sendEvent(view.viewport(), QEvent(QEvent.Type.Leave))
    assert _thickness(bars, VERTICAL) == _THICKNESS
