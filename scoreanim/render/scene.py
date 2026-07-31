"""Layout + StageConfig → one QGraphicsScene per page, plus an ElementId
registry for per-element addressability.

One scene per page (not one scene with page offsets): the page is the
presentation unit (CLAUDE.md rule 7), scene coordinates stay identical to
page coordinates — so future click-to-select and dx/dy overrides need no
offset math — and letterboxing is exactly fitInView(sceneRect). Page flip
is just view.setScene(); all scenes stay built.

Semantics replicate the accepted SVG redraw (tools/bbox_overlay.py):
document paint order, fill None → black, fill "none" → hollow,
stroke "currentColor" → element color, pen width stroke_width or 1
(non-cosmetic, scales with the transform, as SVG strokes do).
"""

from __future__ import annotations

from typing import Mapping

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import (QGraphicsPathItem, QGraphicsRectItem,
                               QGraphicsScene)

from scoreanim.core.animation.reveal import REVEALED_KINDS
from scoreanim.core.animation.scale_groups import scale_pivots
from scoreanim.core.animation.style import StyleRules, takes_part_color
from scoreanim.core.engraving.types import Layout, PathPrimitive
from scoreanim.core.project.document import LayoutOverride
from scoreanim.core.project.stage_config import StageConfig, StageTextElement
from scoreanim.core.score.identity import ElementId, PartId
from scoreanim.render.items import (DEFAULT_COLOR, ElementItem,
                                    RevealPathItem, fill_tracks_color,
                                    svg_pen)
from scoreanim.render.qpath import to_qpainter_path, to_qtransform
from scoreanim.render.text import add_stage_text, add_text_rows


def apply_overrides(scenes: "ScoreScenes",
                    overrides: Mapping[ElementId, LayoutOverride]
                    ) -> None:
    """One-shot application of the WHOLE LayoutOverride onto FRESH
    scenes (export's analog of the window's diff-based sync passes).

    Grew out of `apply_hidden_overrides` at M3.2, and the growth is the
    point: dx/dy were unconsumed schema slots, so hiding was the only
    thing export had to replay. Now that a nudge is real, anything this
    function skips is a way for the exported frame to disagree with the
    stage — which is exactly what M3's exit criterion forbids. One
    function, every field.

    Unknown ids are skipped: override staleness is accepted
    (ARCHITECTURE §4)."""
    for eid, override in overrides.items():
        if override.hidden:
            scenes.set_element_hidden(eid, True)
        if override.dx or override.dy:
            scenes.set_element_offset(eid, override.dx, override.dy)


def apply_style_colors(scenes: "ScoreScenes", style: StyleRules) -> None:
    """Full one-shot application of the document's static ink colors
    onto FRESH scenes: part color rules, then per-element overrides on
    top — the same precedence the main window's diff-based _sync_styles
    maintains incrementally. Color scope is takes_part_color (ruling D)
    for rules and overrides alike."""
    for part, rule in style.parts.items():
        if rule.color is not None:
            scenes.set_part_color(part, QColor(rule.color))
    for eid, elem in style.elements.items():
        if elem.color is None:
            continue
        item = scenes.items.get(eid)
        if item is not None and takes_part_color(item.identity):
            item.set_color(QColor(elem.color))


