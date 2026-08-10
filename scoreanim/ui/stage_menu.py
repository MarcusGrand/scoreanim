"""The stage's right-click menu (2026-08-09; per-system half 2026-08-10).

Two submenus, both about staves, both built FRESH on every popup so
check state is read straight off the document — nothing to resync,
undo/redo cost nothing here.

"Staves" lists EVERY part of the loaded score — hidden ones included,
or nothing could ever be shown again — with a checkmark per part.
Unchecking hides the part everywhere (SetPartHidden, one undo entry, a
~0.6 s re-engrave like the Score menu's hide toggles).

"Staves in this system" appears when the right-click lands on a score
page: the system under the cursor resolves from the band map, and each
part gets a checkable entry scoped to THAT system
(SetSystemStaffHidden, keyed by the system's starting measure). An
entry grays when the hide could not work and says nothing about why —
the reasons are the mechanism's own limits: the part plays notes
there, the part is hidden everywhere already, empty-staff hiding is
off (optimize is the mechanism), or it is system 1 without the
first-system option. An entry that IS hidden never grays, so a stale
override can always be cleared.

Owns no document state. The roster and the per-system facts arrive
from the installer per load (`bind` / `bind_systems`), and every
trigger routes through `app_state.execute`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMenu, QWidget

from scoreanim.core.project import SetPartHidden, SetSystemStaffHidden
from scoreanim.core.score.identity import PartId

if TYPE_CHECKING:
    from scoreanim.ui.app_state import AppState
    from scoreanim.ui.stage_view import StageView


class StageMenu:
    """Build-per-popup context menu for the stage view."""

    def __init__(self, app_state: AppState, view: StageView,
                 parent: QWidget | None = None) -> None:
        self._app_state = app_state
        self._view = view
        self._parent = parent
        self._all_parts: tuple = ()      # FULL roster (PartInfos), per load
        self._scenes = None              # ScoreScenes, for scene → page
        self._band_by_system: dict = {}
        self._first_measure: dict = {}   # system → starting ordinal
        self._noted: dict = {}           # system → parts with noteheads
        view.context_menu_requested.connect(self.popup)

    def bind(self, all_parts) -> None:
        """The loaded score's full roster, hidden parts included."""
        self._all_parts = tuple(all_parts)

    def bind_systems(self, scenes, band_by_system: dict,
                     first_measure_of_system: dict,
                     noted_parts_by_system: dict) -> None:
        """The per-system facts of the loaded score: bands for hit
        resolution, each system's starting measure (the command key),
        and which parts play notes where (those staves cannot hide)."""
        self._scenes = scenes
        self._band_by_system = dict(band_by_system)
        self._first_measure = dict(first_measure_of_system)
        self._noted = dict(noted_parts_by_system)

    # -- resolution --------------------------------------------------------

    def _system_at(self, scene, scene_pos) -> int | None:
        """The system under (or nearest to) a scene position, on the
        page that scene shows. None when nothing resolves."""
        if self._scenes is None or scene is None or scene_pos is None:
            return None
        try:
            page = self._scenes.scenes.index(scene) + 1
        except ValueError:
            return None
        bands = [b for b in self._band_by_system.values() if b.page == page]
        if not bands:
            return None

        def distance(band) -> float:
            top, bottom = band.rect.y, band.rect.y + band.rect.h
            y = scene_pos.y()
            return 0.0 if top <= y <= bottom else min(abs(y - top),
                                                      abs(y - bottom))
        return min(bands, key=distance).system

    # -- build -------------------------------------------------------------

    def build(self, scene=None, scene_pos=None) -> QMenu | None:
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
        system = self._system_at(scene, scene_pos)
        if system is not None and system in self._first_measure:
            self._add_system_menu(menu, doc, roster, system)
        return menu

    def _add_system_menu(self, menu: QMenu, doc, roster, system: int) -> None:
        ordinal = self._first_measure[system]
        hides = doc.system_staff_hides.get(ordinal, frozenset())
        noted = self._noted.get(system, frozenset())
        submenu = QMenu("Staves in This System", menu)
        menu.addMenu(submenu)
        # the mechanism's own limits (see system_hides.py): optimize
        # must run, and system 1 only condenses with the option on
        mechanism_ok = doc.hide_empty_staves and (
            system != 1 or doc.hide_first_system)
        showable = [p for p in roster
                    if p not in doc.hidden_parts and p not in hides]
        for info in self._all_parts:
            pid = PartId(info.part_id)
            hidden_here = pid in hides
            action = submenu.addAction(info.name or str(pid))
            action.setCheckable(True)
            action.setChecked(not hidden_here)
            if not hidden_here:          # a hide can always be cleared
                blocked = (not mechanism_ok
                           or pid in doc.hidden_parts
                           or str(pid) in noted
                           or showable == [pid])
                action.setEnabled(not blocked)
            action.triggered.connect(
                lambda checked=False, p=pid, o=ordinal, order=roster:
                self._app_state.execute(
                    SetSystemStaffHidden(o, p, not checked, order)))

    def popup(self, global_pos, scene_pos) -> None:
        menu = self.build(self._view.scene(), scene_pos)
        if menu is not None:
            menu.exec(global_pos)
