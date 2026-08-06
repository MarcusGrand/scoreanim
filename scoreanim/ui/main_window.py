"""App shell: open a score, flip pages, zoom/pan, tint parts, and play a
recording against it — notes at floor opacity going full at onset.

Phase 4: the window owns an AppState (document + undo stack + shared
time axis) and is the only bridge between it and the transport. Every
timing/style edit is an undoable command; the tempo sidecar is an
import command; file opens reset/bind outside the stack (ruling
2026-07-11). On document_changed the window retimes the animation and
diffs part tints — views never talk to each other.

M3.0 (BACKLOG 9b) took two more jobs out of here: presentation routing
(page/system state + prev/next/follow) is `ui/view_router.py`, and the
three part-shaped dialogs went to `ui/parts_menu.py`, which was already
handed the parts they need. M3.1 took the fourth, Texts…, to
`ui/text_edit.py`, which now owns the engraved layout that dialog reads.
What is left is composition, the document→world sync pass, and the load
install.
"""

from __future__ import annotations

import traceback
from dataclasses import replace as _dc_replace
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QMainWindow, QMessageBox

from scoreanim.core.project import ProjectDoc, StageConfig
from scoreanim.core.timing import TempoMap
from scoreanim.render.export import AnimationInputs
from scoreanim.render.scene import ScoreScenes
from scoreanim.ui.app_state import AppState
from scoreanim.ui.break_action import BreakActionController
from scoreanim.ui.delete_action import DeleteActionController
from scoreanim.ui.stem_flip_action import StemFlipActionController
from scoreanim.ui.document_sync import DocumentSync
from scoreanim.ui.file_actions import FileActions
from scoreanim.ui.inspector import Inspector
from scoreanim.ui.layout_zone import LayoutZone
from scoreanim.ui.menus import MainMenus
from scoreanim.ui.nudge import NudgeController
from scoreanim.ui.parts_menu import PartsMenu
from scoreanim.ui.peaks_worker import PeakExtractor
from scoreanim.ui.playback import PlaybackController
from scoreanim.ui.score_install import ScoreInstaller
from scoreanim.ui.score_loader import ScoreLoader
from scoreanim.ui.selection import SelectionController
from scoreanim.ui.stage_view import StageView
from scoreanim.ui.text_edit import InlineTextEditor
from scoreanim.ui.transport import LowerZone
from scoreanim.ui.view_router import ViewRouter
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
        self.animation_inputs: AnimationInputs | None = None

        self.app_state = AppState(self)
        self.playback = PlaybackController(self)
        self.peaks = PeakExtractor(self)

        # stage central and alone; the timeline area is the lower-zone
        # bottom dock (M1.3) — the dock cannot swallow the central widget,
        # which carries over the old splitter's collapsible=False guarantee
        self.view = StageView()
        self.setCentralWidget(self.view)
        self.lower_zone = LowerZone(self.app_state, self.playback, self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                           self.lower_zone)
        # right-hand inspector (M1.4): Follow/Systems, floor + Sweep,
        # Selection placeholder; resynced in _on_document_changed
        self.inspector = Inspector(self.app_state, self.playback, self,
                                   settings=self._settings)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.inspector)

        self.peaks.progress.connect(
            lambda: self.app_state.set_peaks(self.peaks.cache))
        self.peaks.finished.connect(
            lambda: self.app_state.set_peaks(self.peaks.cache))
        # The animation reads the peaks only once the whole file is
        # decoded, unlike the waveform, which draws every partial
        # snapshot. A half-decoded file gives a loudness reference that
        # is simply wrong and moves on every tick, and each move would
        # cost a full re-apply over every trigger. Decoding is fast
        # (~0.03 s for 35 s), so nothing waits on this in practice.
        self.peaks.finished.connect(
            lambda: self.playback.set_peaks(self.peaks.cache))
        # file/project/export menu handlers + file-session state (M1.9
        # split); connects peaks.failed itself
        self.files = FileActions(self)

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

        # click-to-select (M2.3): the view detects the gesture, the
        # controller resolves it against the pure policy and owns the
        # highlight overlay; _install rebinds it per load
        self.selection = SelectionController(self.app_state, self)
        self.view.clicked.connect(self.selection.select_at)   # (pos, scene)
        self.view.deselect_requested.connect(self.selection.clear)
        # in-place text editing (M3.1) — its own hit path, not the
        # selection's (D5 stands); also owns the Texts… dialog, whose
        # data is the engraved layout (BACKLOG 9b's fourth opener)
        self.text_edit = InlineTextEditor(self.app_state, self.view, self)
        self.view.double_clicked.connect(self.text_edit.edit_at)
        # drag-to-nudge (M3.2): the view asks the probe at press time
        # whether this press moves an element or pans, so the pan is
        # untouched everywhere else
        self.nudge = NudgeController(self.app_state, self)
        self.view.nudge_probe = self.nudge.probe
        self.view.drag_started.connect(self.nudge.start)
        self.view.drag_moved.connect(self.nudge.move)
        self.view.drag_finished.connect(self.nudge.finish)
        self.view.nudge_key.connect(self.nudge.nudge_by)

        # break authoring (M5.4, M5.7, M6.5): the controller owns the
        # three QActions and keeps the policy out of the menu builder;
        # the layout zone (M6.6, BACKLOG 17) is a LEFT dock over those
        # SAME action objects, so the two surfaces cannot diverge. Both
        # are built BEFORE the chrome, because the View menu picks up the
        # zone's toggleViewAction with the other two docks' and the Score
        # menu re-inserts the actions per load.
        self.break_action = BreakActionController(self.app_state, self)
        # delete = hide the selected object (restorable from the layout
        # zone). Its shortcut is added to the VIEW, not the window: the
        # tempo lane already owns Delete/Backspace for its points, and a
        # window-level shortcut would eat them (see delete_action.py)
        self.delete_action = DeleteActionController(self.app_state, self)
        self.view.addAction(self.delete_action.action)
        # F flips the selected note's stem. Stage-scoped for the same
        # reason and one more: F is a BARE LETTER, so window-level it
        # would eat the "f" out of every text field in the app.
        self.stem_flip_action = StemFlipActionController(self.app_state, self)
        self.view.addAction(self.stem_flip_action.action)
        self.layout_zone = LayoutZone(self.app_state,
                                      self.break_action.actions, self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,
                           self.layout_zone)
        # static chrome (M1.5): the five menus, the slim toolbar, and
        # window-level shortcut registration; the window keeps the refs
        # it mutates (undo text, enable-on-load, page readout)
        self.menus = MainMenus(self)
        # presentation routing (M3.0): page/system state and the
        # prev/next/follow/mode paths; needs the chrome for its readout,
        # so it is built after the menus and the two follow signals
        # connect here rather than above
        self.router = ViewRouter(self.view, self.menus)
        # follow reports page AND system; the router picks by the
        # document's presentation mode (Phase 7.4)
        self.playback.page_changed.connect(self.router.on_page_followed)
        self.playback.system_changed.connect(self.router.on_system_followed)
        # dynamic Score-menu content (M1.6): rebuilt per load; check
        # state re-derived from the document by the sync passes below.
        # Owns the three part-shaped dialogs too since M3.0 (BACKLOG 9b)
        self.parts_menu = PartsMenu(self.menus.score_menu, self.app_state,
                                    self)
        # the Score menu is cleared per load, so the break actions are
        # handed to its builder to re-insert; the shortcuts are
        # registered window-level so they fire regardless of focus
        self.parts_menu.set_break_actions(*self.break_action.actions)
        for action in self.break_action.actions:
            self.addAction(action)
        # load pipeline + document→scene diff-sync (M1.7): the loader
        # returns a LoadedScore bundle the installer adopts
        # (ui/score_install.py); the sync owns the applied caches the
        # document-changed pass diffs against
        self.loader = ScoreLoader()
        self.installer = ScoreInstaller(self)
        self.doc_sync = DocumentSync(self.parts_menu)

        # overlay preview (2026-08-06): view state from the canvas
        # panel — the window holds both halves (the scenes' paper rects
        # and the view's fill) and re-applies them per load, because a
        # load adopts fresh scenes with their paper visible.
        self._overlay_preview: tuple[bool, object] = (False, None)
        self.inspector.video_canvas_panel.preview_changed.connect(
            self._set_overlay_preview)
        self.inspector.video_canvas_panel.restore_preview()

        # shell layout (M1.8): restore once docks + toolbar exist; a
        # fresh store yields the first-run default size. UI state only —
        # nothing document-derived lives in the settings (rule 5).
        restore_window_state(self, self.inspector.sections, self._settings)

        if score_path is not None:
            self.files.open_score(score_path)

    # -- playback feedback -----------------------------------------------------

    def _on_time(self, audio_seconds: float, duration: float) -> None:
        # slider + time label feedback lives on the transport strip
        # (M1.3); the window keeps the playhead push to the shared axis
        self.app_state.set_playhead(audio_seconds)

    # -- document → world -------------------------------------------------------

    def timing_config(self, doc: ProjectDoc) -> tuple[float, TempoMap, tuple]:
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
            try:
                self.installer.reengrave(doc,
                                         self.installer.break_anchor(doc))
            except Exception as exc:
                # An engraving failure is NOT a CommandError, so
                # AppState.execute never sees it and it would otherwise
                # escape this slot silently — the edit lands in the
                # document and the score just never redraws (the 2026-07-29
                # bracket report). Say so, and keep the last good render
                # until the next successful re-engrave.
                traceback.print_exc()
                self.app_state.status.emit(f"re-engrave failed: {exc}")
        self.playback.set_timing_config(*self.timing_config(doc))
        self.doc_sync.sync_styles(doc)
        if self.doc_sync.sync_stage(doc) \
                and self.animation_inputs is not None:
            # a stage-text edit must reach export too — inputs.stage is
            # otherwise a load-time snapshot (Phase 7 staleness gotcha)
            self.animation_inputs = _dc_replace(self.animation_inputs,
                                                stage=doc.stage)
        self.doc_sync.sync_hidden(doc)
        self.doc_sync.sync_offsets(doc)
        self.playback.set_style(doc.style)
        self.lower_zone.bar.sync_from_document(doc)
        self.inspector.sync_from_document(doc)
        self.layout_zone.sync_from_document(doc)
        self.parts_menu.sync_from_document(doc)
        self.break_action.sync()      # overrides move the action's label
        self.delete_action.sync()     # a delete disables its own action
        self.stem_flip_action.sync()  # a flip re-engraves under its own tip
        self.router.sync_presentation_mode(doc.stage.mode)
        self.router.sync_canvas(doc.stage.canvas)
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
        name = self.files.score_name
        self.setWindowTitle(f"ScoreAnim — {name}{star}" if name
                            else "ScoreAnim")

    # -- score / project --------------------------------------------------------

    def load_score(self, *args, **kwargs) -> StageConfig:
        """Fresh-load entry (ui/score_install.py owns the pipeline)."""
        return self.installer.load_score(*args, **kwargs)

    # -- overlay preview (view state, never the document) -----------------------

    def _set_overlay_preview(self, active: bool, color) -> None:
        """The panel's preview state: remember it and apply it. Never
        the document, never export (ruling R1)."""
        self._overlay_preview = (active, color)
        self.apply_overlay_preview()

    def apply_overlay_preview(self) -> None:
        """Apply the remembered state — called again by the installer
        after every load, because fresh scenes rebuild their paper
        rects visible."""
        active, color = self._overlay_preview
        if self._scenes is not None:
            self._scenes.set_page_background_visible(not active)
        if color is not None:
            self.view.set_overlay_preview(active, color)

    # -- close ---------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.app_state.is_dirty:
            answer = QMessageBox.question(
                self, "Unsaved changes", "Save project before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Save:
                if not self.files.save_project():
                    event.ignore()
                    return
            elif answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        # accepted close only — a cancelled close saves nothing (M1.8)
        save_window_state(self, self.inspector.sections, self._settings)
        event.accept()
