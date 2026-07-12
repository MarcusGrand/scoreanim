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

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import (QGraphicsPathItem, QGraphicsRectItem,
                               QGraphicsScene)

from scoreanim.core.animation.reveal import REVEALED_KINDS
from scoreanim.core.animation.style import StyleRules, takes_part_color
from scoreanim.core.engraving.types import Layout, PathPrimitive
from scoreanim.core.project.stage_config import StageConfig
from scoreanim.core.score.identity import ElementId, PartId
from scoreanim.render.items import (DEFAULT_COLOR, ElementItem,
                                    RevealPathItem, svg_pen)
from scoreanim.render.qpath import to_qpainter_path, to_qtransform
from scoreanim.render.text import add_stage_text, add_text_rows


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
        self._ghost_opacity = ghost_opacity
        # Spanner ghost children, tracked so the floor can change after
        # construction (Phase 7.2: the floor is document intent).
        self._ghost_items: list[QGraphicsPathItem] = []
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

        for el in layout.elements:
            item = ElementItem(
                el.identity,
                bbox=QRectF(el.bbox.x, el.bbox.y, el.bbox.w, el.bbox.h),
                anchor=QPointF(el.anchor.x, el.anchor.y),
                system=el.system)
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
            self.items[el.identity.element_id] = item

        for text in stage.texts:
            item = ElementItem(identity=None)
            add_stage_text(item, text)
            self.scenes[text.page - 1].addItem(item)
            self.items[ElementId(text.element_id)] = item

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
        0 a spanner still grows out of an invisible ghost."""
        self._ghost_opacity = value
        for child in self._ghost_items:
            child.setOpacity(value)

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
        if ghost:
            child.setOpacity(self._ghost_opacity)
            self._ghost_items.append(child)

        fill_tracks = prim.fill is None
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

        parent.add_path_child(child, fill_tracks, stroke_tracks)
