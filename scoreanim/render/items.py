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

from PySide6.QtCore import QPointF, QRectF, Qt
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
    """All QGraphicsItems of one RenderedElement (or one stage text).

    ``bbox``/``anchor`` (page == scene coordinates) and ``system`` come
    from the RenderedElement: the anchor is the transform origin for
    scale effects (pop), the system keys the reveal edge that drives
    spanner clip-grow."""

    def __init__(self, identity: ElementIdentity | None = None,
                 bbox: QRectF | None = None,
                 anchor: QPointF | None = None,
                 system: int | None = None) -> None:
        super().__init__()
        self.identity = identity
        self.bbox = bbox
        self.anchor = anchor
        self.system = system
        if anchor is not None:
            # scale/pop transforms pivot on the element's stored anchor
            # (page == scene == item-local coords; the parent itself
            # carries no transform)
            self.setTransformOriginPoint(anchor)
        self._color = QColor(DEFAULT_COLOR)
        # (item, fill tracks element color, stroke tracks element color)
        self._tracked: list[tuple[QGraphicsItem, bool, bool]] = []
        self._reveal_children: list[RevealPathItem] = []

    def add_path_child(self, item: QGraphicsPathItem,
                       fill_tracks: bool, stroke_tracks: bool) -> None:
        item.setParentItem(self)
        if fill_tracks or stroke_tracks:
            self._tracked.append((item, fill_tracks, stroke_tracks))
        if isinstance(item, RevealPathItem):
            self._reveal_children.append(item)

    def set_reveal_edge(self, scene_x: float) -> bool:
        """Move every reveal-clipped child's right edge to the scene x.
        Returns whether anything visually changed (the edge is clamped
        per child, so a saturated spanner is a no-op)."""
        changed = False
        for child in self._reveal_children:
            changed |= child.set_clip_right(scene_x)
        return changed

    @property
    def reveal_children(self) -> tuple["RevealPathItem", ...]:
        return tuple(self._reveal_children)

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


class RevealPathItem(QGraphicsPathItem):
    """A path child revealed by a growing clip rect (spanners, Phase 5.2).

    The clip is a right edge in the item's LOCAL coordinates, applied in
    paint() — no shape()/boundingRect() games, no scene re-indexing per
    move, repaint cost is this one path. The edge is clamped to the
    path's own bounds so a fully-hidden or fully-shown spanner is a
    cached no-op; ``None`` means unclipped (fully revealed)."""

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self._clip_right: float | None = None
        self._inverse = None                 # lazily inverted transform

    @property
    def clip_right(self) -> float | None:
        """Local-coords clip edge; None = fully revealed."""
        return self._clip_right

    @property
    def hidden(self) -> bool:
        return (self._clip_right is not None
                and self._clip_right <= super().boundingRect().left())

    def set_clip_right(self, scene_x: float) -> bool:
        if self._inverse is None:
            inv, ok = self.sceneTransform().inverted()
            if not ok:                        # degenerate transform
                return False
            self._inverse = inv
        local_x = self._inverse.map(QPointF(scene_x, 0.0)).x()
        br = super().boundingRect()
        clip: float | None = min(max(local_x, br.left()), br.right())
        if clip >= br.right():
            clip = None                       # fully revealed
        if clip == self._clip_right:
            return False
        self._clip_right = clip
        self.update()
        return True

    def paint(self, painter, option, widget=None) -> None:  # noqa: N802
        if self._clip_right is None:
            super().paint(painter, option, widget)
            return
        br = super().boundingRect()
        if self._clip_right <= br.left():
            return                            # fully hidden
        painter.save()
        painter.setClipRect(QRectF(br.left(), br.top(),
                                   self._clip_right - br.left(),
                                   br.height()),
                            Qt.ClipOperation.IntersectClip)
        super().paint(painter, option, widget)
        painter.restore()
