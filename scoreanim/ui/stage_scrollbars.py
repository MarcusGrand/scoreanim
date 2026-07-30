"""Thin scroll indicators for the stage: they appear while the user is
zooming or scrolling and fade out once the view settles.

Why we paint our own instead of using Qt's scrollbars. Measured on this
machine (spikes/stage_gestures.py): the macOS style here reports
`SH_ScrollBar_Transient = False`, so Qt's bars are the kind that reserve
space — turning them on shrinks the viewport from 600x500 to 580x480.
Showing and hiding them as the user scrolls would therefore shove the
score sideways by 20 px at the start of every gesture. Scrolling itself
works fine with the bars switched off (the scroll range stays live), so
the view keeps them permanently off and we draw a hint instead.

The indicators are feedback only — they say "there is more score this
way, and here is where you are". They are not draggable; they are gone
before you could reach for one.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property, QObject, QPropertyAnimation, QRectF, QTimer,
)
from PySide6.QtGui import QColor, QPainter

_HOLD_MS = 700           # fully visible after the last gesture
_FADE_MS = 250
_THICKNESS = 6.0         # bar thickness in device pixels
_MARGIN = 3.0            # gap from the viewport edge
_MIN_LENGTH = 24.0       # a very deep zoom must still leave something to see
# Dark translucent fill with a pale outline, so the bar reads both on the
# white page and on the dark letterbox.
_FILL = QColor(0, 0, 0, 110)
_EDGE = QColor(255, 255, 255, 70)


class TransientScrollbars(QObject):
    """Draws and fades the two indicators for one scrolling view.

    The view calls `poke()` whenever the user moves or zooms it, and
    `paint()` from its own `paintEvent`. Nothing else is needed — the
    bar geometry is read from the view's scrollbars at paint time, so
    there is no state to keep in step.
    """

    def __init__(self, view) -> None:
        super().__init__(view)
        self._view = view
        self._opacity = 0.0
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
        """The hold is over: fade from wherever the opacity now is."""
        self._fade.setStartValue(self._opacity)
        self._fade.start()

    # -- what the view calls -----------------------------------------------

    def poke(self) -> None:
        """The user just scrolled or zoomed: show the bars, restart the
        countdown to hiding them again."""
        self._fade.stop()
        self._set_opacity(1.0)
        self._hold.start(_HOLD_MS)

    def paint(self, painter: QPainter) -> None:
        """Overlay both bars, in viewport pixels. Cheap no-op when hidden."""
        if self._opacity <= 0.0:
            return
        rect = QRectF(self._view.viewport().rect())
        painter.setOpacity(self._opacity)
        painter.setPen(_EDGE)
        painter.setBrush(_FILL)
        for bar in self._bars(rect):
            radius = _THICKNESS / 2.0
            painter.drawRoundedRect(bar, radius, radius)

    # -- geometry ----------------------------------------------------------

    def _bars(self, rect: QRectF) -> list[QRectF]:
        """The bars worth drawing. An axis with nothing hidden off-screen
        gets none — in fit mode that means no indicators at all."""
        bars = []
        vertical = self._span(self._view.verticalScrollBar(), rect.height())
        if vertical is not None:
            offset, length = vertical
            bars.append(QRectF(rect.right() - _MARGIN - _THICKNESS,
                               rect.top() + offset, _THICKNESS, length))
        horizontal = self._span(self._view.horizontalScrollBar(), rect.width())
        if horizontal is not None:
            offset, length = horizontal
            bars.append(QRectF(rect.left() + offset,
                               rect.bottom() - _MARGIN - _THICKNESS,
                               length, _THICKNESS))
        return bars

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
