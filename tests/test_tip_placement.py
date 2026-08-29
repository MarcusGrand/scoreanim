"""Where the hover box sits (Marcus, 2026-08-30): to the right of the
pointer, always.

The rule is pure, so most of this needs no window at all. The last two
drive Qt's REAL tooltip window, because the thing being corrected is
Qt's own placement and a fake would prove nothing about it.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCursor, QGuiApplication  # noqa: E402
from PySide6.QtWidgets import (QApplication, QToolTip,  # noqa: E402
                               QWidget)

from scoreanim.ui.tip_placement import (CURSOR_GAP,  # noqa: E402
                                        TIP_CLASS, TipPlacement, tip_left)

SCREEN = (0, 800)          # left, one past the last usable pixel


# -- the rule ---------------------------------------------------------------


def test_the_box_starts_at_the_pointer_and_runs_right() -> None:
    assert tip_left(100, 300, *SCREEN) == 100 + CURSOR_GAP


def test_a_box_that_would_overrun_slides_left_just_enough() -> None:
    """Not to the other side of the pointer — the pointer ends up
    somewhere along the box, which is the whole point."""
    x = tip_left(700, 300, *SCREEN)
    assert x == 500                          # flush with the right edge
    assert x < 700 < x + 300                 # the pointer is ON the box


def test_a_box_that_exactly_fits_is_not_moved() -> None:
    assert tip_left(498, 300, *SCREEN) == 500


def test_a_box_wider_than_the_screen_is_pinned_to_the_left() -> None:
    """It overruns on the right, which is the only way its first word
    stays readable."""
    assert tip_left(400, 900, *SCREEN) == 0


def test_the_rule_holds_on_a_screen_that_does_not_start_at_zero() -> None:
    """A second monitor to the right of the first."""
    left, right = 1920, 3520
    assert tip_left(2000, 300, left, right) == 2000 + CURSOR_GAP
    assert tip_left(3400, 300, left, right) == 3220
    assert tip_left(2000, 4000, left, right) == left


@pytest.mark.parametrize("cursor", [0, 1, 399, 400, 700, 799])
@pytest.mark.parametrize("width", [10, 120, 400, 799, 800])
def test_the_box_never_leaves_the_screen_and_never_flips(cursor, width
                                                         ) -> None:
    """The two promises, swept: it starts no further left than the
    screen does, and its right edge never lands left of the pointer —
    which is what 'the box reads rightward' means."""
    x = tip_left(cursor, width, *SCREEN)
    assert x >= SCREEN[0]
    assert x + width > cursor
    assert x + width <= SCREEN[1] or width > SCREEN[1] - SCREEN[0]


# -- Qt's own tooltip window ------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def placed(qapp):
    """The filter installed for one test and taken off again, so it
    cannot follow the suite into another module."""
    placement = TipPlacement()
    qapp.installEventFilter(placement)
    yield placement
    qapp.removeEventFilter(placement)
    QToolTip.hideText()


def _show(qapp, host: QWidget, cursor_x: int, text: str) -> QWidget:
    """Put a real tooltip up at `cursor_x` and hand back Qt's window.

    The text has to differ every time: `QToolTip.showText` returns
    early when the same text is already up, and would place nothing.
    """
    QCursor.setPos(cursor_x, 40)
    QToolTip.hideText()
    qapp.processEvents()
    QToolTip.showText(QCursor.pos(), text, host)
    return next(w for w in QApplication.allWidgets()
                if w.metaObject().className() == TIP_CLASS)


def test_qt_places_its_real_tooltip_where_the_rule_says(qapp, placed) -> None:
    host = QWidget()
    host.resize(200, 100)
    host.show()
    area = QGuiApplication.primaryScreen().availableGeometry()
    edges = (area.left(), area.left() + area.width())
    for index, (cursor_x, text) in enumerate((
            (100, "A hover sentence long enough to have somewhere to go"),
            (area.right() - 30, "Another sentence, near the right edge"),
            (area.right() - 5, "short"),
            (area.left(), "Move the playhead back to the start"))):
        tip = _show(qapp, host, cursor_x, f"{text} {'.' * index}")
        assert tip.x() == tip_left(cursor_x, tip.width(), *edges)
    host.hide()


def test_without_the_filter_qt_flips_the_box_past_the_pointer(qapp) -> None:
    """The behaviour being corrected, pinned — so nobody removes the
    filter thinking Qt would do the right thing on its own."""
    host = QWidget()
    host.resize(200, 100)
    host.show()
    area = QGuiApplication.primaryScreen().availableGeometry()
    tip = _show(qapp, host, area.right() - 30,
                "A hover sentence far too long to fit at the right edge")
    assert tip.width() > 40                  # it really does not fit
    assert tip.x() + tip.width() < area.right() - 30
    QToolTip.hideText()
    host.hide()
