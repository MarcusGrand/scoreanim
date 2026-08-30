"""The stage's scroll indicators: they appear while the user is zooming
or scrolling, and they can be grabbed and dragged like any scrollbar.

Why we paint our own instead of using Qt's. Measured on this machine
(spikes/stage_gestures.py): the macOS style here reports
`SH_ScrollBar_Transient = False`, so Qt's bars are the kind that reserve
space — turning them on shrinks the viewport from 600x500 to 580x480.
Showing and hiding them as the user scrolls would therefore shove the
score sideways by 20 px at the start of every gesture. Scrolling itself
works fine with the bars switched off (the scroll range stays live), so
the view keeps them permanently off and we draw the hint instead.

They started (M2) as feedback only — "there is more score this way, and
here is where you are" — on the reasoning that they were gone before
you could reach for one. That was the wrong way round (Marcus,
2026-08-29): something that looks like a scrollbar has to behave like
one. So they now come up when the pointer reaches for the edge they
live on, they hold still while it is there, and a press anywhere along
that edge scrolls — dragging the bar, or clicking the track to jump the
bar to the pointer and carry on dragging.

A bar says which of those it is up to. Resting it is thin and dark;
close enough to grab it widens, which is a promise that a press right
here will take it; in the hand it goes light. The wide look and the
band `press` accepts are the same number, so the promise cannot come
apart from what actually happens.

The view owns the mouse gestures on the stage, so it offers each press,
move and release here FIRST (`StageView.mousePressEvent`); everything
this declines carries on to selection and nudging as before.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import (
    Property, QObject, QPointF, QPropertyAnimation, QRectF, QTimer,
)
from PySide6.QtGui import QColor, QPainter

from scoreanim.ui.theme import palette

_HOLD_MS = 700           # fully visible after the last gesture
_FADE_MS = 250
_MARGIN = 3.0            # gap from the viewport edge
_MIN_LENGTH = 24.0       # a very deep zoom must still leave something to see
# A bar has two widths, and the wide one is a promise: it means a press
# right here takes the bar. So the reading band is worked out FROM the
# wide bar rather than picked separately — the two cannot drift apart
# and start lying to each other.
_THICKNESS = 6.0         # resting, in device pixels
_READY_THICKNESS = 11.0  # grabbable: the pointer is in reach of it
_GRAB = _MARGIN + _READY_THICKNESS + 2.0
# How close the pointer has to come before the bar shows itself at all.
# Wider than the grab band on purpose: the bar arrives first, and then
# fattens as the hand keeps coming.
_REACH = 32.0
# Dark translucent fill with a pale outline, so the bar reads both on the
# white page and on the dark letterbox. Grabbable is the same bar, more
# solid; in the hand it goes light instead, which no amount of black can
# be mistaken for. The light fill needs a dark outline for the same
# reason the dark one needs a pale one.
_FILL = QColor(0, 0, 0, 110)
_FILL_READY = QColor(0, 0, 0, 165)
_FILL_HELD = QColor(palette.DIM)
_FILL_HELD.setAlpha(235)
_EDGE = QColor(255, 255, 255, 70)
_EDGE_HELD = QColor(0, 0, 0, 70)

VERTICAL = "vertical"
HORIZONTAL = "horizontal"


@dataclass
class _Drag:
    """A bar in the hand: which one, where along it the press landed,
    and what the scrollbar read at that moment. Everything else is
    worked out from where the pointer is now."""
    axis: str
    origin: float        # device px along the track
    value: int           # the scrollbar's value at the press


class TransientScrollbars(QObject):
    """Draws, fades and drags the two indicators for one scrolling view.

    The view calls `poke()` whenever it moves or zooms itself, `paint()`
    from its own `paintEvent`, and offers the mouse to `hover`, `press`,
    `drag`, `release` and `leave`. Bar geometry is read from the view's
    scrollbars every time it is needed, so there is no state to keep in
    step — only the drag in progress and how close the pointer is.
    """

    def __init__(self, view) -> None:
        super().__init__(view)
        self._view = view
        self._opacity = 0.0
        self._drag: _Drag | None = None
        self._reaching: str | None = None      # axis the pointer is near
        self._ready: str | None = None         # axis it could grab now
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.timeout.connect(self._start_fade)
        self._fade = QPropertyAnimation(self, b"opacity", self)
        self._fade.setDuration(_FADE_MS)
        self._fade.setEndValue(0.0)

    # -- the property the fade animates ------------------------------------

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, value: float) -> None:
        self._opacity = float(value)
        self._view.viewport().update()

    opacity = Property(float, _get_opacity, _set_opacity)

    def _start_fade(self) -> None:
        """The hold is over: fade from wherever the opacity now is —
        unless a bar is in the hand or under the pointer, in which case
        it stays up and the countdown starts again."""
        if self._drag is not None or self._reaching is not None:
            self._hold.start(_HOLD_MS)
            return
        self._fade.setStartValue(self._opacity)
        self._fade.start()

    # -- what the view calls -----------------------------------------------

    def poke(self) -> None:
        """The user just scrolled or zoomed: show the bars, restart the
        countdown to hiding them again."""
        self._fade.stop()
        self._set_opacity(1.0)
        self._hold.start(_HOLD_MS)

    def hover(self, pos: QPointF) -> None:
        """The pointer moved with no button down. Reaching for the edge
        a bar lives on brings that bar up and keeps it up; coming close
        enough to grab it widens it, which is how it says so."""
        self._reaching = self._axis_at(pos, _REACH)
        self._ready = self._axis_at(pos, _GRAB)
        if self._reaching is not None:
            self.poke()
        self._view.viewport().update()

    def leave(self) -> None:
        """The pointer left the stage: nothing is being reached for, so
        the bars go back to resting and may fade on their own again."""
        self._reaching = None
        self._ready = None
        self._view.viewport().update()

    def press(self, pos: QPointF) -> bool:
        """Take this press if it landed on a bar the user can see. On
        the track rather than the bar, the bar jumps to the pointer
        first — then either way the drag is on."""
        if self._opacity <= 0.0:
            return False                  # invisible: nothing to grab
        axis = self._axis_at(pos, _GRAB)
        if axis is None:
            return False
        scrollbar = self._scrollbar(axis)
        along = self._along(axis, pos)
        bar = self._bar(axis)
        if bar is None:
            return False
        low, length = self._extent(axis, bar)
        if not low <= along <= low + length:
            scrollbar.setValue(
                self._value_for_offset(axis, along - length / 2.0))
        self._drag = _Drag(axis, along, scrollbar.value())
        self.poke()
        return True

    def drag(self, pos: QPointF) -> bool:
        """Carry a press that landed on a bar. The pointer's travel
        along the track is the bar's travel, so the score keeps up with
        the hand."""
        if self._drag is None:
            return False
        scrollbar = self._scrollbar(self._drag.axis)
        travel = self._travel(self._drag.axis)
        if travel > 0.0:
            moved = self._along(self._drag.axis, pos) - self._drag.origin
            span = scrollbar.maximum() - scrollbar.minimum()
            scrollbar.setValue(
                self._drag.value + round(moved / travel * span))
        self.poke()
        return True

    def release(self, pos: QPointF) -> bool:
        """Let go. True when there was a bar in the hand, so the view
        knows this release was not a click on the score. The bar stays
        wide only if the hand is still on it."""
        if self._drag is None:
            return False
        self._drag = None
        self.hover(pos)
        self.poke()
        return True

    def paint(self, painter: QPainter) -> None:
        """Overlay both bars, in viewport pixels, each in the look its
        own state has earned. Cheap no-op when hidden."""
        if self._opacity <= 0.0:
            return
        painter.setOpacity(self._opacity)
        for axis in (VERTICAL, HORIZONTAL):
            bar = self._bar(axis)
            if bar is None:
                continue
            held = self._held(axis)
            painter.setPen(_EDGE_HELD if held else _EDGE)
            painter.setBrush(_FILL_HELD if held else
                             _FILL_READY if self._grabbable(axis) else _FILL)
            radius = self._thickness(axis) / 2.0
            painter.drawRoundedRect(bar, radius, radius)

    # -- what state a bar is in --------------------------------------------

    def _held(self, axis: str) -> bool:
        """Is this bar in the hand right now?"""
        return self._drag is not None and self._drag.axis == axis

    def _grabbable(self, axis: str) -> bool:
        """Would a press take this bar? This is what the wide look
        promises, so the drawing and `press` read the same answer."""
        return self._held(axis) or (self._opacity > 0.0
                                    and self._ready == axis)

    def _thickness(self, axis: str) -> float:
        return _READY_THICKNESS if self._grabbable(axis) else _THICKNESS

    # -- geometry ----------------------------------------------------------

    def _scrollbar(self, axis: str):
        return self._view.verticalScrollBar() if axis == VERTICAL \
            else self._view.horizontalScrollBar()

    @staticmethod
    def _along(axis: str, pos: QPointF) -> float:
        """Where a point sits ALONG a track, in device pixels."""
        return pos.y() if axis == VERTICAL else pos.x()

    @staticmethod
    def _extent(axis: str, bar: QRectF) -> tuple[float, float]:
        """A bar's (start, length) along its own track."""
        return (bar.top(), bar.height()) if axis == VERTICAL \
            else (bar.left(), bar.width())

    def _track(self, axis: str) -> float:
        rect = self._view.viewport().rect()
        return rect.height() if axis == VERTICAL else rect.width()

    def _bar(self, axis: str) -> QRectF | None:
        """Where this axis's indicator is, or None when the axis already
        fits — in fit mode that means neither of them."""
        rect = QRectF(self._view.viewport().rect())
        span = self._span(self._scrollbar(axis), self._track(axis))
        if span is None:
            return None
        offset, length = span
        # it grows INWARD: the outer edge stays put, so a bar that
        # fattens under the hand does not move out from under it
        thickness = self._thickness(axis)
        if axis == VERTICAL:
            return QRectF(rect.right() - _MARGIN - thickness,
                          rect.top() + offset, thickness, length)
        return QRectF(rect.left() + offset,
                      rect.bottom() - _MARGIN - thickness,
                      length, thickness)

    def _axis_at(self, pos: QPointF, reach: float) -> str | None:
        """Which bar the pointer is at, within `reach` of the edge it
        lives on. An axis with no bar is never the answer, and the
        vertical one wins in the corner where the two bands meet."""
        rect = QRectF(self._view.viewport().rect())
        if self._bar(VERTICAL) is not None and pos.x() >= rect.right() - reach:
            return VERTICAL
        if self._bar(HORIZONTAL) is not None \
                and pos.y() >= rect.bottom() - reach:
            return HORIZONTAL
        return None

    def _travel(self, axis: str) -> float:
        """How far the bar itself can move along its track."""
        span = self._span(self._scrollbar(axis), self._track(axis))
        if span is None:
            return 0.0
        return self._track(axis) - span[1]

    def _value_for_offset(self, axis: str, offset: float) -> int:
        """The scrollbar value that would put the bar's start at
        `offset` — `_span`'s position math, run backwards."""
        scrollbar = self._scrollbar(axis)
        travel = self._travel(axis)
        low, high = scrollbar.minimum(), scrollbar.maximum()
        if travel <= 0.0:
            return low
        position = min(1.0, max(0.0, offset / travel))
        return low + round(position * (high - low))

    @staticmethod
    def _span(scrollbar, track: float) -> tuple[float, float] | None:
        """Where the visible slice sits on this axis, as (offset, length)
        in device pixels along a `track`-long edge, or None if the whole
        axis already fits."""
        low, high = scrollbar.minimum(), scrollbar.maximum()
        page = scrollbar.pageStep()
        if high <= low or page <= 0 or track <= _MIN_LENGTH:
            return None
        total = float(high - low + page)           # full extent, in bar units
        length = max(_MIN_LENGTH, track * page / total)
        travel = track - length
        position = (scrollbar.value() - low) / float(high - low)
        return travel * position, length
