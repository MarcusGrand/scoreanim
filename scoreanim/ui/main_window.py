"""App shell: open a score, flip pages, zoom/pan, tint parts, and play a
recording against it — notes at floor opacity going full at onset.

Phase 4: the window owns an AppState (document + undo stack + shared
time axis) and is the only bridge between it and the transport. Every
timing/style edit is an undoable command; the tempo sidecar is an
import command; file opens reset/bind outside the stack (ruling
2026-07-11). On document_changed the window retimes the animation and
diffs part tints — views never talk to each other.
"""

from __future__ import annotations

from dataclasses import replace as _dc_replace
from pathlib import Path

from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.project import (HIDE_EMPTY_STAVES_DEFAULT, SUFFIX,
                                    ApplyTaps, FileRef,
                                    ImportTempoSetup,
                                    PresentationMode,
                                    ProjectDoc,
                                    StageConfig, check_ref, load_project,
                                    page_content_top, sha256_of)
from scoreanim.core.project import save_project as write_project_file
from scoreanim.core.timing import TempoMap, parse_tempo_file, resolve_seconds
from scoreanim.core.timing.taps import (TapSession, derive_tempo_events,
                                        start_residual)
from scoreanim.render.animate import AnimationApplier
from scoreanim.render.export import AnimationInputs
from scoreanim.render.scene import ScoreScenes
from scoreanim.ui.app_state import AppState
from scoreanim.ui.document_sync import DocumentSync
from scoreanim.ui.export_dialog import ExportDialog
from scoreanim.ui.inspector import Inspector
from scoreanim.ui.menus import MainMenus
from scoreanim.ui.parts_menu import PartsMenu
from scoreanim.ui.peaks_worker import PeakExtractor
from scoreanim.ui.playback import PlaybackController
from scoreanim.ui.part_names_dialog import PartNamesDialog
from scoreanim.ui.score_loader import LoadedScore, ScoreLoader
from scoreanim.ui.score_setup_dialog import ScoreSetupDialog
from scoreanim.ui.staff_groups_dialog import StaffGroupsDialog
from scoreanim.ui.stage_view import StageView
from scoreanim.ui.texts_dialog import TextsDialog
from scoreanim.ui.taps import TapRecorder
from scoreanim.ui.transport import LowerZone
from scoreanim.ui.window_state import (default_settings,
                                       restore_window_state,
                                       save_window_state)


