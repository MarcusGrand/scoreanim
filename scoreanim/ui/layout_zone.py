"""Layout zone: the left dock where break authoring lives (M6.6).

BACKLOG 17, deferred at M5.7 "until more than one action needs a home"
and built here because M6 makes it three. Break authoring is the kind of
work you do in a pass down a score, and a menu round trip per edit is the
wrong shape for that.

Deliberately an **M1-style re-home of existing commands, not new
semantics** (D9). Every button here has a `defaultAction`, and that
action is the SAME `QAction` object the Score menu holds — so enabled
state, label and status tip cannot diverge between the two surfaces, and
pressing either one runs the identical command. It is the `follow_action`
precedent from M1, where the Playback menu and the inspector share one
action. The Score menu keeps everything it had.

The dock itself is the `Inspector` template (M1.4): an `objectName` for
`saveState` identity, no titlebar chrome, one allowed area, and a
`toggleViewAction()` the View menu picks up. `window_state.py` persists
the whole `QMainWindow` state through one `saveState`/`restoreState`
pair, so a third dock needs no new persistence code — verified rather
than assumed (D10), including that a stored layout predating this dock
still places it sanely.

Scrolled, for the reason the inspector is: a dock must never dictate the
window's minimum height, and this one accrues rows as the two readouts
fill up — break overrides, and the objects the user has deleted.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QDockWidget, QLabel, QScrollArea, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from scoreanim.core.project import ProjectDoc
from scoreanim.ui.app_state import AppState
from scoreanim.ui.panels import BreakOverridesList, DeletedElementsList


class LayoutZone(QDockWidget):
    """Left dock: the break actions, and what they have written so far."""

    def __init__(self, app_state: AppState, actions: tuple[QAction, ...],
                 parent: QWidget | None = None) -> None:
        super().__init__("Layout", parent)
        self.setObjectName("LayoutZone")     # saveState identity (M1.8)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        self.toggleViewAction().setText("Layout Zone")

        body = QWidget(self)
        column = QVBoxLayout(body)
        column.setContentsMargins(8, 8, 8, 8)
        column.setSpacing(4)
        heading = QLabel("Breaks")
        heading.setObjectName("ZoneHeading")
        column.addWidget(heading)

        self.buttons: tuple[QToolButton, ...] = tuple(
            self._button(action, body) for action in actions)
        for button in self.buttons:
            column.addWidget(button)

        column.addSpacing(8)
        overrides_heading = QLabel("Overrides")
        overrides_heading.setObjectName("ZoneHeading")
        column.addWidget(overrides_heading)
        # its own widget module rather than a limb on the dock (D9)
        self.overrides = BreakOverridesList(app_state, body)
        column.addWidget(self.overrides)

        column.addSpacing(8)
        deleted_heading = QLabel("Deleted")
        deleted_heading.setObjectName("ZoneHeading")
        column.addWidget(deleted_heading)
        # deleted ink is not clickable, so this list is the only way back
        # other than undo — it belongs where the work is, not in a dialog
        self.deleted = DeletedElementsList(app_state, body)
        column.addWidget(self.deleted)
        column.addStretch(1)

        scroller = QScrollArea(self)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QScrollArea.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setWidget(body)
        self.setWidget(scroller)

    @staticmethod
    def _button(action: QAction, parent: QWidget) -> QToolButton:
        """One button over one SHARED action.

        `setDefaultAction` is the whole mechanism: the button takes its
        text, enabled state, status tip and trigger from the action, and
        keeps taking them as `BreakActionController.sync()` re-derives
        them. Nothing here needs syncing of its own, which is exactly
        what "a second surface, not a second implementation" means.
        """
        button = QToolButton(parent)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Fixed)
        return button

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Only the readouts have document state to resync; the buttons
        follow their shared actions, which the break controller syncs."""
        self.overrides.sync_from_document(doc)
        self.deleted.sync_from_document(doc)
