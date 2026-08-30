"""Dynamic Score-menu content (M1.6): the static setup head plus one
submenu per part — color swatches (palette + Custom… + No Color).

The per-part effect radio group dropped out in M4 (brief F5): the
Effects panel covers the document default, and per-part effect
deviations — still honored and round-tripped (part rules are
untouched) — become authorable again with M3's Selection panel.

Rebuilt per load by the window (the menu itself lives in the M1.5
chrome). The check-state registries and their blockSignals resync live
here; the window's style diff enumerates parts via `part_ids()` and
drives `sync_checks(pid, rule)` per part, and `sync_from_document(doc)`
resyncs the Hide Empty Staves toggle on every document change.

Since M3.0 (BACKLOG 9b) this module also OPENS the three part-shaped
dialogs its own items launch — Score Setup, Staff Groups, Part Names.
They were window methods guarding on a window-held `_parts` tuple, but
the parts arrive here already (`rebuild` is called with them per load),
so the data and the dialogs that consume it now live together and the
window holds neither.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPixmap
from PySide6.QtWidgets import QColorDialog, QMenu, QWidget

from scoreanim.core.project import (SetHideEmptyStaves, SetHideFirstSystem,
                                    SetPartColor)
from scoreanim.core.score.identity import PartId
from scoreanim.ui import tips
from scoreanim.ui.part_names_dialog import PartNamesDialog
from scoreanim.ui.score_setup_dialog import ScoreSetupDialog
from scoreanim.ui.staff_groups_dialog import StaffGroupsDialog

if TYPE_CHECKING:
    from scoreanim.ui.app_state import AppState

# Part-color swatch palette (Custom… covers the rest).
PART_COLORS = ["#cc2222", "#1a7a2e", "#1c4fd6", "#b26b00",
               "#8422b8", "#0b7f7f", "#c22276"]


class PartsMenu:
    """Builder + check-state sync for the Score menu's dynamic content.

    Owns no document state: every trigger routes through
    `app_state.execute`, and check state is re-derived from the
    document's StyleRules by the sync methods (the blockSignals idiom).
    """

    def __init__(self, menu: QMenu, app_state: AppState,
                 parent: QWidget) -> None:
        self._menu = menu
        self._app_state = app_state
        self._parent = parent
        self._parts: tuple = ()          # PartInfos of the current build
        self._break_actions: tuple[QAction, ...] = ()
        self._hide_staves_action: QAction | None = None
        self._hide_first_action: QAction | None = None
        self._color_actions: dict[PartId, dict] = {}

    def set_break_actions(self, *actions: QAction) -> None:
        """The Score menu is cleared per load, so M5's break actions are
        handed here to be re-inserted rather than added once in the
        static chrome. This module owns WHERE they sit, never what they
        do — ui/break_action.py keeps that."""
        self._break_actions = actions

    # -- the part-shaped dialogs -----------------------------------------------

    def open_score_setup(self) -> None:
        """The one way in — a load never opens this by itself
        (2026-07-30)."""
        if not self._parts:
            return
        ScoreSetupDialog(self._app_state, self._parts,
                         parent=self._parent).exec()

    def open_staff_groups(self) -> None:
        if not self._parts:
            return
        StaffGroupsDialog(self._app_state, self._parts,
                          parent=self._parent).exec()

    def open_part_names(self) -> None:
        if not self._parts:
            return
        # a PROVIDER, not a snapshot: each rename re-engraves and calls
        # rebuild() with the effective names — the dialog's rebuild must
        # show them
        PartNamesDialog(self._app_state, parts_provider=lambda: self._parts,
                        parent=self._parent).exec()

    def part_ids(self) -> tuple[PartId, ...]:
        """The parts of the current build — the window's style diff
        iterates these (they double as the loaded-part registry)."""
        return tuple(self._color_actions)

    def rebuild(self, parts) -> None:
        """One submenu per part, after the static setup head. Called per
        load; the window resets its applied-style caches alongside
        (fresh scenes carry no tints)."""
        menu = self._menu
        menu.clear()
        self._color_actions = {}
        self._parts = tuple(parts)
        setup_action = QAction("Score Setup…", menu)
        setup_action.triggered.connect(self.open_score_setup)
        tips.describe_action(setup_action,
                             "Which parts are engraved, and in what order")
        menu.addAction(setup_action)
        groups_action = QAction("Staff Groups…", menu)
        groups_action.triggered.connect(self.open_staff_groups)
        tips.describe_action(groups_action,
                             "Braces and brackets, and which parts are "
                             "condensed onto one staff")
        menu.addAction(groups_action)
        names_action = QAction("Part Names…", menu)
        names_action.triggered.connect(self.open_part_names)
        tips.describe_action(names_action,
                             "Rename a part as it is printed on the page")
        menu.addAction(names_action)
        # an engraving input like the two above (Phase 10R): toggling
        # re-engraves via the _applied_hide_empty diff, one undo step
        self._hide_staves_action = QAction("Hide Empty Staves", menu)
        self._hide_staves_action.setCheckable(True)
        self._hide_staves_action.setChecked(
            self._app_state.doc.hide_empty_staves)
        self._hide_staves_action.toggled.connect(
            lambda checked: self._app_state.execute(
                SetHideEmptyStaves(checked)))
        tips.describe_action(
            self._hide_staves_action,
            "Leave a staff out of a system where that part has nothing "
            "to play")
        menu.addAction(self._hide_staves_action)
        # the first-system extension (2026-07-24): meaningful only while
        # hiding is on, so it enables with the parent toggle
        self._hide_first_action = QAction(
            "Hide Empty Staves on First System", menu)
        self._hide_first_action.setCheckable(True)
        self._hide_first_action.setChecked(
            self._app_state.doc.hide_first_system)
        self._hide_first_action.toggled.connect(
            lambda checked: self._app_state.execute(
                SetHideFirstSystem(checked)))
        tips.describe_action(
            self._hide_first_action,
            "Hide there too — most publishers show the full roster on "
            "the first system")
        tips.gate(self._hide_first_action,
                  self._app_state.doc.hide_empty_staves,
                  "Turn on Hide Empty Staves first")
        menu.addAction(self._hide_first_action)
        # a layout-intent edit, so it belongs with the layout choices —
        # and, like them, an engraving input that re-engraves via the
        # loader's applied-input diff (M5.4)
        if self._break_actions:
            menu.addSeparator()
            for action in self._break_actions:
                menu.addAction(action)
        menu.addSeparator()
        for info in parts:
            pid = PartId(info.part_id)
            submenu = menu.addMenu(info.name)

            color_group = QActionGroup(submenu)
            color_actions: dict = {}
            for c in PART_COLORS:
                action = QAction(c, submenu)
                action.setCheckable(True)
                tips.describe(action, f"Draw this part's ink in {c}")
                pm = QPixmap(12, 12)
                pm.fill(QColor(c))
                action.setIcon(QIcon(pm))
                action.triggered.connect(
                    lambda _=False, p=pid, col=c:
                    self._app_state.execute(SetPartColor(p, col)))
                color_group.addAction(action)
                submenu.addAction(action)
                color_actions[c] = action
            custom = QAction("Custom…", submenu)
            custom.setCheckable(True)
            tips.describe(custom, "Pick any colour for this part")
            custom.triggered.connect(
                lambda _=False, p=pid: self._pick_part_color(p))
            color_group.addAction(custom)
            submenu.addAction(custom)
            color_actions["custom"] = custom
            no_color = QAction("No Color", submenu)
            no_color.setCheckable(True)
            tips.describe(no_color,
                          "Drop the part colour — back to the page's own "
                          "ink")
            no_color.setChecked(True)
            no_color.triggered.connect(
                lambda _=False, p=pid:
                self._app_state.execute(SetPartColor(p, None)))
            color_group.addAction(no_color)
            submenu.addAction(no_color)
            color_actions[None] = no_color
            self._color_actions[pid] = color_actions

    def sync_checks(self, pid: PartId, rule) -> None:
        """Re-derive one part's checkmarks from its StyleRules entry.
        Effect state is no longer surfaced here (M4, F5) — a part
        rule's effect stays in the document untouched."""
        color = rule.color if rule is not None else None
        color_actions = self._color_actions.get(pid, {})
        for key, action in color_actions.items():
            action.blockSignals(True)
            if key == "custom":
                action.setChecked(color is not None
                                  and color not in color_actions)
            else:
                action.setChecked(color == key)
            action.blockSignals(False)

    def sync_from_document(self, doc) -> None:
        """Resync the hide toggles — execute, undo, and redo all arrive
        here via the window's document-changed pass."""
        if self._hide_staves_action is not None:
            self._hide_staves_action.blockSignals(True)
            self._hide_staves_action.setChecked(doc.hide_empty_staves)
            self._hide_staves_action.blockSignals(False)
        if self._hide_first_action is not None:
            self._hide_first_action.blockSignals(True)
            self._hide_first_action.setChecked(doc.hide_first_system)
            tips.gate(self._hide_first_action, doc.hide_empty_staves,
                      "Turn on Hide Empty Staves first")
            self._hide_first_action.blockSignals(False)

    def _pick_part_color(self, pid: PartId) -> None:
        rule = self._app_state.doc.style.parts.get(pid)
        initial = QColor(rule.color) if rule is not None and rule.color \
            else QColor(PART_COLORS[0])
        color = QColorDialog.getColor(initial, self._parent, "Part color")
        if color.isValid():
            self._app_state.execute(SetPartColor(pid, color.name()))
        else:
            # cancelled: clicking Custom… checked it, but no command ran
            # — restore this part's checks from the unchanged document
            self.sync_checks(pid, self._app_state.doc.style.parts.get(pid))
