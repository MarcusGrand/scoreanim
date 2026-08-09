"""The stage's right-click menu (2026-08-09).

One controller for the context menu the stage view requests: a
"Staves" submenu listing EVERY part of the loaded score — hidden ones
included, or nothing could ever be shown again — with a checkmark per
part. Unchecking hides the part everywhere (SetPartHidden, one undo
entry, a ~0.6 s re-engrave like the Score menu's hide toggles);
checking shows it again.

Unlike PartsMenu, which syncs persistent menu-bar actions with the
blockSignals idiom, this menu is built FRESH on every popup: check
state is read straight off the document at build time, so there is
nothing to resync and undo/redo cost nothing here.

Owns no document state. The roster arrives from the installer per load
(`bind`), and every trigger routes through `app_state.execute`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMenu, QWidget

from scoreanim.core.project import SetPartHidden
from scoreanim.core.score.identity import PartId

if TYPE_CHECKING:
    from scoreanim.ui.app_state import AppState
    from scoreanim.ui.stage_view import StageView


class StageMenu:
    """Build-per-popup context menu for the stage view."""

    def __init__(self, app_state: AppState, view: StageView,
                 parent: QWidget | None = None) -> None:
        self._app_state = app_state
        self._parent = parent
        self._all_parts: tuple = ()      # FULL roster (PartInfos), per load
        view.context_menu_requested.connect(self.popup)

    def bind(self, all_parts) -> None:
        """The loaded score's full roster, hidden parts included."""
        self._all_parts = tuple(all_parts)

    def build(self) -> QMenu | None:
        """The menu as the document stands right now, or None before
        any score is loaded. Split from popup so tests can walk it."""
        if not self._all_parts:
            return None
        doc = self._app_state.doc
        roster = tuple(PartId(p.part_id) for p in self._all_parts)
        visible = [pid for pid in roster if pid not in doc.hidden_parts]
        menu = QMenu(self._parent)
        # QMenu(title, parent) rather than addMenu(title): the latter's
        # returned wrapper is Python-owned in PySide6, so the submenu's
        # C++ object dies with this function's locals — the explicit Qt
        # parent keeps it alive as long as the menu itself
        staves = QMenu("Staves", menu)
        menu.addMenu(staves)
        for info in self._all_parts:
            pid = PartId(info.part_id)
            action = staves.addAction(info.name or str(pid))
            action.setCheckable(True)
            action.setChecked(pid not in doc.hidden_parts)
            # the command would refuse anyway; graying says so up front
            if visible == [pid]:
                action.setEnabled(False)
            # default-arg capture (the PartsMenu idiom); `checked` is the
            # action's NEW state, so unchecking asks to hide
            action.triggered.connect(
                lambda checked=False, p=pid, order=roster:
                self._app_state.execute(SetPartHidden(p, not checked, order)))
        return menu

    def popup(self, global_pos, _scene_pos) -> None:
        menu = self.build()
        if menu is not None:
            menu.exec(global_pos)
