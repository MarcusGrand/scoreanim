"""Drag-to-nudge (M3.2): move a selected element, commit once.

The Qt half. Policy — which kinds may move, and what an arrow key is
worth — is `core/editing/nudge.py`; this owns the gesture and the one
command it ends in.

**One gesture, one undo entry (rule 8).** A drag previews by moving the
scene item directly and executes `SetLayoutOverride` exactly once, on
release. Nothing touches the document mid-drag: `AppState.preview` is
deliberately not used, because the preview here is a pure render
concern (an item's position) with no document state to show. The delta
the command carries is ABSOLUTE — the element's total offset from its
engraved position — which is what makes the single commit describe the
whole gesture, and what makes undo a plain replay of the previous value
rather than an unwinding.

**Deltas are page units, and the document stores only them** (rule 5).
Scene coordinates ARE page coordinates, so a drag's scene delta needs no
conversion; the engraved position it rides on top of re-derives on every
load and is never stored.

The drag is bound to the SELECTION, not to whatever is under the
pointer: you select first, then drag. That keeps this gesture from
competing with the click that made the selection, and it means the
element being moved is always the one the Selection panel is describing.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPointF
from PySide6.QtWidgets import QGraphicsScene

from scoreanim.core.editing import is_nudgeable, nudged_delta
from scoreanim.core.project import SetLayoutOverride
from scoreanim.core.score.identity import ElementId
from scoreanim.render.scene import ScoreScenes
from scoreanim.ui.app_state import AppState


class NudgeController(QObject):
    """Press → preview → one command. Bound per load, like its siblings."""

    def __init__(self, app_state: AppState,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._scenes: ScoreScenes | None = None
        self._dragging: ElementId | None = None
        self._base = (0.0, 0.0)          # the override the drag started from

    def bind_scenes(self, scenes: ScoreScenes | None) -> None:
        self._scenes = scenes
        self._dragging = None

    # -- what may be dragged -----------------------------------------------

    def target(self) -> ElementId | None:
        """The selected element, if it is one that may be nudged."""
        identity = self._state.selected
        if identity is None or not is_nudgeable(identity.kind):
            return None
        return identity.element_id

    def probe(self, scene_pos: QPointF,
              scene: QGraphicsScene | None = None) -> bool:
        """Should a press here start a nudge?

        Only when the press lands on the SELECTED element's own ink.
        Anywhere else — including on a different nudgeable element — the
        drag does nothing, so the stage never feels like it grabs things
        the user did not ask it to grab."""
        eid = self.target()
        if eid is None or self._scenes is None:
            return False
        item = self._scenes.items.get(eid)
        if item is None or (scene is not None and item.scene() is not scene):
            return False
        return item.sceneBoundingRect().contains(scene_pos)

    # -- the drag ----------------------------------------------------------

    def start(self, scene_pos: QPointF,
              scene: QGraphicsScene | None = None) -> None:
        eid = self.target()
        if eid is None:
            return
        override = self._state.doc.layout_overrides.get(eid)
        self._base = ((override.dx, override.dy) if override is not None
                      else (0.0, 0.0))
        self._dragging = eid

    def move(self, delta: QPointF) -> None:
        """Live preview: move the item, touch nothing else."""
        if self._dragging is None or self._scenes is None:
            return
        self._scenes.set_element_offset(self._dragging,
                                        self._base[0] + delta.x(),
                                        self._base[1] + delta.y())

    def finish(self, delta: QPointF) -> None:
        """One command for the whole gesture."""
        eid, self._dragging = self._dragging, None
        if eid is None:
            return
        dx, dy = self._base[0] + delta.x(), self._base[1] + delta.y()
        if (dx, dy) == self._base:
            return                    # a press with no movement: not an edit
        # the document change syncs the scene back onto the same value,
        # so the preview and the committed state cannot drift
        self._state.execute(SetLayoutOverride(eid, dx, dy))

    # -- keyboard ----------------------------------------------------------

    def nudge_by(self, step_dx: float, step_dy: float) -> None:
        """One arrow press = one undo entry, accumulating on whatever
        the element's delta already is."""
        eid = self.target()
        if eid is None:
            return
        override = self._state.doc.layout_overrides.get(eid)
        dx, dy = ((override.dx, override.dy) if override is not None
                  else (0.0, 0.0))
        self._state.execute(SetLayoutOverride(
            eid, *nudged_delta(dx, dy, step_dx, step_dy)))

    def clear(self) -> None:
        """Put the selected element back where the engraver put it."""
        eid = self.target()
        if eid is not None:
            self._state.execute(SetLayoutOverride(eid, 0.0, 0.0))
