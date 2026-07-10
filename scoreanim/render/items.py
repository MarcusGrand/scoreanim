"""Scene item classes: one ElementItem per RenderedElement.

A plain QGraphicsItem parent (empty paint) rather than QGraphicsItemGroup
— groups grab child events, which we don't want once click-to-select
arrives. Children are stock QGraphicsPathItem / QGraphicsSimpleTextItem;
each is registered on construction with whether its fill/stroke tracks
the element color (SVG default black / currentColor) or is fixed (explicit
fills like the gray lyricist), so recoloring touches exactly the right
paints.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPathItem,
                               QGraphicsSimpleTextItem)

from scoreanim.core.score.identity import ElementIdentity

DEFAULT_COLOR = QColor(Qt.GlobalColor.black)   # SVG initial 'color'/fill

# SVG stroke defaults differ from QPen's: butt caps (Qt default is
# square, which would lengthen every staff line and stem by half a
# width), miter joins, miter limit 4.
_SVG_CAP = Qt.PenCapStyle.FlatCap
_SVG_JOIN = Qt.PenJoinStyle.MiterJoin
_SVG_MITER_LIMIT = 4.0


def svg_pen(color: QColor, width: float) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(_SVG_CAP)
    pen.setJoinStyle(_SVG_JOIN)
    pen.setMiterLimit(_SVG_MITER_LIMIT)
    return pen


class GroupItem(QGraphicsItem):
    """Non-painting parent; geometry comes entirely from children."""

    def boundingRect(self):  # noqa: N802 (Qt naming)
        return self.childrenBoundingRect()

    def paint(self, painter, option, widget=None) -> None:  # noqa: N802
        pass


class ElementItem(GroupItem):
    """All QGraphicsItems of one RenderedElement (or one stage text)."""

    def __init__(self, identity: ElementIdentity | None = None) -> None:
        super().__init__()
        self.identity = identity
        self._color = QColor(DEFAULT_COLOR)
        # (item, fill tracks element color, stroke tracks element color)
        self._tracked: list[tuple[QGraphicsItem, bool, bool]] = []

    def add_path_child(self, item: QGraphicsPathItem,
                       fill_tracks: bool, stroke_tracks: bool) -> None:
        item.setParentItem(self)
        if fill_tracks or stroke_tracks:
            self._tracked.append((item, fill_tracks, stroke_tracks))

    def add_text_child(self, item: QGraphicsSimpleTextItem,
                       fill_tracks: bool) -> None:
        item.setParentItem(self)
        if fill_tracks:
            self._tracked.append((item, True, False))

    def set_color(self, color: QColor | None) -> None:
        """Repaint every color-tracking child; None restores black."""
        self._color = QColor(color) if color is not None else QColor(DEFAULT_COLOR)
        for item, fill_tracks, stroke_tracks in self._tracked:
            if fill_tracks:
                item.setBrush(QBrush(self._color))
            if stroke_tracks and isinstance(item, QGraphicsPathItem):
                pen = item.pen()
                pen.setColor(self._color)
                item.setPen(pen)

    @property
    def color(self) -> QColor:
        return QColor(self._color)
