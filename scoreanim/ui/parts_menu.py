"""Dynamic Score-menu content (M1.6): the static setup head plus one
submenu per part — color swatches (palette + Custom… + No Color) and an
effect radio group enumerated from the preset registry, so adding a
preset needs no menu code.

Rebuilt per load by the window (the menu itself lives in the M1.5
chrome). The check-state registries and their blockSignals resync live
here; the window's style diff enumerates parts via `part_ids()` and
drives `sync_checks(pid, rule)` per part, and `sync_from_document(doc)`
resyncs the Hide Empty Staves toggle on every document change.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPixmap
from PySide6.QtWidgets import QColorDialog, QMenu, QWidget

from scoreanim.core.animation import DEFAULT_EFFECT, PRESETS
from scoreanim.core.project import (SetHideEmptyStaves, SetPartColor,
                                    SetPartEffect)
from scoreanim.core.score.identity import PartId

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

    def __init__(self, menu: QMenu, app_state: AppState, parent: QWidget,
                 open_score_setup: Callable[[], None],
                 open_staff_groups: Callable[[], None],
                 open_part_names: Callable[[], None]) -> None:
        self._menu = menu
        self._app_state = app_state
        self._parent = parent
        self._open_score_setup = open_score_setup
        self._open_staff_groups = open_staff_groups
        self._open_part_names = open_part_names
        self._hide_staves_action: QAction | None = None
        self._color_actions: dict[PartId, dict] = {}
        self._effect_actions: dict[PartId, dict] = {}

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
        self._effect_actions = {}
        setup_action = QAction("Score Setup…", menu)
        setup_action.triggered.connect(self._open_score_setup)
        menu.addAction(setup_action)
        groups_action = QAction("Staff Groups…", menu)
        groups_action.triggered.connect(self._open_staff_groups)
        menu.addAction(groups_action)
        names_action = QAction("Part Names…", menu)
        names_action.triggered.connect(self._open_part_names)
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
        menu.addAction(self._hide_staves_action)
        menu.addSeparator()
        for info in parts:
            pid = PartId(info.part_id)
            submenu = menu.addMenu(info.name)

            color_group = QActionGroup(submenu)
            color_actions: dict = {}
            for c in PART_COLORS:
                action = QAction(c, submenu)
                action.setCheckable(True)
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
            custom.triggered.connect(
                lambda _=False, p=pid: self._pick_part_color(p))
            color_group.addAction(custom)
            submenu.addAction(custom)
            color_actions["custom"] = custom
            no_color = QAction("No Color", submenu)
            no_color.setCheckable(True)
            no_color.setChecked(True)
            no_color.triggered.connect(
                lambda _=False, p=pid:
                self._app_state.execute(SetPartColor(p, None)))
            color_group.addAction(no_color)
            submenu.addAction(no_color)
            color_actions[None] = no_color
            self._color_actions[pid] = color_actions

            submenu.addSeparator()
            effect_group = QActionGroup(submenu)
            effect_actions: dict = {}
            default_action = QAction(f"Effect: {DEFAULT_EFFECT} (default)",
                                     submenu)
            default_action.setCheckable(True)
            default_action.setChecked(True)
            default_action.triggered.connect(
                lambda _=False, p=pid:
                self._app_state.execute(SetPartEffect(p, None)))
            effect_group.addAction(default_action)
            submenu.addAction(default_action)
            effect_actions[None] = default_action
            for name in sorted(PRESETS):
                if name == DEFAULT_EFFECT:
                    continue
                action = QAction(f"Effect: {name}", submenu)
                action.setCheckable(True)
                action.triggered.connect(
                    lambda _=False, p=pid, n=name:
                    self._app_state.execute(SetPartEffect(p, n)))
                effect_group.addAction(action)
                submenu.addAction(action)
                effect_actions[name] = action
            self._effect_actions[pid] = effect_actions

    def sync_checks(self, pid: PartId, rule) -> None:
        """Re-derive one part's checkmarks from its StyleRules entry."""
        color = rule.color if rule is not None else None
        effect = rule.effect if rule is not None else None
        color_actions = self._color_actions.get(pid, {})
        for key, action in color_actions.items():
            action.blockSignals(True)
            if key == "custom":
                action.setChecked(color is not None
                                  and color not in color_actions)
            else:
                action.setChecked(color == key)
            action.blockSignals(False)
        effect_actions = self._effect_actions.get(pid, {})
        known = effect in effect_actions
        for key, action in effect_actions.items():
            action.blockSignals(True)
            action.setChecked(effect == key if known else key is None)
            action.blockSignals(False)

    def sync_from_document(self, doc) -> None:
        """Resync Hide Empty Staves — execute, undo, and redo all arrive
        here via the window's document-changed pass."""
        if self._hide_staves_action is not None:
            self._hide_staves_action.blockSignals(True)
            self._hide_staves_action.setChecked(doc.hide_empty_staves)
            self._hide_staves_action.blockSignals(False)

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
