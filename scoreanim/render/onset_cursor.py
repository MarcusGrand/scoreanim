"""The onset cursor: a vertical line over the ink, marking where the
selected element fires right now — the first true overlay item in the
score scene (selection is a tint, the mask is view-painted).

Geometry only. The drag is view-level (ui/onset_cursor.py through the
DragRouter), so this item handles no mouse events; it is built in
Python and added with addItem, never scene.addLine (the shiboken
teardown trap noted in render/scene.py).
"""
from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsLineItem

from scoreanim.core.selection.highlight import SELECTION_COLOR

_WIDTH = 2.0            # device pixels — the pen is cosmetic
_ACTIVE_WIDTH = 3.5     # a little thicker while the hand holds it
GRAB_TOLERANCE = 10.0   # page units either side of the line


class OnsetCursorItem(QGraphicsLineItem):
    def __init__(self) -> None:
        super().__init__()
        pen = QPen(QColor(SELECTION_COLOR))
        pen.setWidthF(_WIDTH)
        pen.setCosmetic(True)        # constant on screen at every zoom
        self.setPen(pen)
        self.setZValue(1.0)          # above the ink, which sits at 0
        # the standard affordance: the pointer says "grabbable" over
        # the whole grab band (shape() below), Qt handles the hover
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_span(self, x: float, top: float, bottom: float) -> None:
        self.setLine(QLineF(x, top, x, bottom))

    def set_active(self, active: bool) -> None:
        """Thicken while dragged — the pressed look."""
        pen = self.pen()
        pen.setWidthF(_ACTIVE_WIDTH if active else _WIDTH)
        self.setPen(pen)

    def shape(self) -> QPainterPath:  # noqa: N802
        """The grab band, not the hairline: this is what Qt hovers the
        pointing hand over, and what the probe tests against."""
        line = self.line()
        path = QPainterPath()
        path.addRect(line.x1() - GRAB_TOLERANCE, line.y1(),
                     2 * GRAB_TOLERANCE, line.y2() - line.y1())
        return path

    @property
    def x_pos(self) -> float:
        return self.line().x1()

    def grabs(self, scene_pos: QPointF) -> bool:
        """Is a press close enough to take the line? A thin line is a
        mean target, so the grab band is wider than the ink."""
        line = self.line()
        return (abs(scene_pos.x() - line.x1()) <= GRAB_TOLERANCE
                and line.y1() <= scene_pos.y() <= line.y2())
