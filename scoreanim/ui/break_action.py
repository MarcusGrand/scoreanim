"""The Score-menu "Toggle System Break" action (M5.4).

D1: a menu action rather than a stage context menu. There is no
`contextMenuEvent` anywhere on the stage today, so a right-click menu is
new machinery; the Score menu is already the home of every layout choice
(Score Setup, Staff Groups, Hide Empty Staves), and break authoring
wants to be keyboard-reachable when you are working through a score. A
context menu can be added later over this same command without changing
anything below the UI.

Everything this class does with the selection is decided by
`core/editing/breaks.py` — it owns the QAction, not the policy. The
D1 rider lives here: the action carries a shortcut, and when it is
disabled its status tip names WHY (no selection, not a barline, a
system-start barline carrying no measure, the last measure).

The Score menu is cleared and rebuilt per load (`ui/parts_menu.py`), so
the action is handed to that builder to re-insert rather than added once
in the static chrome.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

from PySide6.QtGui import QAction, QKeySequence

from scoreanim.core.editing.breaks import resolve
from scoreanim.core.project import SetSystemBreak, SystemBreak

if TYPE_CHECKING:
    from scoreanim.ui.app_state import AppState

SHORTCUT = "Ctrl+Shift+B"

# The action renames itself to what it would actually do, so the menu is
# honest before you open it (the SetElementStyle "clear" idiom).
_LABEL = {
    SystemBreak.FORCE: "Force System Break Here",
    SystemBreak.SUPPRESS: "Remove System Break Here",
    None: "Clear System Break Override Here",
}
_DEFAULT_LABEL = "Toggle System Break Here"


class BreakActionController:
    """Owns the QAction, its enable/label sync, and its one trigger."""

    def __init__(self, app_state: AppState, parent) -> None:
        self._app_state = app_state
        self._system_of_measure: Mapping[int, int] = {}
        self.action = QAction(_DEFAULT_LABEL, parent)
        self.action.setShortcut(QKeySequence(SHORTCUT))
        self.action.setEnabled(False)
        self.action.triggered.connect(self.trigger)
        app_state.selection_changed.connect(self.sync)

    def bind(self, system_of_measure: Mapping[int, int]) -> None:
        """Per load: the engraved measure→system map the policy reads."""
        self._system_of_measure = dict(system_of_measure)
        self.sync()

    def current(self):
        return resolve(self._app_state.selection,
                       self._app_state.doc.system_break_overrides,
                       self._system_of_measure)

    def sync(self) -> None:
        """Re-derive enabled state, label and status tip. Called on every
        selection change and on every document change (the overrides move
        the label between force / remove / clear)."""
        action = self.current()
        self.action.setEnabled(action.enabled)
        if action.enabled:
            self.action.setText(_LABEL[action.mode])
            self.action.setStatusTip("")
        else:
            self.action.setText(_DEFAULT_LABEL)
            self.action.setStatusTip(action.reason or "")

    def trigger(self) -> None:
        action = self.current()
        if not action.enabled:
            return
        self._app_state.execute(SetSystemBreak(action.ordinal, action.mode))
