"""The Delete action: hide the selected object, and say so honestly.

The `ui/break_action.py` template — this class owns one QAction and its
enable/status-tip sync, and `core/editing/deletion.py` owns every
decision about what may be deleted and why. The D1 rider applies: when
the action is disabled, its status tip names the reason.

**Delete here means HIDE.** Nothing is removed from the score and
nothing about the music changes; the object stops being drawn and stops
being clickable, and the Layout zone lists it with a way back. The
wording on every surface says so, because "Delete" on its own would
promise something this feature deliberately does not do.

Two things it does that the break actions do not:

**It fans the id out over its `:seg` family.** A slur or hairpin broken
across systems is several elements and one object, so hiding one piece
is never what anybody meant — the same fan-out per-element colour uses,
against the loaded registry so it can never name an id the engraving
does not have.

**Its shortcut is scoped to the stage view, not the window.** Every
other shortcut in the app is registered window-level so it fires
regardless of focus. Delete cannot be: `ui/tempo_lane.py` already
handles Delete/Backspace for tempo points, and Qt matches shortcuts
before the key reaches the focused widget — a window-level Delete would
silently eat point deletion, and text fields with it. So the action is
added to the stage view with `WidgetWithChildrenShortcut`, which is
where `Esc` and the arrow keys already live for the same reason. The
Edit menu still shows the key.

Deleting clears the selection. Hidden ink is neither visible nor
hit-testable, so a surviving selection would point at something nobody
can see or click again — the inspector would offer colour and nudge
controls for absent ink. Selection is transient state (rule 13), so
undo brings the object back but not its selection; one click re-takes
it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

from scoreanim.core.editing.deletion import ENABLED_TIP, resolve
from scoreanim.core.editing.segments import family_of
from scoreanim.core.project import SetElementsHidden

if TYPE_CHECKING:
    from scoreanim.render.scene import ScoreScenes
    from scoreanim.ui.app_state import AppState

LABEL = "Delete"
# Both keys, because they are one key to most people: the Mac laptop
# key labelled "delete" sends Backspace, and a full keyboard's "Del"
# sends Delete. The first is what the menu displays.
SHORTCUTS = (Qt.Key.Key_Backspace, Qt.Key.Key_Delete)


class DeleteActionController:
    """Owns the Delete QAction, its sync, and its one command."""

    def __init__(self, app_state: AppState, parent) -> None:
        self._app_state = app_state
        self._scenes: ScoreScenes | None = None
        self.action = QAction(LABEL, parent)
        self.action.setShortcuts([QKeySequence(key) for key in SHORTCUTS])
        # stage-scoped on purpose — see the module docstring
        self.action.setShortcutContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.action.setEnabled(False)
        self.action.triggered.connect(self.trigger)
        app_state.selection_changed.connect(self.sync)

    def bind_scenes(self, scenes: ScoreScenes | None) -> None:
        """Adopt one load's scenes — the registry the `:seg` fan-out is
        intersected with. The `DocumentSync.bind_scenes` pattern."""
        self._scenes = scenes
        self.sync()

    # -- state --------------------------------------------------------------

    def current(self):
        return resolve(self._app_state.selection, self._hidden_ids())

    def sync(self) -> None:
        """Re-derive enabled state and status tip. Called on every
        selection change and on every document change — deleting an
        object is itself a document change that must disable the
        action."""
        resolved = self.current()
        self.action.setEnabled(resolved.enabled)
        self.action.setStatusTip(ENABLED_TIP if resolved.enabled
                                 else (resolved.reason or ""))

    def _hidden_ids(self) -> frozenset:
        return frozenset(eid for eid, override
                         in self._app_state.doc.layout_overrides.items()
                         if override.hidden)

    # -- the gesture --------------------------------------------------------

    def family(self, element_id) -> tuple:
        """Every id this delete should reach: the `:seg` family,
        intersected with the loaded score."""
        known = (self._scenes.items.keys() if self._scenes is not None
                 else (element_id,))
        return family_of(element_id, known)

    def trigger(self) -> None:
        resolved = self.current()
        if not resolved.enabled:
            return
        if self._app_state.execute(
                SetElementsHidden(self.family(resolved.element_id), True)):
            self._app_state.set_selection(None)
