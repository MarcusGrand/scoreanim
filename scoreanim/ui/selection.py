"""SelectionController: click on the stage -> a selected element.

The Qt half of M2. It collects candidates from the scene, hands them to
the pure policy in core/selection, and writes the winner onto AppState;
it owns the highlight overlay (M2.4) because the overlay's lifetime is
exactly the selection's. It never touches the document — selection is
transient UI state.

Bound to one ScoreScenes at a time via bind_scenes(), the
DocumentSync.bind_scenes pattern: MainWindow._install calls it on every
load and re-engrave, which is also the clearing hook, since a
re-engrave destroys every ElementItem the selection could point at.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene

from scoreanim.core.selection import HitCandidate, pick
from scoreanim.render.items import ElementItem
from scoreanim.render.scene import ScoreScenes
from scoreanim.ui.app_state import AppState

# Click tolerance in PAGE units (scene == page coords). Thin ink is
# unclickable at a bare point — the M2.0 census returned nothing at all
# for slurs and hairpins at tol=0 — and 6 units is ~3 view px at fit
# zoom, which made every probed kind hit (spikes/NOTES.md, M2.0).
CLICK_TOLERANCE = 6.0

_HIGHLIGHT = QColor("#2b8cff")
_HIGHLIGHT_PAD = 4.0                 # page units of air around the ink
_HIGHLIGHT_Z = 1_000.0               # above all engraved ink


class SelectionController(QObject):
    def __init__(self, app_state: AppState,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._scenes: ScoreScenes | None = None
        self._overlay: QGraphicsRectItem | None = None
        self._state.selection_changed.connect(self._refresh_overlay)

    # -- lifecycle ---------------------------------------------------------

    def bind_scenes(self, scenes: ScoreScenes | None) -> None:
        """Adopt one load's scenes. Clears the selection: a re-engrave
        rebuilds every ElementItem, so the held identity would point at
        objects that no longer exist (and the overlay lived in a scene
        that is being dropped)."""
        self._drop_overlay()
        self._scenes = scenes
        self._state.set_selection(None)

    # -- hit-testing -------------------------------------------------------

    def candidates_at(self, scene_pos: QPointF,
                      scene: QGraphicsScene | None = None
                      ) -> list[HitCandidate]:
        """Every identity-bearing element under the point, as policy
        input. Walks each hit item up to its ElementItem parent (the
        parents are hit-transparent since M2.3, so hits are real ink),
        dedupes by element id, and records whether the click was inside
        the element's own ink or merely within the tolerance rect — the
        distinction the policy needs to keep a zero-area stem from
        stealing its notehead's click."""
        if scene is None:
            scene = self._scene_of(scene_pos)
        if scene is None:
            return []
        area = QRectF(scene_pos.x() - CLICK_TOLERANCE,
                      scene_pos.y() - CLICK_TOLERANCE,
                      2 * CLICK_TOLERANCE, 2 * CLICK_TOLERANCE)
        out: list[HitCandidate] = []
        seen: set = set()
        for hit in scene.items(area):
            item = _element_parent(hit)
            if item is None or item.identity is None:
                continue                 # stage texts carry no identity
            eid = item.identity.element_id
            if eid in seen:
                continue
            seen.add(eid)
            bbox = item.bbox
            out.append(HitCandidate(
                eid, item.identity.kind,
                bbox.width() * bbox.height() if bbox is not None else 0.0,
                _contains_ink(item, scene_pos)))
        return out

    def select_at(self, scene_pos: QPointF) -> None:
        """The click handler: pick a winner, or clear when nothing is
        under the pointer."""
        winner = pick(self.candidates_at(scene_pos))
        if winner is None or self._scenes is None:
            self._state.set_selection(None)
            return
        item = self._scenes.items.get(winner)
        self._state.set_selection(item.identity if item is not None else None)

    def clear(self) -> None:
        self._state.set_selection(None)

    # -- highlight overlay (M2.4) ------------------------------------------

    @property
    def overlay(self) -> QGraphicsRectItem | None:
        return self._overlay

    def _refresh_overlay(self) -> None:
        """An overlay ITEM, never a repaint of the element — so the
        highlight cannot fight animation opacity, part tinting, or a
        spanner's reveal clip. It lives in the element's own page scene,
        which is why a selection survives a page flip: the scenes are all
        retained and the overlay is simply on another one.

        Export builds its own private ScoreScenes from AnimationInputs,
        so it structurally cannot see this (the stage_view mask
        precedent); tests/test_selection.py pins it anyway."""
        self._drop_overlay()
        identity = self._state.selected
        if identity is None or self._scenes is None:
            return
        item = self._scenes.items.get(identity.element_id)
        if item is None:
            return
        scene = item.scene()
        if scene is None:
            return
        # childrenBoundingRect, not the authored bbox: the box has to
        # contain the ink you can SEE, and the authored rect underruns
        # curved spanners and multi-row text by up to 3.7x in area
        # (M2.0 finding B). Item coords == scene coords (the parent
        # carries no transform of its own; a transient pop scale pivots
        # on the anchor and deliberately does not move the highlight).
        rect = item.childrenBoundingRect()
        if rect.isEmpty() and item.bbox is not None:
            rect = QRectF(item.bbox)
        overlay = QGraphicsRectItem(
            rect.adjusted(-_HIGHLIGHT_PAD, -_HIGHLIGHT_PAD,
                          _HIGHLIGHT_PAD, _HIGHLIGHT_PAD))
        pen = QPen(_HIGHLIGHT)
        pen.setCosmetic(True)            # constant width at any zoom
        pen.setWidthF(2.0)
        overlay.setPen(pen)
        overlay.setBrush(Qt.BrushStyle.NoBrush)
        overlay.setZValue(_HIGHLIGHT_Z)
        scene.addItem(overlay)
        self._overlay = overlay

    def _drop_overlay(self) -> None:
        if self._overlay is None:
            return
        scene = self._overlay.scene()
        if scene is not None:
            scene.removeItem(self._overlay)
        self._overlay = None

    # -- internals ---------------------------------------------------------

    def _scene_of(self, scene_pos: QPointF) -> QGraphicsScene | None:
        """Fallback for callers that do not name a scene (tests): the
        window always clicks in the scene the view is showing."""
        if self._scenes is None or not self._scenes.scenes:
            return None
        for scene in self._scenes.scenes:
            if scene.sceneRect().contains(scene_pos):
                return scene
        return self._scenes.scenes[0]


def _element_parent(item) -> ElementItem | None:
    node = item
    while node is not None and not isinstance(node, ElementItem):
        node = node.parentItem()
    return node


def _contains_ink(item: ElementItem, scene_pos: QPointF) -> bool:
    """Is the point inside this element's actual ink (as opposed to
    merely within the tolerance rect around it)?"""
    for child in item.childItems():
        if not child.isVisible() or not hasattr(child, "shape"):
            continue
        if child.shape().contains(child.mapFromScene(scene_pos)):
            return True
    return False
