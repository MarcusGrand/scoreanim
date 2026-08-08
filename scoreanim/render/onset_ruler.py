"""The tick ruler above a system while a re-timeable element is
selected: bars tallest, beats smaller, eighths smaller still (the
Dorico grid look). Painted as ONE item, hit-transparent like the
system groups, so it never competes with selection or the cursor.
Neutral grey, legible on the light and the dark page alike.
"""
from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from scoreanim.core.animation import GridTick, TickRank

_HEIGHTS = {TickRank.BAR: 30.0, TickRank.BEAT: 20.0,
            TickRank.EIGHTH: 12.0}    # page units below the baseline
_GAP = 10.0                           # air between ruler and system ink
_COLOR = "#888888"


class OnsetRulerItem(QGraphicsItem):
    def __init__(self) -> None:
        super().__init__()
        self._ticks: tuple[GridTick, ...] = ()
        self._baseline = 0.0          # scene y the ticks hang from
        self.setZValue(1.0)           # above the ink, beside the cursor

    def set_ticks(self, ticks: Sequence[GridTick],
                  system_top: float) -> None:
        self.prepareGeometryChange()
        self._ticks = tuple(ticks)
        self._baseline = system_top - _GAP
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        if not self._ticks:
            return QRectF()
        xs = [t.x for t in self._ticks]
        top = self._baseline - max(_HEIGHTS.values())
        return QRectF(min(xs) - 1.0, top,
                      max(xs) - min(xs) + 2.0,
                      self._baseline - top)

    def shape(self) -> QPainterPath:  # noqa: N802
        return QPainterPath()         # hit-transparent (the group idiom)

    def paint(self, painter, option, widget=None) -> None:  # noqa: N802
        pen = QPen(QColor(_COLOR))
        pen.setWidthF(1.2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for tick in self._ticks:
            painter.drawLine(
                QPointF(tick.x, self._baseline - _HEIGHTS[tick.rank]),
                QPointF(tick.x, self._baseline))