class ScoreScenes:
    """All pages of one score as scenes + the element registry."""

    def __init__(self, layout: Layout, stage: StageConfig,
                 ghost_opacity: float = 0.3) -> None:
        self.items: dict[ElementId, ElementItem] = {}
        self._path_cache: dict[str, QPainterPath] = {}
        # The floor is document intent and can change after construction
        # (Phase 7.2). Each ElementItem owns its own ghost children's
        # opacity, since selection composes with it (M2.8).
        self._ghost_opacity = ghost_opacity
        self.scenes: list[QGraphicsScene] = []
        # kept by reference so export can hide the paper for
        # transparent-background frames (Phase 6, ruling R1)
        self.page_rects: list[QGraphicsRectItem] = []
        for geo in layout.pages:
            scene = QGraphicsScene(0, 0, geo.width, geo.height)
            # Python-constructed (not scene.addRect): a retained wrapper
            # for a C++-created item bus-errors in shiboken teardown once
            # the scene deletes the item first.
            rect = QGraphicsRectItem(0, 0, geo.width, geo.height)
            rect.setPen(QPen(Qt.PenStyle.NoPen))
            rect.setBrush(QBrush(QColor(Qt.GlobalColor.white)))
            scene.addItem(rect)
            self.page_rects.append(rect)
            self.scenes.append(scene)

        # Where each element's scale effect pivots — a whole note turns
        # around its noteheads' centre, so it grows and shrinks as one
        # object (core/animation/scale_groups.py owns that policy).
        pivots = scale_pivots(layout)

        for el in layout.elements:
            item = ElementItem(
                el.identity,
                bbox=QRectF(el.bbox.x, el.bbox.y, el.bbox.w, el.bbox.h),
                anchor=QPointF(el.anchor.x, el.anchor.y),
                system=el.system)
            pivot = pivots.get(el.identity.element_id)
            item.set_scale_pivot(QPointF(pivot.x, pivot.y)
                                 if pivot is not None else None)
            item.set_ghost_opacity(self._ghost_opacity)
            # Spanners reveal by clip-grow: each path gets a dimmed ghost
            # of the whole curve underneath the clipped full-opacity copy
            # (Phase 5.2 ruling — consistent with the dimmed ghost score).
            reveal = el.identity.kind in REVEALED_KINDS
            for prim in el.glyph.paths:
                if reveal:
                    self._add_path(item, prim, ghost=True)
                self._add_path(item, prim, reveal=reveal)
            for prim in el.glyph.texts:
                add_text_rows(item, prim)
            self.scenes[el.page - 1].addItem(item)
            if el.identity.element_id in self.items:
                raise ValueError(f"duplicate id {el.identity.element_id}")
            item.element_key = el.identity.element_id
            self.items[el.identity.element_id] = item

        # Stage-text items are tracked (id, page) so set_stage_texts can
        # swap just this layer — the engraved items never rebuild short
        # of a re-engrave.
        self._stage_text_pages: dict[ElementId, int] = {}
        self._add_stage_texts(stage.texts)

    def _add_stage_texts(self,
                         texts: tuple[StageTextElement, ...]) -> None:
        for text in texts:
            item = ElementItem(identity=None)
            add_stage_text(item, text)
            self.scenes[text.page - 1].addItem(item)
            item.element_key = ElementId(text.element_id)
            self.items[ElementId(text.element_id)] = item
            self._stage_text_pages[ElementId(text.element_id)] = text.page

    def set_stage_texts(self, texts: tuple[StageTextElement, ...]) -> None:
        """Replace all stage-text items (remove + re-add) — stage edits
        touch a handful of texts, so wholesale rebuild of just this
        layer; engraved items are untouched (never re-engraves)."""
        for eid, page in self._stage_text_pages.items():
            item = self.items.pop(eid)
            self.scenes[page - 1].removeItem(item)
        self._stage_text_pages = {}
        self._add_stage_texts(texts)

    def scene_for_page(self, page: int) -> QGraphicsScene:
        return self.scenes[page - 1]

    @property
    def page_count(self) -> int:
        return len(self.scenes)

    def set_page_background_visible(self, visible: bool) -> None:
        """Show/hide the white paper rects — hidden for transparent
        overlay export; the live stage always shows them."""
        for rect in self.page_rects:
            rect.setVisible(visible)

    def set_ghost_opacity(self, value: float) -> None:
        """Re-dim every spanner ghost to the document's floor opacity.
        The clipped full-opacity reveal copies are untouched — at floor
        0 a spanner still grows out of an invisible ghost. Applied
        through each item, which composes the floor with its selection
        state (M2.8)."""
        self._ghost_opacity = value
        for item in self.items.values():
            item.set_ghost_opacity(value)

    def set_element_hidden(self, element_id: ElementId,
                           hidden: bool) -> None:
        """Show/hide one element: a tempo overlay hiding the engraved
        mark (Phase 9.2), or the user deleting an object.

        Plain item visibility on the group parent, which is why it
        composes with everything else safely — Qt does not paint the
        children of an invisible parent, so the animation's opacity, the
        selection tint and a spanner's reveal clip all keep writing to an
        item that simply does not draw. Unknown id = no-op (override
        staleness accepted)."""
        item = self.items.get(element_id)
        if item is not None:
            item.setVisible(not hidden)

    def set_element_offset(self, element_id: ElementId,
                           dx: float, dy: float) -> None:
        """Move one element by its layout-override delta (M3.2). Page
        units == scene units, so the delta needs no conversion — the
        reason `render/scene.py` has always built one scene per page
        rather than one scene with page offsets. Unknown id = no-op
        (override staleness accepted)."""
        item = self.items.get(element_id)
        if item is not None:
            item.set_offset(dx, dy)

    def set_part_color(self, part: PartId, color: QColor | None) -> None:
        """Tint a part's playing ink (None restores black). Scope is
        TINTED_KINDS (core/animation/style.py, ruling D 2026-07-12):
        clefs, signatures, texts, rests, and dynamics stay black."""
        for item in self.items.values():
            identity = item.identity
            if (identity is not None and identity.part == part
                    and takes_part_color(identity)):
                item.set_color(color)

    # -- construction helpers ------------------------------------------------

    def _qpath(self, d: str) -> QPainterPath:
        """Glyph defs repeat heavily (1374 unique of ~2400 uses on the
        fixture); cache by path data, transform stays per-item."""
        path = self._path_cache.get(d)
        if path is None:
            path = self._path_cache[d] = to_qpainter_path(d)
        return path

    def _add_path(self, parent: ElementItem, prim: PathPrimitive,
                  reveal: bool = False, ghost: bool = False) -> None:
        cls = RevealPathItem if reveal else QGraphicsPathItem
        child = cls(self._qpath(prim.d))
        child.setTransform(to_qtransform(prim.transform))

        fill_tracks = fill_tracks_color(prim.fill)
        if prim.fill is None:
            child.setBrush(QBrush(DEFAULT_COLOR))
        elif prim.fill == "none":
            child.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        else:
            child.setBrush(QBrush(QColor(prim.fill)))

        stroke_tracks = prim.stroke == "currentColor"
        width = prim.stroke_width if prim.stroke_width is not None else 1.0
        if prim.stroke is None or prim.stroke == "none":
            child.setPen(QPen(Qt.PenStyle.NoPen))
            stroke_tracks = False
        elif stroke_tracks:
            child.setPen(svg_pen(DEFAULT_COLOR, width))
        else:
            child.setPen(svg_pen(QColor(prim.stroke), width))

        parent.add_path_child(child, fill_tracks, stroke_tracks, ghost=ghost)
