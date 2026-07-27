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
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
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

    def shape(self):  # noqa: N802
        """Hit-transparent (M2.3): hits come from real ink only.

        Qt's default shape() is boundingRect() as a path, and ours is
        childrenBoundingRect() — so without this a parent answers a
        click anywhere in its children's united bbox, and a STAFF_LINES
        element (which spans its whole system) is a candidate for every
        click on the page. The M2.0 census measured exactly that: a
        notehead click also returned the staff lines and the part label.
        Children are stock QGraphicsPathItem/SimpleTextItem whose own
        shape() includes the pen stroke, so thin stems and staff lines
        stay clickable through them; the selection controller walks
        child -> parent to recover identity.

        Painting is unaffected (paint() is empty and boundingRect still
        reports the true extent, so no clipping or culling changes)."""
        return QPainterPath()

    def paint(self, painter, option, widget=None) -> None:  # noqa: N802
        pass


class ElementItem(GroupItem):
    """All QGraphicsItems of one RenderedElement (or one stage text).

    ``bbox``/``anchor`` (page == scene coordinates) and ``system`` come
    from the RenderedElement: the anchor is the transform origin for
    scale effects (pop), the system keys the reveal edge that drives
    spanner clip-grow.

    **This item is the one compositing point for how an element looks.**
    Its appearance is a function of independent INPUTS, each written by
    the layer that owns it and never by the others, composed here:

      authored color   `set_color`            — document intent (part
                                                tint, element override)
      animation state  `set_animated_opacity` — the effect evaluator
                       `setScale`

    Each setter stores its own input and re-derives the painted result,
    so writing one never destroys another and no caller has to know what
    else is currently applied. That matters concretely: DocumentSync's
    style pass is a DIFF cache, so anything that overwrote the authored
    color behind its back would leave it believing a color it can no
    longer restore."""

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
        # -- composition inputs (see the class docstring) --
        self._color = QColor(DEFAULT_COLOR)      # authored, from the doc
        self._animated_opacity = 1.0             # from the evaluator
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
        """Set the AUTHORED ink color — document intent (a part tint or
        a per-element override). None restores black."""
        self._color = QColor(color) if color is not None \
            else QColor(DEFAULT_COLOR)
        self._repaint()

    def set_animated_opacity(self, value: float) -> None:
        """Set the opacity the effect evaluator computed for this element
        at the current t. Goes through the composite rather than
        setOpacity() directly, so the evaluator stays the sole owner of
        this input without owning the painted result."""
        self._animated_opacity = value
        self._recompose_opacity()

    @property
    def color(self) -> QColor:
        """The AUTHORED color — what the document says, not necessarily
        what is on screen."""
        return QColor(self._color)

    @property
    def animated_opacity(self) -> float:
        """The evaluator's opacity for the current t, readable back so a
        caller can tell the animation input apart from the composite."""
        return self._animated_opacity

    # -- composition -------------------------------------------------------

    def _paint_color(self) -> QColor:
        return self._color

    def _paint_opacity(self) -> float:
        return self._animated_opacity

    def _repaint(self) -> None:
        """Push the composed color onto every color-tracking child."""
        color = self._paint_color()
        for item, fill_tracks, stroke_tracks in self._tracked:
            if fill_tracks:
                item.setBrush(QBrush(color))
            if stroke_tracks and isinstance(item, QGraphicsPathItem):
                pen = item.pen()
                pen.setColor(color)
                item.setPen(pen)

    def _recompose_opacity(self) -> None:
        self.setOpacity(self._paint_opacity())


class RevealPathItem(QGraphicsPathItem):
    """A path child revealed by a growing clip rect (spanners, Phase 5.2).

    The clip is a right edge in the item's LOCAL coordinates, applied in
    paint() — no shape()/boundingRect() games, no scene re-indexing per
    move, repaint cost is this one path. The edge is clamped to the
    path's own bounds so a fully-hidden or fully-shown spanner is a
    cached no-op; ``None`` means unclipped (fully revealed).

    Construction starts at ``-inf`` (fully HIDDEN): a child whose
    (system, part) key never receives an edge fails safe as invisible
    ink over its floor-opacity ghost, instead of painting fully from
    t=0 (the FINDING-2 silent early-reveal, fixed 2026-07-22). The
    applier warns loudly about such curve-less keys."""

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self._clip_right: float | None = float("-inf")
        self._inverse = None                 # lazily inverted transform

    @property
    def clip_right(self) -> float | None:
        """Local-coords clip edge; None = fully revealed, -inf = the
        never-edged construction default (fully hidden)."""
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