class MainWindow(QMainWindow):
    def __init__(self, score_path: Path | None = None,
                 settings: QSettings | None = None) -> None:
        super().__init__()
        self.setWindowTitle("ScoreAnim")
        self._settings = settings if settings is not None \
            else default_settings()

        self._scenes: ScoreScenes | None = None
        self._animation_inputs: AnimationInputs | None = None
        self._applier: AnimationApplier | None = None
        self._export_settings: dict | None = None    # session memory (R3)
        self._page = 1
        self._system = 1
        self._band_by_system: dict = {}              # derived, never saved
        self._applied_mode = PresentationMode.PAGED  # what the view shows
        self._last_overflow = False          # last load overflowed a page
        self._parts: tuple = ()            # PartInfos of the loaded score
        self._score_name: str | None = None
        self._project_path: Path | None = None
        self._tempo_path: Path | None = None

        self.app_state = AppState(self)
        self.playback = PlaybackController(self)
        self.peaks = PeakExtractor(self)
        self.tap_recorder = TapRecorder(self.app_state,
                                        self.playback.transport, self)
        self.tap_recorder.status.connect(
            lambda msg: self.statusBar().showMessage(msg))
        self.tap_recorder.session_finished.connect(self._on_tap_session)

        # stage central and alone; the timeline area is the lower-zone
        # bottom dock (M1.3) — the dock cannot swallow the central widget,
        # which carries over the old splitter's collapsible=False guarantee
        self.view = StageView()
        self.setCentralWidget(self.view)
        self.lower_zone = LowerZone(self.app_state, self.playback,
                                    self.tap_recorder, self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                           self.lower_zone)
        # right-hand inspector (M1.4): Follow/Systems, floor + Sweep,
        # Selection placeholder; resynced in _on_document_changed
        self.inspector = Inspector(self.app_state, self.playback, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.inspector)

        self.peaks.progress.connect(
            lambda: self.app_state.set_peaks(self.peaks.cache))
        self.peaks.finished.connect(
            lambda: self.app_state.set_peaks(self.peaks.cache))
        self.peaks.failed.connect(self._on_peaks_failed)

        # follow reports page AND system; the window routes by the
        # document's presentation mode (Phase 7.4)
        self.playback.page_changed.connect(self._on_page_followed)
        self.playback.system_changed.connect(self._on_system_followed)
        self.playback.status_message.connect(
            lambda msg: self.statusBar().showMessage(msg))
        self.playback.time_changed.connect(self._on_time)
        # duration comes from the CONTROLLER, not the audio wrapper, so
        # no-audio playback (FIX 2) drives the same UI paths; play-state
        # feedback (button text, tap disarm) lives on the transport strip
        self.playback.duration_changed.connect(
            self.app_state.axis.set_duration)

        self.app_state.seek_requested.connect(self.playback.seek)
        self.app_state.document_changed.connect(self._on_document_changed)
        self.app_state.status.connect(
            lambda msg: self.statusBar().showMessage(msg))

        # static chrome (M1.5): the five menus, the slim toolbar, and
        # window-level shortcut registration; the window keeps the refs
        # it mutates (undo text, enable-on-load, page readout)
        self.menus = MainMenus(self)
        # dynamic Score-menu content (M1.6): rebuilt per load; check
        # state re-derived from the document by the sync passes below
        self.parts_menu = PartsMenu(
            self.menus.score_menu, self.app_state, self,
            self._open_score_setup_dialog, self._open_staff_groups_dialog,
            self._open_part_names_dialog)
        # load pipeline + document→scene diff-sync (M1.7): the loader
        # returns a LoadedScore bundle _install adopts; the sync owns
        # the applied caches the document-changed pass diffs against
        self.loader = ScoreLoader()
        self.doc_sync = DocumentSync(self.parts_menu)

        # shell layout (M1.8): restore once docks + toolbar exist; a
        # fresh store yields the first-run default size. UI state only —
        # nothing document-derived lives in the settings (rule 5).
        restore_window_state(self, self.inspector.sections, self._settings)

        if score_path is not None:
            self.open_score(score_path)

    # -- file dialogs (menu handlers) ----------------------------------------

    def open_score_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Open MusicXML score", "",
            "MusicXML (*.musicxml *.xml);;All files (*)")
        if name:
            self.open_score(Path(name))

    def open_project_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Open project", "",
            f"ScoreAnim projects (*{SUFFIX});;All files (*)")
        if name:
            self.open_project(Path(name))

    def open_audio_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Open recording", "",
            "Audio (*.wav *.mp3 *.m4a *.flac);;All files (*)")
        if name:
            self.open_audio(Path(name))

    def open_audio(self, path: Path) -> None:
        """Audio binding: outside the undo stack (ruling 2026-07-11)."""
        path = path.resolve()        # refs are absolute at runtime,
        self.app_state.bind_audio(FileRef(path=str(path),  # relative on disk
                                          sha256=sha256_of(path)))
        self.playback.open_audio(path)
        self.app_state.set_peaks(None)       # clear stale waveform
        self.peaks.start(path)

    def _on_peaks_failed(self, message: str) -> None:
        """No waveform is a degraded view, never a blocker for playback."""
        self.app_state.set_peaks(None)
        self.statusBar().showMessage(f"waveform unavailable: {message}")

    def open_tempo_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Import tempo file", "",
            "Tempo files (*.tempo *.txt);;All files (*)")
        if name:
            self._import_tempo(Path(name))

    def _import_tempo(self, path: Path) -> None:
        """Sidecar import — one undoable command replacing offset + all
        tempo events (the file's semantics)."""
        try:
            setup = parse_tempo_file(path.read_text(),
                                     self.app_state.measures)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Tempo file", f"{path.name}: {exc}")
            return
        self._tempo_path = path
        if self.app_state.execute(ImportTempoSetup(
                setup.offset_seconds, setup.events, path.name)):
            self.statusBar().showMessage(
                f"tempo: {path.name} — offset {setup.offset_seconds:.2f}s, "
                f"{len(setup.events)} event(s)")

    def reload_tempo(self) -> None:
        if self._tempo_path is None:
            QMessageBox.warning(self, "Tempo file",
                                "no tempo file imported (Import Tempo… first)")
            return
        self._import_tempo(self._tempo_path)

    # -- playback feedback -----------------------------------------------------

    def _on_time(self, audio_seconds: float, duration: float) -> None:
        # slider + time label feedback lives on the transport strip
        # (M1.3); the window keeps the playhead push to the shared axis
        self.app_state.set_playhead(audio_seconds)

    def _on_tap_session(self, session: TapSession) -> None:
        doc = self.app_state.doc
        derivation = derive_tempo_events(session)
        residual = start_residual(
            session, TempoMap(list(doc.timing.tempo_events)),
            doc.timing.offset_seconds)
        if self.app_state.execute(ApplyTaps(
                session, derivation.events,
                (derivation.first_beat, derivation.last_beat), "derive")):
            notes = (" · " + "; ".join(derivation.warnings)
                     if derivation.warnings else "")
            self.statusBar().showMessage(
                f"taps: {len(session.taps)} taps → "
                f"{len(derivation.events)} tempo event(s) in "
                f"[{derivation.first_beat:g}, {derivation.last_beat:g}) · "
                f"start residual {residual * 1000:+.0f} ms{notes}")

    # -- document → world -------------------------------------------------------

    def _timing_config(self, doc: ProjectDoc) -> tuple[float, TempoMap, tuple]:
        """THE construction of (offset, TempoMap, swing) from document
        intent — one expression shared by live retiming and export, so
        the two paths cannot diverge."""
        return (doc.timing.offset_seconds,
                TempoMap(list(doc.timing.tempo_events)),
                doc.timing.swing_regions)

    def _on_document_changed(self) -> None:
        doc = self.app_state.doc
        # engraving inputs changed (execute, undo, OR redo — all arrive
        # here): re-derive the engraved world FIRST, so the sync below
        # re-pushes timing/tints/floor/stage/hidden onto the fresh
        # scenes in the same pass
        if (self._scenes is not None and doc.score is not None
                and self.loader.needs_reengrave(doc)):
            self._reengrave(doc)
        self.playback.set_timing_config(*self._timing_config(doc))
        self.doc_sync.sync_styles(doc)
        if self.doc_sync.sync_stage(doc) \
                and self._animation_inputs is not None:
            # a stage-text edit must reach export too — inputs.stage is
            # otherwise a load-time snapshot (Phase 7 staleness gotcha)
            self._animation_inputs = _dc_replace(self._animation_inputs,
                                                 stage=doc.stage)
        self.doc_sync.sync_hidden(doc)
        self.playback.set_style(doc.style)
        self.lower_zone.strip.sync_from_document(doc)
        self.inspector.sync_from_document(doc)
        self.parts_menu.sync_from_document(doc)
        self._sync_presentation_mode(doc.stage.mode)
        undo_text = self.app_state.undo_text()
        redo_text = self.app_state.redo_text()
        undo = self.menus.undo_action
        redo = self.menus.redo_action
        undo.setEnabled(self.app_state.can_undo)
        undo.setText(f"Undo {undo_text}" if undo_text else "Undo")
        redo.setEnabled(self.app_state.can_redo)
        redo.setText(f"Redo {redo_text}" if redo_text else "Redo")
        self._sync_title()

    def _sync_title(self) -> None:
        star = " *" if self.app_state.is_dirty else ""
        name = f" — {self._score_name}{star}" if self._score_name else ""
        self.setWindowTitle(f"ScoreAnim{name}")

    # -- score / project --------------------------------------------------------

    def open_score(self, path: Path) -> None:
        """Fresh document from a bare score (undo stack reset — ruling
        2026-07-11). A sibling .tempo sidecar auto-imports as a command."""
        path = path.resolve()        # refs are absolute at runtime
        stage = self._load_score(path, EngravingParams(), stage=None)
        doc = ProjectDoc(score=FileRef(path=str(path),
                                       sha256=sha256_of(path)),
                         stage=stage)
        self._project_path = None
        self._score_name = path.name
        self._tempo_path = None
        self.app_state.reset_document(doc)   # → _on_document_changed
        self._show_current()
        self.view.fit()
        # a score that overflows its page needs staff-count reduction —
        # offer the Score Setup dialog on open (Phase 12.4)
        if self._last_overflow:
            self._open_score_setup_dialog()

        sidecar = path.with_suffix(".tempo")
        if sidecar.exists():
            self._import_tempo(sidecar)

    def open_project(self, path: Path) -> None:
        """Re-derive everything from the saved intent: engrave the
        referenced score with the saved params/stage, install the doc,
        rebind audio. Hash mismatches warn; a missing score aborts
        (nothing to display); a project never auto-loads a sidecar."""
        try:
            doc = load_project(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Open project", str(exc))
            return
        if doc.score is None:
            QMessageBox.warning(self, "Open project",
                                f"{path.name}: no score reference")
            return
        warnings = []
        score_warning = check_ref(doc.score)
        if score_warning is not None:
            if "missing" in score_warning:
                QMessageBox.warning(self, "Open project", score_warning)
                return
            warnings.append(score_warning)

        # groups + label overrides + hide flag engrave here once; the
        # reset_document below finds the _applied_* caches already equal
        # — no double engrave
        self._load_score(Path(doc.score.path), doc.engraving,
                         stage=doc.stage, groups=doc.staff_groups,
                         text_overrides=doc.text_overrides,
                         hide_empty_staves=doc.hide_empty_staves,
                         condense_groups=doc.condense_groups,
                         hide_first_system=doc.hide_first_system)
        self._project_path = path
        self._score_name = path.name
        self._tempo_path = None
        self.app_state.reset_document(doc)
        self._show_current()
        self.view.fit()

        if doc.audio is not None:
            audio_warning = check_ref(doc.audio)
            if audio_warning is not None:
                warnings.append(audio_warning)
            if audio_warning is None or "missing" not in audio_warning:
                audio_path = Path(doc.audio.path)
                self.playback.open_audio(audio_path)
                self.app_state.set_peaks(None)
                self.peaks.start(audio_path)
        if warnings:
            QMessageBox.warning(self, "Open project", "\n".join(warnings))

    def _load_score(self, path: Path, params: EngravingParams,
                    stage: StageConfig | None,
                    groups: tuple = (),
                    text_overrides: dict | None = None,
                    hide_empty_staves: bool = HIDE_EMPTY_STAVES_DEFAULT,
                    condense_groups: tuple = (),
                    hide_first_system: bool = False
                    ) -> StageConfig:
        """Fresh-load entry: engrave + wire, then reset to page 1."""
        loaded = self.loader.load(path, params, stage,
                                  self.app_state.doc.style, groups,
                                  text_overrides or {},
                                  hide_empty_staves, condense_groups,
                                  hide_first_system)
        self._install(loaded)
        self._page = 1
        self._system = 1
        return loaded.stage

    def _reengrave(self, doc: ProjectDoc) -> None:
        """Re-derive the engraved world after a staff-group, part-label,
        or hide-empty-staves change, preserving page/system/zoom (no
        view.fit, no position reset). ~0.6 s on the GUI thread per call
        (engrave + scene rebuild), so these commands must arrive via
        execute(), never preview()."""
        loaded = self.loader.load(Path(doc.score.path), doc.engraving,
                                  doc.stage, doc.style, doc.staff_groups,
                                  doc.text_overrides, doc.hide_empty_staves,
                                  doc.condense_groups, doc.hide_first_system)
        self._install(loaded)
        self._show_current()             # install the fresh scene

    def _install(self, loaded: LoadedScore) -> None:
        """Adopt one load's derived world and point every consumer at
        it: view scenes, export inputs, playback animation, the shared
        measure axis, the per-load Score menu."""
        self._scenes = loaded.scenes
        self._animation_inputs = loaded.animation_inputs
        self._applier = loaded.applier
        self.doc_sync.bind_scenes(loaded.scenes, loaded.stage.texts)
        self.menus.export_action.setEnabled(True)
        self.menus.texts_action.setEnabled(True)
        self.playback.set_animation(loaded.applier, loaded.measures)
        self._band_by_system = loaded.band_by_system
        self.app_state.set_measures(loaded.measures)
        self._parts = loaded.parts
        self.parts_menu.rebuild(loaded.parts)
        self._last_overflow = loaded.overflow
        self.statusBar().showMessage(loaded.status_line)

    # -- staff groups ------------------------------------------------------------

    def _open_staff_groups_dialog(self) -> None:
        if not self._parts:
            return
        StaffGroupsDialog(self.app_state, self._parts, parent=self).exec()

    def _open_score_setup_dialog(self) -> None:
        if not self._parts:
            return
        ScoreSetupDialog(self.app_state, self._parts, parent=self).exec()

    def _open_part_names_dialog(self) -> None:
        if not self._parts:
            return
        # a PROVIDER, not a snapshot: each rename re-engraves and
        # refreshes self._parts with the effective names — the dialog's
        # rebuild must show them
        PartNamesDialog(self.app_state, parts_provider=lambda: self._parts,
                        parent=self).exec()

    # -- texts ---------------------------------------------------------------------

    def open_texts_dialog(self) -> None:
        if self._animation_inputs is None:
            return
        # band = the free space above the top staff, re-derived from the
        # CURRENT engraved layout (runtime data for the header refit —
        # the doc stores intent only)
        layout = self._animation_inputs.layout
        band = page_content_top(layout)
        tempo_elements = tuple(el for el in layout.elements
                               if el.text_class == "tempo")
        TextsDialog(self.app_state, band=band,
                    tempo_elements=tempo_elements, parent=self).exec()

    # -- export --------------------------------------------------------------------

    def open_export_dialog(self) -> None:
        if self._animation_inputs is None:
            return
        self.playback.pause()                # no live tick under the modal
        doc = self.app_state.doc
        offset, tempo_map, swing = self._timing_config(doc)
        duration = self.playback.transport.duration_seconds()
        if duration <= 0.0:                  # no audio loaded: score length
            score_end = max((m.start + m.quarter_length
                             for m in self.app_state.measures), default=0.0)
            duration = offset + resolve_seconds([score_end], tempo_map,
                                                swing)[0]
        dialog = ExportDialog(self._animation_inputs, doc.style, tempo_map,
                              swing, self.app_state.measures, offset,
                              duration, self._score_name or "score",
                              mode=doc.stage.mode,   # live doc, not the
                              overrides=dict(doc.layout_overrides),  # ditto
                              settings=self._export_settings,
                              parent=self)
        dialog.exec()
        self._export_settings = {**(self._export_settings or {}),
                                 **dialog.remembered()}

    # -- save / load --------------------------------------------------------------

    def save_project(self) -> bool:
        if self._project_path is None:
            return self.save_project_as()
        write_project_file(self.app_state.doc, self._project_path)
        self.app_state.mark_saved()
        self.statusBar().showMessage(f"saved {self._project_path.name}")
        return True

    def save_project_as(self) -> bool:
        name, _ = QFileDialog.getSaveFileName(
            self, "Save project", "",
            f"ScoreAnim projects (*{SUFFIX})")
        if not name:
            return False
        path = Path(name)
        if path.suffix != SUFFIX:
            path = path.with_suffix(SUFFIX)
        self._project_path = path
        self._score_name = path.name
        return self.save_project()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.app_state.is_dirty:
            answer = QMessageBox.question(
                self, "Unsaved changes", "Save project before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Save:
                if not self.save_project():
                    event.ignore()
                    return
            elif answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        # accepted close only — a cancelled close saves nothing (M1.8)
        save_window_state(self, self.inspector.sections, self._settings)
        event.accept()

    def show_page(self, page: int) -> None:
        if self._scenes is None:
            return
        self._page = max(1, min(page, self._scenes.page_count))
        self.view.show_scene(self._scenes.scene_for_page(self._page))
        self.menus.page_label.setText(
            f" {self._page}/{self._scenes.page_count} ")
        self.menus.prev_action.setEnabled(self._page > 1)
        self.menus.next_action.setEnabled(
            self._page < self._scenes.page_count)

    def show_system(self, system: int) -> None:
        """Frame one system's band (Phase 7.4): the band's page scene,
        centered, masked — the page flip is implied by the band's page."""
        if self._scenes is None or not self._band_by_system:
            return
        self._system = max(1, min(system, len(self._band_by_system)))
        band = self._band_by_system[self._system]
        self._page = band.page                   # keep page state coherent
        rect = band.rect
        self.view.show_system_band(
            self._scenes.scene_for_page(band.page),
            QRectF(rect.x, rect.y, rect.w, rect.h))
        self.menus.page_label.setText(
            f" sys {self._system}/{len(self._band_by_system)} ")
        self.menus.prev_action.setEnabled(self._system > 1)
        self.menus.next_action.setEnabled(
            self._system < len(self._band_by_system))

    def step(self, delta: int) -> None:
        """Prev/next in the current presentation unit."""
        if self._applied_mode is PresentationMode.SYSTEM:
            self.show_system(self._system + delta)
        else:
            self.show_page(self._page + delta)

    def _show_current(self) -> None:
        """(Re-)show the current position in the current mode — the
        mode-aware version of the old show_page(1) after a load."""
        if self._applied_mode is PresentationMode.SYSTEM:
            self.show_system(self._system)
        else:
            self.show_page(self._page)

    def _on_page_followed(self, page: int) -> None:
        if self._applied_mode is PresentationMode.PAGED:
            self.show_page(page)

    def _on_system_followed(self, system: int) -> None:
        if self._applied_mode is PresentationMode.SYSTEM:
            self.show_system(system)

    def _sync_presentation_mode(self, mode: PresentationMode) -> None:
        """Diff the document's mode onto the view (called on every
        document change — commands, undo, project load)."""
        if mode is self._applied_mode:
            return
        self._applied_mode = mode
        if self._scenes is None:
            return
        if mode is PresentationMode.SYSTEM:
            self.show_system(self._applier.current_system()
                             if self._applier is not None else 1)
        else:
            self.view.clear_band()
            self.show_page(self._applier.current_page()
                           if self._applier is not None else self._page)
