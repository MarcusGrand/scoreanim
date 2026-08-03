"""The Flip Stem action: `F` points the selected note's stem the other way.

The `ui/delete_action.py` template — this class owns one QAction and its
enable/status-tip sync, and `core/editing/stem_flip.py` owns every
decision about what may be flipped and why.

**Its shortcut is scoped to the stage view, not the window.** `F` is a
bare letter, and Qt matches shortcuts BEFORE the key reaches the focused
widget: registered window-level, it would eat the "f" out of every text
field in the app — the title, a part label, a tempo box. So the action
is added to the stage view with `WidgetWithChildrenShortcut`, which is
where Delete, `Esc` and the arrow keys already live for the same reason.
The Edit menu still shows the key.

**Flipping re-engraves.** Unlike a nudge or a delete, a stem direction
is drawn by Verovio, so the flip is a prep-seam input and the whole
score is re-engraved — ~0.25 s on testscore, ~1.3 s on bigband1, on the
GUI thread. That is why it goes through `execute()` and never
`preview()`, and why one press is one undo entry rather than a gesture.

The selection SURVIVES: `bind_scenes` re-resolves the held identity
against the fresh item table, and a flip changes no part of an id. So
you can press `F` twice and watch the same note go back.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

from scoreanim.core.editing.stem_flip import ENABLED_TIP, resolve
from scoreanim.core.project import SetStemDirection

if TYPE_CHECKING:
    from scoreanim.core.engraving.types import Layout
    from scoreanim.ui.app_state import AppState

LABEL = "Flip Stem"
SHORTCUT = Qt.Key.Key_F


class StemFlipActionController:
    """Owns the Flip Stem QAction, its sync, and its one command."""

    def __init__(self, app_state: AppState, parent) -> None:
        self._app_state = app_state
        self._layout: Layout | None = None
        self.action = QAction(LABEL, parent)
        self.action.setShortcut(QKeySequence(SHORTCUT))
        # stage-scoped on purpose — see the module docstring
        self.action.setShortcutContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.action.setEnabled(False)
        self.action.triggered.connect(self.trigger)
        app_state.selection_changed.connect(self.sync)

    def bind_layout(self, layout: Layout | None) -> None:
        """Adopt one load's layout — the drawn geometry the current stem
        direction is read from. The `DocumentSync.bind_scenes` pattern."""
        self._layout = layout
        self.sync()

    # -- state --------------------------------------------------------------

    def current(self):
        return resolve(self._app_state.selection, self._layout)

    def sync(self) -> None:
        """Re-derive enabled state and status tip. Called on every
        selection change and on every document change — a flip
        re-engraves, so the direction the tip describes moves under it."""
        resolved = self.current()
        self.action.setEnabled(resolved.enabled)
        self.action.setStatusTip(ENABLED_TIP if resolved.enabled
                                 else (resolved.reason or ""))

    # -- the gesture --------------------------------------------------------

    def trigger(self) -> None:
        resolved = self.current()
        if not resolved.enabled:
            return
        self._app_state.execute(
            SetStemDirection(resolved.element_id, resolved.direction))
