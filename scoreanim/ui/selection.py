"""SelectionController: click on the stage -> a selected element.

The Qt half of M2. It collects candidates from the scene, hands them to
the pure policy in core/selection, and writes the winner onto AppState;
it owns the highlight, because the highlight's lifetime is exactly the
selection's. It never touches the document — selection is transient UI
state.

The highlight is a TINT on the element's own ink (M2.8, superseding
M2.4's bbox outline): the controller marks one ElementItem selected and
unmarks the last, and the item composes that with the document's color
and the evaluator's opacity (see ElementItem's docstring for the rule).
So the controller holds an item, not a scene item of its own, and there
is nothing to add to or remove from a scene.

Bound to one ScoreScenes at a time via bind_scenes(), the
DocumentSync.bind_scenes pattern: MainWindow._install calls it on every
load and re-engrave, which is also the clearing hook, since a
re-engrave destroys every ElementItem the selection could point at.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QRectF
from PySide6.QtWidgets import QGraphicsScene

from scoreanim.core.selection import HitCandidate, pick
from scoreanim.render.items import ElementItem
from scoreanim.render.scene import ScoreScenes
from scoreanim.ui.app_state import AppState

# Click tolerance in PAGE units (scene == page coords). Thin ink is
# unclickable at a bare point — the M2.0 census returned nothing at all
# for slurs and hairpins at tol=0 — and 6 units is ~3 view px at fit
# zoom, which made every probed kind hit (spikes/NOTES.md, M2.0).
CLICK_TOLERANCE = 6.0


class SelectionController(QObject):
    def __init__(self, app_state: AppState,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._scenes: ScoreScenes | None = None
        self._highlighted: ElementItem | None = None
        self._state.selection_changed.connect(self._refresh_highlight)

    # -- lifecycle ---------------------------------------------------------

    def bind_scenes(self, scenes: ScoreScenes | None) -> None:
        """Adopt one load's scenes. Clears the selection: a re-engrave
        rebuilds every ElementItem, so the held identity would point at
        objects that no longer exist (and the item carrying the tint is
        being dropped with them)."""
        self._unmark()
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

    def select_at(self, scene_pos: QPointF,
                  scene: QGraphicsScene | None = None) -> None:
        """The click handler: pick a winner, or clear when nothing is
        under the pointer.

        `scene` is the page the click happened in and should always be
        supplied — every page scene has the SAME sceneRect, so a
        position alone cannot identify the page."""
        winner = pick(self.candidates_at(scene_pos, scene))
        if winner is None or self._scenes is None:
            self._state.set_selection(None)
            return
        item = self._scenes.items.get(winner)
        self._state.set_selection(item.identity if item is not None else None)

    def clear(self) -> None:
        self._state.set_selection(None)

    # -- highlight (M2.8: a tint on the element's own ink) -----------------

    @property
    def highlighted(self) -> ElementItem | None:
        """The item currently carrying the selection tint, if any."""
        return self._highlighted

    def _refresh_highlight(self) -> None:
        """Move the tint to the newly selected element.

        The tint is a paint state ON the element, composed by the item
        with the document's authored color and the evaluator's opacity —
        so it follows a pop's scale, rides a spanner's ghost rather than
        fighting its reveal clip, and cannot be mistaken for score ink
        (there is no extra object to mistake).

        Export builds its own private ScoreScenes from AnimationInputs,
        whose items are constructed unselected, and never consults
        AppState — so a live selection structurally cannot reach a frame
        (the stage_view mask precedent); tests/test_export.py pins it
        from both ends."""
        self._unmark()
        identity = self._state.selected
        if identity is None or self._scenes is None:
            return
        item = self._scenes.items.get(identity.element_id)
        if item is None:
            return
        item.set_selected(True)
        self._highlighted = item

    def _unmark(self) -> None:
        if self._highlighted is None:
            return
        self._highlighted.set_selected(False)
        self._highlighted = None

    # -- internals ---------------------------------------------------------

    def _scene_of(self, scene_pos: QPointF) -> QGraphicsScene | None:
        """Fallback when no scene is named: the FIRST page.

        Deliberately not a search — page scenes all share one sceneRect,
        so containment cannot distinguish them and a guess would return
        page 1's ink for a click on page 3. Callers that can be on any
        page must pass the scene (StageView.clicked carries it)."""
        if self._scenes is None or not self._scenes.scenes:
            return None
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
