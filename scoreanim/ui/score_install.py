"""The load pipeline: engrave (or re-engrave) and adopt the result.

Lifted verbatim out of the window, which is a composition root and was
carrying this whole second job past the module ceiling. One component,
one job: run the loader, then point every per-load consumer at the
fresh derived world (`install`). The window stays the owner of the
components this binds — the installer only walks them.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.project import (HIDE_EMPTY_STAVES_DEFAULT, ProjectDoc,
                                    StageConfig)
from scoreanim.ui import tips

if TYPE_CHECKING:
    from scoreanim.ui.main_window import MainWindow
    from scoreanim.ui.score_loader import LoadedScore


class ScoreInstaller:
    """load_score / reengrave / install, bound to the window."""

    def __init__(self, window: MainWindow) -> None:
        self._w = window

    def load_score(self, path: Path, params: EngravingParams,
                   stage: StageConfig | None,
                   groups: tuple = (),
                   text_overrides: dict | None = None,
                   hide_empty_staves: bool = HIDE_EMPTY_STAVES_DEFAULT,
                   condense_groups: tuple = (),
                   hide_first_system: bool = False,
                   hidden_parts: frozenset = frozenset(),
                   system_staff_hides: dict | None = None
                   ) -> StageConfig:
        """Fresh-load entry: engrave + wire, then reset to page 1."""
        w = self._w
        loaded = w.loader.load(path, params, stage,
                               w.app_state.doc.style, groups,
                               text_overrides or {},
                               hide_empty_staves, condense_groups,
                               hide_first_system,
                               w.app_state.doc.system_break_overrides,
                               w.app_state.doc.page_break_overrides,
                               w.app_state.doc.stem_directions,
                               w.app_state.doc.trigger_overrides,
                               hidden_parts, system_staff_hides,
                               w.app_state.doc.tied_notes_as_one)
        self.install(loaded)
        w.router.reset()
        return loaded.stage

    def break_anchor(self, doc: ProjectDoc) -> int | None:
        """Which measure a break edit touched, for the view to re-anchor
        to (M5.5 D8; generalized to both override maps in M6.5, D11).
        Diffed against the loader's applied inputs rather than passed
        down from the action, so undo and redo re-anchor on the same
        path — and so a change that touches many ordinals at once (a
        project load) anchors nowhere and keeps the position.

        A gesture writes at most TWO ordinals over the UNION of the two
        maps — M5.7's move-up suppresses this system's start and forces
        the remainder; a page toggle writes its own ordinal plus, at
        most, the clearing of a contradicting system override at the
        SAME ordinal (D3) — and the anchor is the LOWEST of them, which
        is where the affected music is (D14)."""
        w = self._w
        changed: set[int] = set()
        for before, after in ((w.loader.applied_breaks,
                               dict(doc.system_break_overrides)),
                              (w.loader.applied_page_breaks,
                               dict(doc.page_break_overrides))):
            changed |= {o for o in set(before) | set(after)
                        if before.get(o) != after.get(o)}
        return min(changed) if 1 <= len(changed) <= 2 else None

    def reengrave(self, doc: ProjectDoc,
                  anchor_measure: int | None = None) -> None:
        """Re-derive the engraved world after a staff-group, part-label,
        hide-empty-staves, or system-break change, preserving
        page/system/zoom (no view.fit, no position reset). ~0.6 s on the
        GUI thread per call (engrave + scene rebuild), so these commands
        must arrive via execute(), never preview()."""
        w = self._w
        loaded = w.loader.load(Path(doc.score.path), doc.engraving,
                               doc.stage, doc.style, doc.staff_groups,
                               doc.text_overrides, doc.hide_empty_staves,
                               doc.condense_groups, doc.hide_first_system,
                               doc.system_break_overrides,
                               doc.page_break_overrides,
                               doc.stem_directions,
                               doc.trigger_overrides,
                               doc.hidden_parts,
                               doc.system_staff_hides,
                               doc.tied_notes_as_one)
        self.install(loaded)
        # a break edit re-anchors to the measure it touched, so the stage
        # stays where you were working (D8); everything else re-shows the
        # position it had
        if anchor_measure is not None:
            w.router.show_measure(anchor_measure)
        else:
            w.router.show_current()   # install the fresh scene

    def install(self, loaded: LoadedScore) -> None:
        """Adopt one load's derived world and point every consumer at
        it: view scenes, export inputs, playback animation, the shared
        measure axis, the per-load Score menu."""
        w = self._w
        w._scenes = loaded.scenes
        w.animation_inputs = loaded.animation_inputs
        w.doc_sync.bind_scenes(loaded.scenes, loaded.stage.texts)
        w.selection.bind_scenes(loaded.scenes)   # also clears selection
        w.delete_action.bind_scenes(loaded.scenes)   # the :seg registry
        # the drawn geometry a stem's CURRENT direction is read from
        w.stem_flip_action.bind_layout(loaded.animation_inputs.layout)
        w.router.bind(loaded.scenes, loaded.band_by_system,
                      loaded.applier, loaded.system_of_measure,
                      loaded.systems_frame)
        w.break_action.bind(loaded.system_of_measure,
                            loaded.page_of_measure)
        w.text_edit.bind(loaded.scenes, loaded.animation_inputs.layout,
                         loaded.parts)
        w.nudge.bind_scenes(loaded.scenes)
        # the :seg fan-out only ever names ids the load actually has
        w.inspector.selection_panel.style_controls.bind_scenes(
            loaded.scenes)
        # the stepper reads the CURRENT schedule through a provider —
        # the window swaps it on a live rebuild, so a pull never stales
        w.inspector.selection_panel.trigger_controls.bind_score(
            loaded.animation_inputs.layout, loaded.measures,
            lambda: (w.animation_inputs.schedule
                     if w.animation_inputs is not None else None))
        # the on-page onset cursor: same provider, plus the bands its
        # line spans and the fresh scenes it draws into
        w.onset_cursor.bind(
            loaded.scenes, loaded.animation_inputs.layout,
            loaded.band_by_system, loaded.system_of_measure,
            lambda: (w.animation_inputs.schedule
                     if w.animation_inputs is not None else None))
        # both were grayed with "Open a score first" on them (E2); the
        # score is in now, so they go live and the reason comes off
        tips.gate(w.menus.export_action, True, tips.NEEDS_SCORE)
        tips.gate(w.menus.texts_action, True, tips.NEEDS_SCORE)
        w.playback.set_animation(loaded.applier, loaded.measures)
        w.app_state.set_measures(loaded.measures)
        w.parts_menu.rebuild(loaded.parts)
        # the stage's Staves menu lists the FULL roster, hidden included;
        # the per-system half needs the bands and per-system facts too
        w.stage_menu.bind(loaded.all_parts)
        w.stage_menu.bind_systems(loaded.scenes, loaded.band_by_system,
                                  loaded.first_measure_of_system,
                                  loaded.noted_parts_by_system)
        # fresh scenes rebuild their paper rects visible, so the
        # overlay preview's paper-hiding half is re-applied per load
        w.apply_overlay_preview()
        w.hints.message(loaded.status_line)
