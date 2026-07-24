"""Document → scene diff-sync (M1.7): part tints, per-element color
overrides, the ghost floor, stage texts, and hidden flags, each behind
an applied cache so every pass costs a diff, not a rebuild.

Execute, undo, and redo all arrive through the window's
document-changed pass — apply and revert ride the same code. The
caches are rebound per load (`bind_scenes`) to the fresh scene's
construction state, so the first pass after a load re-applies the
document's intent onto scenes that carry none of it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QColor

from scoreanim.core.animation import FLOOR_OPACITY, takes_part_color
from scoreanim.core.project import ProjectDoc
from scoreanim.core.score.identity import PartId

if TYPE_CHECKING:
    from scoreanim.render.scene import ScoreScenes
    from scoreanim.ui.parts_menu import PartsMenu


class DocumentSync:
    """Owns the applied caches and the styles/stage/hidden diffs."""

    def __init__(self, parts_menu: PartsMenu) -> None:
        self._parts_menu = parts_menu
        self._scenes: ScoreScenes | None = None
        self._applied_colors: dict[PartId, str | None] = {}
        self._applied_overrides: dict = {}     # ElementId → applied color
        self._applied_floor = FLOOR_OPACITY    # ghost opacity on the scenes
        self._applied_stage_texts: tuple = ()  # stage texts on the scenes
        self._applied_hidden: dict = {}    # ElementId → applied hidden flag

    def bind_scenes(self, scenes: ScoreScenes, stage_texts: tuple) -> None:
        """Adopt a load's fresh scenes: caches reset to the scene's
        construction state — ghosts at the default floor, the load's
        stage texts applied, nothing hidden, no tints."""
        self._scenes = scenes
        self._applied_colors = {}
        self._applied_overrides = {}
        self._applied_floor = FLOOR_OPACITY
        self._applied_stage_texts = stage_texts
        self._applied_hidden = {}

    def sync_styles(self, doc: ProjectDoc) -> None:
        """Diff the document's StyleRules onto the scene: part tints,
        then per-element color overrides on top (a part re-tint touches
        every item of the part, so overrides re-apply after it). The
        ghost floor rides along: the trigger-animated side updates via
        playback.set_style → applier re-resolve; the static spanner
        ghosts need this push. Part-menu checkmarks re-derive in the
        same loop."""
        if self._scenes is None:
            return
        if self._applied_floor != doc.style.floor_opacity:
            self._scenes.set_ghost_opacity(doc.style.floor_opacity)
            self._applied_floor = doc.style.floor_opacity
        parts_retinted = set()
        for pid in self._parts_menu.part_ids():
            rule = doc.style.parts.get(pid)
            color = rule.color if rule is not None else None
            if self._applied_colors.get(pid) != color:
                self._scenes.set_part_color(
                    pid, QColor(color) if color else None)
                self._applied_colors[pid] = color
                parts_retinted.add(pid)
            self._parts_menu.sync_checks(pid, rule)

        overrides = {eid: st.color for eid, st in doc.style.elements.items()
                     if st.color is not None}
        for eid, prev in list(self._applied_overrides.items()):
            item = self._scenes.items.get(eid)
            if item is None:
                del self._applied_overrides[eid]
                continue
            ident = item.identity
            retinted = ident is not None and ident.part in parts_retinted
            if eid not in overrides:                 # override removed →
                part_color = self._applied_colors.get(       # part color
                    ident.part if ident else None)
                item.set_color(QColor(part_color) if part_color else None)
                del self._applied_overrides[eid]
            elif retinted:
                del self._applied_overrides[eid]     # re-apply below
        for eid, color in overrides.items():
            if self._applied_overrides.get(eid) != color:
                item = self._scenes.items.get(eid)
                if item is not None and takes_part_color(item.identity):
                    item.set_color(QColor(color))
                    self._applied_overrides[eid] = color

    def sync_stage(self, doc: ProjectDoc) -> bool:
        """Diff the document's stage texts onto the scene (Phase 9.1).
        A text edit rebuilds just the stage-text layer — never a
        re-engrave. Returns True when texts were re-applied, so the
        window refreshes its retained AnimationInputs and export
        follows the edit (inputs.stage is otherwise a load-time
        snapshot, the Phase 7 staleness gotcha)."""
        if self._scenes is None \
                or doc.stage.texts == self._applied_stage_texts:
            return False
        self._scenes.set_stage_texts(doc.stage.texts)
        self._applied_stage_texts = doc.stage.texts
        return True

    def sync_hidden(self, doc: ProjectDoc) -> None:
        """Diff LayoutOverride.hidden onto the scene (Phase 9.2: tempo
        overlays hide the engraved mark)."""
        if self._scenes is None:
            return
        hidden = {eid: True for eid, o in doc.layout_overrides.items()
                  if o.hidden}
        for eid in list(self._applied_hidden):
            if eid not in hidden:
                self._scenes.set_element_hidden(eid, False)
                del self._applied_hidden[eid]
        for eid in hidden:
            if eid not in self._applied_hidden:
                self._scenes.set_element_hidden(eid, True)
                self._applied_hidden[eid] = True
