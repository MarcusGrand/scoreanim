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

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsScene

from scoreanim.core.engraving.types import Layout, PathPrimitive
from scoreanim.core.project.stage_config import StageConfig
from scoreanim.core.score.identity import ElementId, ElementKind, PartId
from scoreanim.render.items import DEFAULT_COLOR, ElementItem, svg_pen
from scoreanim.render.qpath import to_qpainter_path, to_qtransform
from scoreanim.render.text import add_stage_text, add_text_rows

# Structural elements a part tint leaves alone (deliberate: coloring the
# staff itself reads as broken, not highlighted; easy to revisit).
_UNTINTED_KINDS = frozenset({ElementKind.STAFF_LINES, ElementKind.BARLINE})


class ScoreScenes:
    """All pages of one score as scenes + the element registry."""

    def __init__(self, layout: Layout, stage: StageConfig) -> None:
        self.items: dict[ElementId, ElementItem] = {}
        self._path_cache: dict[str, QPainterPath] = {}
        self.scenes: list[QGraphicsScene] = []
        for geo in layout.pages:
            scene = QGraphicsScene(0, 0, geo.width, geo.height)
            scene.addRect(0, 0, geo.width, geo.height,
                          QPen(Qt.PenStyle.NoPen),
                          QBrush(QColor(Qt.GlobalColor.white)))
            self.scenes.append(scene)

        for el in layout.elements:
            item = ElementItem(el.identity)
            for prim in el.glyph.paths:
                self._add_path(item, prim)
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

    def set_part_color(self, part: PartId, color: QColor | None) -> None:
        """Tint every element of a part (None restores black). Staff
        lines and barlines stay untinted."""
        for item in self.items.values():
            identity = item.identity
            if (identity is not None and identity.part == part
                    and identity.kind not in _UNTINTED_KINDS):
                item.set_color(color)

    # -- construction helpers ------------------------------------------------

    def _qpath(self, d: str) -> QPainterPath:
        """Glyph defs repeat heavily (1374 unique of ~2400 uses on the
        fixture); cache by path data, transform stays per-item."""
        path = self._path_cache.get(d)
        if path is None:
            path = self._path_cache[d] = to_qpainter_path(d)
        return path

    def _add_path(self, parent: ElementItem, prim: PathPrimitive) -> None:
        child = QGraphicsPathItem(self._qpath(prim.d))
        child.setTransform(to_qtransform(prim.transform))

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
