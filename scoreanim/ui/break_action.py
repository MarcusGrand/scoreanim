"""The Score menu's break actions (M5.4, M5.7).

D1: a menu action rather than a stage context menu. There is no
`contextMenuEvent` anywhere on the stage today, so a right-click menu is
new machinery; the Score menu is already the home of every layout choice
(Score Setup, Staff Groups, Hide Empty Staves), and break authoring
wants to be keyboard-reachable when you are working through a score. A
context menu can be added later over this same command without changing
anything below the UI.

Everything this class does with the selection is decided by
`core/editing/breaks.py` — it owns the QActions, not the policy. The
D1 rider lives here: each action carries a shortcut, and when it is
disabled its status tip names WHY (no selection, not a barline, a
system-start barline carrying no measure, the last measure).

M5.7 adds the second action, "Move to Previous System" — the same
selection, the same policy module, the same command, and a composed
entry set instead of a single toggle. It lives in this class rather than
its own because everything around the QAction (the per-load measure→
system map, the enable/label sync, the one trigger) is shared; only the
policy call differs.

M6.5 adds the third, the page toggle, on exactly that spine: one more
constructor block, one more policy call, one more command. The class was
built for a variadic set of break actions (`actions`, and
`PartsMenu.set_break_actions(*actions)`), so nothing around it reshapes —
which is also what lets M6.6's layout zone host the SAME QAction objects
rather than parallel ones that could drift out of step.

The Score menu is cleared and rebuilt per load (`ui/parts_menu.py`), so
the actions are handed to that builder to re-insert rather than added
once in the static chrome.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

from PySide6.QtGui import QAction, QKeySequence

from scoreanim.core.editing.breaks import resolve, resolve_move_up
from scoreanim.core.editing.page_breaks import resolve as resolve_page
from scoreanim.core.project import (PageBreak, SetPageBreak, SetSystemBreak,
                                    SystemBreak)
from scoreanim.ui.theme import icons

if TYPE_CHECKING:
    from scoreanim.ui.app_state import AppState

SHORTCUT = "Ctrl+Shift+B"
MOVE_UP_SHORTCUT = "Ctrl+Shift+Up"
PAGE_SHORTCUT = "Ctrl+Shift+P"

# The action renames itself to what it would actually do, so the menu is
# honest before you open it (the SetElementStyle "clear" idiom).
_LABEL = {
    SystemBreak.FORCE: "Force System Break Here",
    SystemBreak.SUPPRESS: "Remove System Break Here",
    None: "Clear System Break Override Here",
}
_DEFAULT_LABEL = "Toggle System Break Here"
_MOVE_UP_LABEL = "Move to Previous System"
_PAGE_LABEL = {
    PageBreak.FORCE: "Force Page Break Here",
    PageBreak.SUPPRESS: "Remove Page Break Here",
    None: "Clear Page Break Override Here",
}
_PAGE_DEFAULT_LABEL = "Toggle Page Break Here"


class BreakActionController:
    """Owns the three break QActions, their enable/label sync, and their
    triggers."""

    def __init__(self, app_state: AppState, parent) -> None:
        self._app_state = app_state
        self._system_of_measure: Mapping[int, int] = {}
        self._page_of_measure: Mapping[int, int] = {}
        # icon-only in the layout zone, labelled in the Score menu; the
        # label the action renames itself to becomes the button's tooltip
        self.action = QAction(icons.icon("corner-down-left"),
                              _DEFAULT_LABEL, parent)
        self.action.setShortcut(QKeySequence(SHORTCUT))
        self.action.setEnabled(False)
        self.action.triggered.connect(self.trigger)
        self.move_up_action = QAction(icons.icon("corner-left-up"),
                                      _MOVE_UP_LABEL, parent)
        self.move_up_action.setShortcut(QKeySequence(MOVE_UP_SHORTCUT))
        self.move_up_action.setEnabled(False)
        self.move_up_action.triggered.connect(self.trigger_move_up)
        self.page_action = QAction(icons.icon("separator-horizontal"),
                                   _PAGE_DEFAULT_LABEL, parent)
        self.page_action.setShortcut(QKeySequence(PAGE_SHORTCUT))
        self.page_action.setEnabled(False)
        self.page_action.triggered.connect(self.trigger_page)
        app_state.selection_changed.connect(self.sync)

    @property
    def actions(self) -> tuple[QAction, ...]:
        """In menu order — the two system gestures, then the page one."""
        return (self.action, self.move_up_action, self.page_action)

    def bind(self, system_of_measure: Mapping[int, int],
             page_of_measure: Mapping[int, int] | None = None) -> None:
        """Per load: the engraved maps the policies read. Both are
        DERIVED from the load, never document state (rule 5) — the page
        one composes the system bands with the measure→system map
        (§1.2), so it costs no adapter change."""
        self._system_of_measure = dict(system_of_measure)
        self._page_of_measure = dict(page_of_measure or {})
        self.sync()

    def current(self):
        doc = self._app_state.doc
        return resolve(self._app_state.selection, doc.system_break_overrides,
                       self._system_of_measure, doc.page_break_overrides)

    def current_move_up(self):
        doc = self._app_state.doc
        return resolve_move_up(self._app_state.selection,
                               doc.system_break_overrides,
                               self._system_of_measure,
                               doc.page_break_overrides)

    def current_page(self):
        doc = self._app_state.doc
        return resolve_page(self._app_state.selection,
                            doc.page_break_overrides,
                            doc.system_break_overrides,
                            self._page_of_measure)

    def sync(self) -> None:
        """Re-derive enabled state, label and status tip for all three.
        Called on every selection change and on every document change
        (the overrides move a toggle's label between force / remove /
        clear)."""
        self._sync_toggle(self.action, self.current(), _LABEL,
                          _DEFAULT_LABEL)
        self._sync_toggle(self.page_action, self.current_page(), _PAGE_LABEL,
                          _PAGE_DEFAULT_LABEL)
        # the move-up label never changes — the gesture is the same
        # whichever way its two halves happen to be written
        move_up = self.current_move_up()
        self.move_up_action.setEnabled(move_up.enabled)
        self.move_up_action.setStatusTip(
            "" if move_up.enabled else (move_up.reason or ""))

    @staticmethod
    def _sync_toggle(action: QAction, resolved, labels, default) -> None:
        action.setEnabled(resolved.enabled)
        action.setText(labels[resolved.mode] if resolved.enabled else default)
        action.setStatusTip("" if resolved.enabled
                            else (resolved.reason or ""))

    def trigger(self) -> None:
        self._execute(self.current())

    def trigger_move_up(self) -> None:
        self._execute(self.current_move_up())

    def trigger_page(self) -> None:
        resolved = self.current_page()
        if not resolved.enabled:
            return
        self._app_state.execute(SetPageBreak(
            resolved.ordinal, resolved.mode, resolved.also,
            resolved.also_system))

    def _execute(self, action) -> None:
        """One command for either system gesture — `also` carries the
        composed entries and `also_page` the cross-map clearing, so each
        is a single undo step (rule 8)."""
        if not action.enabled:
            return
        self._app_state.execute(SetSystemBreak(
            action.ordinal, action.mode, action.also, action.also_page))
