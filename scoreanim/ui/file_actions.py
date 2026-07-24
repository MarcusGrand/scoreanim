"""File & project actions: every menu handler that touches the
filesystem — score/project opens, audio binding, tempo-sidecar import,
save/save-as, and the export dialog (M1.9: the split that finishes the
no-monoliths audit after M1.7 still left the window ~580 lines).

Window glue like MainMenus, not a service: holds the window and drives
its public load/show surface. The engrave pipeline stays in
ui/score_loader.py and the window remains the composition root that
adopts each load; this module owns the file-session state that travels
with opens and saves — `score_name` (window title), `project_path`
(save target), `tempo_path` (F5 reload), and the remembered export
settings (session memory, R3).
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QMessageBox

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.project import (SUFFIX, FileRef, ImportTempoSetup,
                                    ProjectDoc, check_ref, load_project,
                                    sha256_of)
from scoreanim.core.project import save_project as write_project_file
from scoreanim.core.timing import parse_tempo_file, resolve_seconds
from scoreanim.ui.export_dialog import ExportDialog

if TYPE_CHECKING:
    from scoreanim.ui.main_window import MainWindow


class FileActions:
    def __init__(self, window: MainWindow) -> None:
        self._window = window
        self.score_name: str | None = None
        self.project_path: Path | None = None
        self.tempo_path: Path | None = None
        self._export_settings: dict | None = None    # session memory (R3)
        window.peaks.failed.connect(self._on_peaks_failed)

    # -- open dialogs ---------------------------------------------------------

    def open_score_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self._window, "Open MusicXML score", "",
            "MusicXML (*.musicxml *.xml);;All files (*)")
        if name:
            self.open_score(Path(name))

    def open_project_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self._window, "Open project", "",
            f"ScoreAnim projects (*{SUFFIX});;All files (*)")
        if name:
            self.open_project(Path(name))

    def open_audio_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self._window, "Open recording", "",
            "Audio (*.wav *.mp3 *.m4a *.flac);;All files (*)")
        if name:
            self.open_audio(Path(name))

    def open_audio(self, path: Path) -> None:
        """Audio binding: outside the undo stack (ruling 2026-07-11)."""
        w = self._window
        path = path.resolve()        # refs are absolute at runtime,
        w.app_state.bind_audio(FileRef(path=str(path),  # relative on disk
                                       sha256=sha256_of(path)))
        w.playback.open_audio(path)
        w.app_state.set_peaks(None)          # clear stale waveform
        w.peaks.start(path)

    def _on_peaks_failed(self, message: str) -> None:
        """No waveform is a degraded view, never a blocker for playback."""
        self._window.app_state.set_peaks(None)
        self._window.statusBar().showMessage(
            f"waveform unavailable: {message}")

    # -- tempo sidecar --------------------------------------------------------

    def open_tempo_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self._window, "Import tempo file", "",
            "Tempo files (*.tempo *.txt);;All files (*)")
        if name:
            self.import_tempo(Path(name))

    def import_tempo(self, path: Path) -> None:
        """Sidecar import — one undoable command replacing offset + all
        tempo events (the file's semantics)."""
        w = self._window
        try:
            setup = parse_tempo_file(path.read_text(), w.app_state.measures)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(w, "Tempo file", f"{path.name}: {exc}")
            return
        self.tempo_path = path
        if w.app_state.execute(ImportTempoSetup(
                setup.offset_seconds, setup.events, path.name)):
            w.statusBar().showMessage(
                f"tempo: {path.name} — offset {setup.offset_seconds:.2f}s, "
                f"{len(setup.events)} event(s)")

    def reload_tempo(self) -> None:
        if self.tempo_path is None:
            QMessageBox.warning(
                self._window, "Tempo file",
                "no tempo file imported (Import Tempo… first)")
            return
        self.import_tempo(self.tempo_path)

    # -- score / project ------------------------------------------------------

    def open_score(self, path: Path) -> None:
        """Fresh document from a bare score (undo stack reset — ruling
        2026-07-11). A sibling .tempo sidecar auto-imports as a command."""
        w = self._window
        path = path.resolve()        # refs are absolute at runtime
        stage = w.load_score(path, EngravingParams(), stage=None)
        doc = ProjectDoc(score=FileRef(path=str(path),
                                       sha256=sha256_of(path)),
                         stage=stage)
        self.project_path = None
        self.score_name = path.name
        self.tempo_path = None
        w.app_state.reset_document(doc)      # → _on_document_changed
        w.show_current()
        w.view.fit()
        # a score that overflows its page needs staff-count reduction —
        # offer the Score Setup dialog on open (Phase 12.4)
        if w.last_overflow:
            w.open_score_setup_dialog()

        sidecar = path.with_suffix(".tempo")
        if sidecar.exists():
            self.import_tempo(sidecar)

    def open_project(self, path: Path) -> None:
        """Re-derive everything from the saved intent: engrave the
        referenced score with the saved params/stage, install the doc,
        rebind audio. Hash mismatches warn; a missing score aborts
        (nothing to display); a project never auto-loads a sidecar."""
        w = self._window
        try:
            doc = load_project(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(w, "Open project", str(exc))
            return
        if doc.score is None:
            QMessageBox.warning(w, "Open project",
                                f"{path.name}: no score reference")
            return
        warnings = []
        score_warning = check_ref(doc.score)
        if score_warning is not None:
            if "missing" in score_warning:
                QMessageBox.warning(w, "Open project", score_warning)
                return
            warnings.append(score_warning)

        # groups + label overrides + hide flag engrave here once; the
        # reset_document below finds the _applied_* caches already equal
        # — no double engrave
        w.load_score(Path(doc.score.path), doc.engraving,
                     stage=doc.stage, groups=doc.staff_groups,
                     text_overrides=doc.text_overrides,
                     hide_empty_staves=doc.hide_empty_staves,
                     condense_groups=doc.condense_groups,
                     hide_first_system=doc.hide_first_system)
        self.project_path = path
        self.score_name = path.name
        self.tempo_path = None
        w.app_state.reset_document(doc)
        w.show_current()
        w.view.fit()

        if doc.audio is not None:
            audio_warning = check_ref(doc.audio)
            if audio_warning is not None:
                warnings.append(audio_warning)
            if audio_warning is None or "missing" not in audio_warning:
                audio_path = Path(doc.audio.path)
                w.playback.open_audio(audio_path)
                w.app_state.set_peaks(None)
                w.peaks.start(audio_path)
        if warnings:
            QMessageBox.warning(w, "Open project", "\n".join(warnings))

    # -- save -----------------------------------------------------------------

    def save_project(self) -> bool:
        if self.project_path is None:
            return self.save_project_as()
        write_project_file(self._window.app_state.doc, self.project_path)
        self._window.app_state.mark_saved()
        self._window.statusBar().showMessage(
            f"saved {self.project_path.name}")
        return True

    def save_project_as(self) -> bool:
        name, _ = QFileDialog.getSaveFileName(
            self._window, "Save project", "",
            f"ScoreAnim projects (*{SUFFIX})")
        if not name:
            return False
        path = Path(name)
        if path.suffix != SUFFIX:
            path = path.with_suffix(SUFFIX)
        self.project_path = path
        self.score_name = path.name
        return self.save_project()

    # -- export ---------------------------------------------------------------

    def open_export_dialog(self) -> None:
        w = self._window
        if w.animation_inputs is None:
            return
        w.playback.pause()                   # no live tick under the modal
        doc = w.app_state.doc
        offset, tempo_map, swing = w.timing_config(doc)
        duration = w.playback.transport.duration_seconds()
        if duration <= 0.0:                  # no audio loaded: score length
            score_end = max((m.start + m.quarter_length
                             for m in w.app_state.measures), default=0.0)
            duration = offset + resolve_seconds([score_end], tempo_map,
                                                swing)[0]
        dialog = ExportDialog(w.animation_inputs, doc.style, tempo_map,
                              swing, w.app_state.measures, offset,
                              duration, self.score_name or "score",
                              mode=doc.stage.mode,   # live doc, not the
                              overrides=dict(doc.layout_overrides),  # ditto
                              settings=self._export_settings,
                              parent=w)
        dialog.exec()
        self._export_settings = {**(self._export_settings or {}),
                                 **dialog.remembered()}
