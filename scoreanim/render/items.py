"""Scene item classes: one ElementItem per RenderedElement.

The path child a spanner reveals by clip-grow lives next door, in
`render/reveal_item.py`, and the SVG paint translation the scene
builder shares with these items is in `render/svg_paint.py`.

A plain QGraphicsItem parent (empty paint) rather than QGraphicsItemGroup
— groups grab child events, which we don't want once click-to-select
arrives. Children are stock QGraphicsPathItem / QGraphicsSimpleTextItem;
each is registered on construction with whether its fill/stroke tracks
the element color (SVG default black / currentColor) or is fixed (explicit
fills like the gray lyricist), so recoloring touches exactly the right
paints.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainterPath
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPathItem,
                               QGraphicsSimpleTextItem)

from scoreanim.core.score.identity import ElementIdentity
from scoreanim.core.selection.highlight import (SELECTION_MIN_OPACITY,
                                                selection_color_for)
from scoreanim.render.glow_sprite import GlowSlot
from scoreanim.render.reveal_item import RevealPathItem
from scoreanim.render.svg_paint import DEFAULT_COLOR


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
    from the RenderedElement: the anchor is the element's own centre,
    the system keys the reveal edge that drives spanner clip-grow. What
    a scale effect turns around is the separate ``scale_pivot`` — see
    `set_scale_pivot` — and how far it may grow is ``scale_cap``.

    **This item is the one compositing point for how an element looks.**
    Its appearance is a function of independent INPUTS, each written by
    the layer that owns it and never by the others, composed here:

      ink color        `set_ink_color`        — document intent, the
                                                whole page's ink
      authored color   `set_color`            — document intent (part
                                                tint, element override)
      layout nudge     `set_offset`             document intent (dx/dy)
      ghost floor      `set_ghost_opacity`      the document's floor
      glow style       `set_glow_style`       — document intent (the
                                                halo's colour and size)
      animation state  `set_animated_opacity` — the effect evaluator
                       `set_animated_offset`
                       `setScale`
                       `set_glow`
      selection        `set_selected`         — transient UI state

    Each setter stores its own input and re-derives the painted result,
    so writing one never destroys another and no caller has to know what
    else is currently applied. That matters concretely: DocumentSync's
    style pass is a DIFF cache, so anything that overwrote the authored
    color behind its back would leave it believing a color it can no
    longer restore. The ink is that same argument one input further
    down: it is what this element paints as when nothing has authored a
    color for it, an authored color always wins, and keeping the two
    apart is what lets a page recolor and a part tint arrive in either
    order.

    **Selection composites last, and touches only what it must.** It
    replaces the color and raises an opacity floor — it never touches
    scale (so a selected note still pops), never touches the reveal clip
    (so a selected spanner still grows), and never writes back into the
    inputs above. Deselecting re-derives the composite of the others;
    nothing is remembered. The floor is what makes the rule work at all:
    the document's ghost floor may be 0, at which point a tint on
    pre-trigger ink would otherwise be invisible."""

    def __init__(self, identity: ElementIdentity | None = None,
                 bbox: QRectF | None = None,
                 anchor: QPointF | None = None,
                 system: int | None = None) -> None:
        super().__init__()
        self.identity = identity
        # The registry key this item is filed under in ScoreScenes.items,
        # set there. Engraved items could derive it from `identity`, but
        # stage texts have none (identity=None is what makes them
        # unselectable, D5) — and M3's in-place text editing must reach
        # both families, so one uniform back-reference beats two paths.
        self.element_key = None
        self.bbox = bbox
        self.anchor = anchor
        self.system = system
        # Where a scale effect pivots, set by ScoreScenes from the pure
        # policy (core/animation/scale_groups.py): each notehead turns
        # around its own centre, and the ink hanging off it follows the
        # head it belongs to. None means this ink never scales.
        self.scale_pivot: QPointF | None = None
        # The largest scale this ink may take, from the same pure policy
        # (core/animation/stem_caps.py): a stem stops at its beam. None
        # means no ceiling.
        self.scale_cap: float | None = None
        # -- composition inputs (see the class docstring) --
        self._authored: QColor | None = None     # a tint or an override
        self._ink = QColor(DEFAULT_COLOR)        # the document's ink
        self._animated_opacity = 1.0             # from the evaluator
        self._doc_offset = (0.0, 0.0)            # the document's nudge
        self._animated_offset = (0.0, 0.0)       # from the evaluator
        self._ghost_opacity = 1.0                # document floor, ghosts
        self._selected = False                   # transient UI state
        # The outer glow: the halo's colour and size are document
        # intent, how brightly it burns comes from the evaluator, and
        # the pre-rendered pixmap child behind both is its own small
        # object (render/glow_sprite.py).
        self._glow = GlowSlot(self, DEFAULT_COLOR)
        # (item, fill tracks element color, stroke tracks element color)
        self._tracked: list[tuple[QGraphicsItem, bool, bool]] = []
        self._reveal_children: list[RevealPathItem] = []
        self._ghost_children: list[QGraphicsPathItem] = []
        # last reveal edge pushed, so a move can re-derive the clip that
        # the move itself invalidated (see set_offset)
        self._reveal_edge: float | None = None

    def set_scale_pivot(self, pivot: QPointF | None) -> None:
        """The point a scale effect turns around (page == scene ==
        item-local coords; the parent itself carries no transform)."""
        self.scale_pivot = pivot
        if pivot is not None:
            self.setTransformOriginPoint(pivot)

    def set_scale_cap(self, cap: float | None) -> None:
        """The ceiling a scale effect is clamped to. A stem carries one
        so it can swell without pushing through its beam."""
        self.scale_cap = cap

    def add_path_child(self, item: QGraphicsPathItem,
                       fill_tracks: bool, stroke_tracks: bool,
                       ghost: bool = False) -> None:
        item.setParentItem(self)
        if fill_tracks or stroke_tracks:
            self._tracked.append((item, fill_tracks, stroke_tracks))
        if isinstance(item, RevealPathItem):
            self._reveal_children.append(item)
        if ghost:
            self._ghost_children.append(item)
            item.setOpacity(self._paint_ghost_opacity())

    def set_reveal_edge(self, scene_x: float) -> bool:
        """Move every reveal-clipped child's right edge to the scene x.
        Returns whether anything visually changed (the edge is clamped
        per child, so a saturated spanner is a no-op)."""
        self._reveal_edge = scene_x
        changed = False
        for child in self._reveal_children:
            changed |= child.set_clip_right(scene_x)
        return changed

    def refresh_reveal_clip(self) -> None:
        """Re-derive every reveal child's clip after this item's SCENE
        transform changed — it moved, or a parent group scaled. See
        `_recompose_pos` for why both halves are needed."""
        for child in self._reveal_children:
            child.invalidate_transform_cache()
        if self._reveal_edge is not None:
            self.set_reveal_edge(self._reveal_edge)

    def set_offset(self, dx: float, dy: float) -> None:
        """Apply the document's layout-override delta (M3.2). One of the
        two things that move this item; the animation is the other, and
        `_recompose_pos` adds them."""
        if (dx, dy) == self._doc_offset:
            return
        self._doc_offset = (dx, dy)
        self._recompose_pos()

    def set_animated_offset(self, dx: float, dy: float) -> None:
        """Set how far the effect evaluator wants this element from its
        engraved place at the current t (the slide effect). Stored apart
        from the document's nudge, so a nudged note slides to its NUDGED
        place and neither writer overwrites the other."""
        if (dx, dy) == self._animated_offset:
            return
        self._animated_offset = (dx, dy)
        self._recompose_pos()

    def set_animated_offset_x(self, value: float) -> None:
        """One axis of the animated offset — what the applier's fixed
        property map reaches, since each property applies on its own."""
        self.set_animated_offset(value, self._animated_offset[1])

    def set_animated_offset_y(self, value: float) -> None:
        self.set_animated_offset(self._animated_offset[0], value)

    @property
    def animated_offset(self) -> tuple[float, float]:
        """The evaluator's offset for the current t, readable back so a
        caller can tell the animation input apart from the position."""
        return self._animated_offset

    @property
    def reveal_children(self) -> tuple[RevealPathItem, ...]:
        return tuple(self._reveal_children)

    def add_text_child(self, item: QGraphicsSimpleTextItem,
                       fill_tracks: bool) -> None:
        item.setParentItem(self)
        if fill_tracks:
            self._tracked.append((item, True, False))

    def set_color(self, color: QColor | None) -> None:
        """Set the AUTHORED ink color — document intent (a part tint or
        a per-element override). None means nothing is authored, so the
        element falls back to the document's ink color."""
        self._authored = QColor(color) if color is not None else None
        self._repaint()

    def set_ink_color(self, color: QColor) -> None:
        """Set the document's ink color — what this element paints as
        when no part tint and no override has claimed it. Never written
        into `_authored`: a page recolor must not look like authored
        intent to DocumentSync's diff cache."""
        self._ink = QColor(color)
        self._repaint()

    def set_animated_opacity(self, value: float) -> None:
        """Set the opacity the effect evaluator computed for this element
        at the current t. Goes through the composite rather than
        setOpacity() directly, so the evaluator stays the sole owner of
        this input without owning the painted result."""
        self._animated_opacity = value
        self._recompose_opacity()

    def set_glow_style(self, color: QColor, radius: float,
                       passes: float = 1.0) -> None:
        """What this element's halo looks like when it is lit: document
        intent, written once when the document changes, never per
        frame."""
        self._glow.set_style(color, radius, passes)

    def set_glow(self, value: float) -> None:
        """Set how brightly the effect evaluator wants this element's
        halo to burn at the current t."""
        self._glow.set_strength(value)

    @property
    def glow_strength(self) -> float:
        """The evaluator's glow for the current t, readable back so a
        caller can tell the animation input apart from the halo."""
        return self._glow.strength

    def set_ghost_opacity(self, value: float) -> None:
        """Set the document's ghost floor for this element's spanner
        ghost children (0 is allowed — an invisible ghost score)."""
        self._ghost_opacity = value
        self._recompose_ghosts()

    def set_selected(self, selected: bool) -> None:
        """Mark/unmark this element as the transient stage selection.
        Never document state, never undoable (rule 13)."""
        if selected == self._selected:
            return
        self._selected = selected
        self._repaint()
        self._recompose_opacity()
        self._recompose_ghosts()

    @property
    def color(self) -> QColor:
        """What the document says this element's color is, which is not
        necessarily what is on screen (selection tints over the top).
        The authored color if one was written, otherwise the page's
        ink."""
        return QColor(self._authored if self._authored is not None
                      else self._ink)

    @property
    def authored_color(self) -> QColor | None:
        """Only the authored half — None when nothing has claimed this
        element and it is simply painting the page's ink."""
        return QColor(self._authored) if self._authored is not None else None

    @property
    def animated_opacity(self) -> float:
        """The evaluator's opacity for the current t, readable back so a
        caller can tell the animation input apart from the composite."""
        return self._animated_opacity

    @property
    def selected(self) -> bool:
        return self._selected

    # -- composition -------------------------------------------------------

    def _paint_color(self) -> QColor:
        """Authored color over ink, then the selection tint over that.
        The collision check reads the EFFECTIVE color: on a white-ink
        page what the tint must stay tellable apart from is the white,
        not a black nobody can see."""
        effective = self.color
        if not self._selected:
            return effective
        return QColor(selection_color_for(effective.name()))

    def _paint_opacity(self) -> float:
        if not self._selected:
            return self._animated_opacity
        return max(self._animated_opacity, SELECTION_MIN_OPACITY)

    def _paint_ghost_opacity(self) -> float:
        if not self._selected:
            return self._ghost_opacity
        return max(self._ghost_opacity, SELECTION_MIN_OPACITY)

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

    def _recompose_pos(self) -> None:
        """Where the item actually sits: the document's nudge plus the
        animation's offset. The one place either input reaches setPos.

        Moving the item invalidates a cache the reveal clip depends on.
        `RevealPathItem.set_clip_right` takes the edge as a SCENE x and
        maps it into local coordinates through the inverse of its scene
        transform, which it caches on first use — so after a move the
        clip lands dx off, measured exactly (spikes/nudge_reveal.py: a
        +30 nudge displaced the edge by +30.00). Invalidating makes the
        local clip track exactly −dx and stay y-independent.

        The last edge is then re-pushed, because the clip currently in
        force was computed with the stale inverse and nothing else would
        recompute it until the next tick — which never comes while
        paused, and nudging is something people do while paused.
        Spanners never receive triggers, so an animated offset does not
        reach them today; the invalidation runs either way, so the item
        stays right if one ever does."""
        x = self._doc_offset[0] + self._animated_offset[0]
        y = self._doc_offset[1] + self._animated_offset[1]
        if x == self.pos().x() and y == self.pos().y():
            return
        self.setPos(x, y)
        self.refresh_reveal_clip()

    def _recompose_opacity(self) -> None:
        self.setOpacity(self._paint_opacity())

    def _recompose_ghosts(self) -> None:
        value = self._paint_ghost_opacity()
        for child in self._ghost_children:
            child.setOpacity(value)
