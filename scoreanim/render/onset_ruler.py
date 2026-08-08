"""The tick ruler above a system while a re-timeable element is
selected: bars deepest, beats shorter, eighths shorter still (the
Dorico grid look), every tick hanging from ONE top line — top-aligned,
Marcus's call 2026-08-09.

Not a scene item any more (also 2026-08-09): a scene item is painted
UNDER the view's mask, so system mode clipped the ruler away. The view
now calls `overlay_painter` after every mask, and this module is just
the drawing — the controller (ui/onset_cursor.py) owns when and where.
"""
from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPen

from scoreanim.core.animation import GridTick, TickRank

_DEPTHS = {TickRank.BAR: 30.0, TickRank.BEAT: 20.0,
           TickRank.EIGHTH: 12.0}    # page units below the shared top
_GAP = 10.0                          # air between ruler and system ink
_COLOR = "#888888"


def ruler_top(system_top: float) -> float:
    """The shared top line: high enough that the deepest tick (a bar)
    still clears the system's ink by the gap."""
    return system_top - _GAP - _DEPTHS[TickRank.BAR]


def paint_ticks(painter, ticks: Sequence[GridTick], top: float) -> None:
    """Every tick starts at `top` and hangs down by its rank's depth,
    so the tops align and the bars reach closest to the music."""
    pen = QPen(QColor(_COLOR))
    pen.setWidthF(1.2)
    pen.setCosmetic(True)
    painter.setPen(pen)
    for tick in ticks:
        painter.drawLine(QPointF(tick.x, top),
                         QPointF(tick.x, top + _DEPTHS[tick.rank]))
