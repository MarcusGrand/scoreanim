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

import sys
import time
from dataclasses import replace as _dc_replace
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (QAction, QActionGroup, QColor, QIcon,
                           QKeySequence, QPixmap)
from PySide6.QtWidgets import (QColorDialog, QDoubleSpinBox, QFileDialog,
                               QLabel, QMainWindow, QMenu, QMessageBox,
                               QSlider, QSplitter, QToolBar)

from scoreanim.core.animation import (DEFAULT_EFFECT, FLOOR_OPACITY, PRESETS,
                                      RevealMode, build_reveal_tracks,
                                      build_trigger_schedule,
                                      takes_part_color)
from scoreanim.core.engraving.systems import system_bands
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.project import (DEFAULT_BPM,
                                    HIDE_EMPTY_STAVES_DEFAULT, SUFFIX,
                                    ApplyTaps, FileRef,
                                    ImportTempoSetup, MoveTempoEvent,
                                    PresentationMode,
                                    ProjectDoc,
                                    SetFloorOpacity, SetGlobalSwing,
                                    SetHideEmptyStaves,
                                    SetOffset, SetPartColor,
                                    SetPartEffect, SetPresentationMode,
                                    SetRevealMode,
                                    StageConfig, check_ref,
                                    default_stage_config, load_project,
                                    page_content_top, sha256_of)
from scoreanim.core.project import save_project as write_project_file
from scoreanim.core.score.identity import PartId
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.musicxml_prep import (PartCondenseSpec,
                                                PartGroupSpec, PartTextSpec)
from scoreanim.core.score.model import build_score_model
from scoreanim.core.timing import (TempoEvent, TempoMap, parse_tempo_file,
                                   resolve_seconds)
from scoreanim.core.timing.taps import (TapSession, derive_tempo_events,
                                        start_residual)
from scoreanim.render.animate import AnimationApplier
from scoreanim.render.export import AnimationInputs
from scoreanim.render.scene import ScoreScenes
from scoreanim.ui.app_state import AppState
from scoreanim.ui.export_dialog import ExportDialog
from scoreanim.ui.peaks_worker import PeakExtractor
from scoreanim.ui.playback import PlaybackController
from scoreanim.ui.part_names_dialog import PartNamesDialog
from scoreanim.ui.score_setup_dialog import ScoreSetupDialog
from scoreanim.ui.staff_groups_dialog import StaffGroupsDialog
from scoreanim.ui.stage_view import StageView
from scoreanim.ui.texts_dialog import TextsDialog
from scoreanim.ui.taps import TapRecorder
from scoreanim.ui.tempo_lane import TempoLaneView
from scoreanim.ui.waveform import WaveformView

# FLOOR_OPACITY moved to core/animation/presets.py in Phase 5.3 (the
# ghost floor is preset data, not UI policy); imported above for the
# spanner-ghost layers.

# Part-color swatch palette for the Parts menu (Custom… covers the rest).
_PART_COLORS = ["#cc2222", "#1a7a2e", "#1c4fd6", "#b26b00",
                "#8422b8", "#0b7f7f", "#c22276"]


class MainWindow(QMainWindow):
    def __init__(self, score_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("ScoreAnim")
        self.resize(1000, 1200)

        self._scenes: ScoreScenes | None = None
        self._animation_inputs: AnimationInputs | None = None
        self._applier: AnimationApplier | None = None
        self._export_settings: dict | None = None    # session memory (R3)
        self._page = 1
        self._page_label = QLabel("–/–")
        self._system = 1
        self._band_by_system: dict = {}              # derived, never saved
        self._applied_mode = PresentationMode.PAGED  # what the view shows
        self._applied_groups: tuple = ()   # staff groups the engrave used
        self._applied_text_overrides: dict = {}   # label overrides ditto
        self._applied_hide_empty = False   # hide-empty-staves ditto
        self._applied_condense: tuple = ()   # condense groups ditto
        self._last_overflow = False          # last load overflowed a page
        self._hide_staves_action: QAction | None = None
        self._applied_stage_texts: tuple = ()   # stage texts on the scenes
        self._applied_hidden: dict = {}    # ElementId → applied hidden flag
        self._parts: tuple = ()            # PartInfos of the loaded score
        self._score_name: str | None = None
        self._project_path: Path | None = None
        self._tempo_path: Path | None = None
        self._applied_colors: dict[PartId, str | None] = {}
        self._applied_overrides: dict = {}     # ElementId → applied color
        self._applied_floor = FLOOR_OPACITY    # ghost opacity on the scenes
        self._part_color_actions: dict[PartId, dict] = {}
        self._part_effect_actions: dict[PartId, dict] = {}

        self.app_state = AppState(self)
        self.playback = PlaybackController(self)
        self.peaks = PeakExtractor(self)
        self.tap_recorder = TapRecorder(self.app_state,
                                        self.playback.transport, self)
        self.tap_recorder.status.connect(
            lambda msg: self.statusBar().showMessage(msg))
        self.tap_recorder.session_finished.connect(self._on_tap_session)

        # stage above, timeline views below, one splitter (ARCHITECTURE §7)
        self.view = StageView()
        self.waveform = WaveformView(self.app_state)
        self.tempo_lane = TempoLaneView(self.app_state)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.view)
        splitter.addWidget(self.waveform)
        splitter.addWidget(self.tempo_lane)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 0)
        splitter.setCollapsible(0, False)
        self.setCentralWidget(splitter)

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
        # play-state and duration come from the CONTROLLER, not the audio
        # wrapper, so no-audio playback (FIX 2) drives the same UI paths
        self.playback.playing_changed.connect(self._on_playing)
        self.playback.duration_changed.connect(
            self.app_state.axis.set_duration)

        self.app_state.seek_requested.connect(self.playback.seek)
        self.app_state.document_changed.connect(self._on_document_changed)
        self.app_state.status.connect(
            lambda msg: self.statusBar().showMessage(msg))

        self._build_actions()
        self._build_transport_bar()

        if score_path is not None:
            self.open_score(score_path)

    # -- chrome --------------------------------------------------------------

    def _build_actions(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)

        open_action = QAction("Open Score…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_dialog)

        open_project_action = QAction("Open Project…", self)
        open_project_action.setShortcut("Ctrl+Shift+O")
        open_project_action.triggered.connect(self._open_project_dialog)

        save_action = QAction("Save Project", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_project)

        save_as_action = QAction("Save Project As…", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_project_as)

        self._export_action = QAction("Export Video…", self)
        self._export_action.setShortcut("Ctrl+E")
        self._export_action.setEnabled(False)        # needs a loaded score
        self._export_action.triggered.connect(self._open_export_dialog)

        # prev/next step the presentation unit: pages in paged mode,
        # systems in system mode
        self._prev = QAction("◀", self)
        self._prev.setShortcut(QKeySequence.StandardKey.MoveToPreviousPage)
        self._prev.triggered.connect(lambda: self._step(-1))
        self._next = QAction("▶", self)
        self._next.setShortcut(QKeySequence.StandardKey.MoveToNextPage)
        self._next.triggered.connect(lambda: self._step(+1))

        fit = QAction("Fit", self)
        fit.setShortcut("Ctrl+0")
        fit.triggered.connect(self.view.fit)

        toolbar.addAction(open_action)
        toolbar.addSeparator()
        toolbar.addAction(self._prev)
        toolbar.addWidget(self._page_label)
        toolbar.addAction(self._next)
        toolbar.addSeparator()
        toolbar.addAction(fit)

        self._undo = QAction("Undo", self)
        self._undo.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo.setEnabled(False)
        self._undo.triggered.connect(self.app_state.undo)
        self._redo = QAction("Redo", self)
        self._redo.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo.setEnabled(False)
        self._redo.triggered.connect(self.app_state.redo)

        self._parts_menu = QMenu("&Parts", self)
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(open_action)
        file_menu.addAction(open_project_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self._export_action)
        self._texts_action = QAction("Texts…", self)
        self._texts_action.setEnabled(False)         # needs a loaded score
        self._texts_action.triggered.connect(self._open_texts_dialog)

        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self._undo)
        edit_menu.addAction(self._redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self._texts_action)
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(fit)
        view_menu.addAction(self._prev)
        view_menu.addAction(self._next)
        menubar.addMenu(self._parts_menu)
        # window-level so shortcuts fire regardless of focus
        self.addAction(self._undo)
        self.addAction(self._redo)
        self.addAction(save_action)

    def _build_transport_bar(self) -> None:
        bar = QToolBar("Transport")
        bar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, bar)

        open_audio = QAction("Open Audio…", self)
        open_audio.triggered.connect(self._open_audio_dialog)
        open_tempo = QAction("Import Tempo…", self)
        open_tempo.triggered.connect(self._open_tempo_dialog)
        reload_tempo = QAction("Reload Tempo", self)
        reload_tempo.setShortcut("F5")
        reload_tempo.triggered.connect(self._reload_tempo)

        self._play = QAction("▶ Play", self)
        self._play.setShortcut(Qt.Key.Key_Space)
        self._play.triggered.connect(self.playback.toggle_play)

        self._follow = QAction("Follow", self)
        self._follow.setCheckable(True)
        self._follow.setChecked(True)
        self._follow.toggled.connect(self.playback.set_follow)

        # PresentationMode toggle (Phase 7.4): checked = one system at a
        # time. Document intent → command, like Sweep.
        self._systems_mode = QAction("Systems", self)
        self._systems_mode.setCheckable(True)
        self._systems_mode.setToolTip("Stage one system at a time; "
                                      "unchecked shows whole pages")
        self._systems_mode.toggled.connect(
            lambda checked: self.app_state.execute(SetPresentationMode(
                PresentationMode.SYSTEM if checked
                else PresentationMode.PAGED)))

        # RevealMode toggle: checked = CONTINUOUS sweep, unchecked =
        # STEPPED (jumps at musical onsets). Document intent → command.
        self._sweep = QAction("Sweep", self)
        self._sweep.setCheckable(True)
        self._sweep.setToolTip("Continuous reveal sweep; unchecked steps "
                               "at musical onsets")
        self._sweep.toggled.connect(
            lambda checked: self.app_state.execute(SetRevealMode(
                RevealMode.CONTINUOUS if checked else RevealMode.STEPPED)))

        self._arm_taps = QAction("● Arm Taps", self)
        self._arm_taps.setCheckable(True)
        self._arm_taps.setShortcut("Shift+T")
        self._arm_taps.toggled.connect(self.tap_recorder.set_armed)
        tap_action = QAction("Tap", self)
        tap_action.setShortcut("T")
        tap_action.setAutoRepeat(False)
        tap_action.triggered.connect(self.tap_recorder.tap)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setSingleStep(100)        # ms
        self._slider.setPageStep(2000)
        self._slider.sliderMoved.connect(
            lambda ms: self.playback.seek(ms / 1000.0))
        self._slider.valueChanged.connect(self._on_slider_value)
        self._time_label = QLabel(" 0:00.0 / 0:00.0 ")

        # initial tempo (FIX 2): edits the beat-0 tempo event through the
        # existing tempo-map machinery (MoveTempoEvent) — not a parallel
        # path. With no audio it sets the no-audio playback pace; the
        # offset is simply 0 then.
        self._bpm_spin = QDoubleSpinBox()
        self._bpm_spin.setPrefix("bpm ")
        self._bpm_spin.setDecimals(1)
        self._bpm_spin.setSingleStep(1.0)
        self._bpm_spin.setRange(20.0, 400.0)
        self._bpm_spin.setKeyboardTracking(False)
        self._bpm_spin.setToolTip("Initial tempo — drives no-audio "
                                  "playback and the tempo map")
        self._bpm_spin.editingFinished.connect(self._commit_bpm)

        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setPrefix("offset ")
        self._offset_spin.setSuffix(" s")
        self._offset_spin.setDecimals(2)
        self._offset_spin.setSingleStep(0.05)
        self._offset_spin.setRange(-60.0, 3600.0)
        self._offset_spin.setKeyboardTracking(False)
        self._offset_spin.editingFinished.connect(self._commit_offset)

        # global swing ratio (ruling 2026-07-11): 0.50 straight … 0.67
        # triplet, one value for the whole piece; regions later (BACKLOG 7)
        self._swing_spin = QDoubleSpinBox()
        self._swing_spin.setPrefix("swing ")
        self._swing_spin.setDecimals(2)
        self._swing_spin.setSingleStep(0.01)
        self._swing_spin.setRange(0.50, 0.75)
        self._swing_spin.setKeyboardTracking(False)
        self._swing_spin.editingFinished.connect(self._commit_swing)

        # ghost floor (Phase 7.2): document intent, 0 allowed — scaffold
        # stays visible, unrevealed animated ink goes fully invisible
        self._floor_spin = QDoubleSpinBox()
        self._floor_spin.setPrefix("floor ")
        self._floor_spin.setDecimals(2)
        self._floor_spin.setSingleStep(0.05)
        self._floor_spin.setRange(0.0, 1.0)
        self._floor_spin.setKeyboardTracking(False)
        self._floor_spin.editingFinished.connect(self._commit_floor)

        bar.addAction(open_audio)
        bar.addAction(open_tempo)
        bar.addAction(reload_tempo)
        bar.addSeparator()
        bar.addAction(self._play)
        bar.addWidget(self._slider)
        bar.addWidget(self._time_label)
        bar.addWidget(self._bpm_spin)
        bar.addWidget(self._offset_spin)
        bar.addWidget(self._swing_spin)
        bar.addWidget(self._floor_spin)
        bar.addAction(self._sweep)
        bar.addAction(self._arm_taps)
        bar.addAction(self._follow)
        bar.addAction(self._systems_mode)
        # window-level so shortcuts fire regardless of focus
        self.addAction(self._play)
        self.addAction(reload_tempo)
        self.addAction(self._arm_taps)
        self.addAction(tap_action)

    def _open_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Open MusicXML score", "",
            "MusicXML (*.musicxml *.xml);;All files (*)")
        if name:
            self.open_score(Path(name))

    def _open_project_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Open project", "",
            f"ScoreAnim projects (*{SUFFIX});;All files (*)")
        if name:
            self.open_project(Path(name))

    def _open_audio_dialog(self) -> None:
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

    def _open_tempo_dialog(self) -> None:
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

    def _reload_tempo(self) -> None:
        if self._tempo_path is None:
            QMessageBox.warning(self, "Tempo file",
                                "no tempo file imported (Import Tempo… first)")
            return
        self._import_tempo(self._tempo_path)

    # -- playback feedback -----------------------------------------------------

    def _on_time(self, audio_seconds: float, duration: float) -> None:
        def fmt(s: float) -> str:
            s = max(0.0, s)
            return f"{int(s // 60)}:{int(s % 60):02d}.{int(s * 10 % 10)}"
        self._time_label.setText(f" {fmt(audio_seconds)} / {fmt(duration)} ")
        if not self._slider.isSliderDown():
            self._slider.blockSignals(True)
            self._slider.setRange(0, int(duration * 1000))
            self._slider.setValue(int(audio_seconds * 1000))
            self._slider.blockSignals(False)
        self.app_state.set_playhead(audio_seconds)

    def _on_slider_value(self, ms: int) -> None:
        # keyboard/page-step changes (sliderMoved covers drags)
        if not self._slider.isSliderDown():
            self.playback.seek(ms / 1000.0)

    def _on_playing(self, playing: bool) -> None:
        self._play.setText("⏸ Pause" if playing else "▶ Play")
        if not playing and self.tap_recorder.armed:
            self._arm_taps.setChecked(False)     # pause ends the session

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
        # staff groups and part-label overrides are engraving inputs: a
        # change (execute, undo, OR redo — all arrive here) re-derives
        # the engraved world FIRST, so the sync below re-pushes
        # timing/tints/floor/stage/hidden onto the fresh scenes in the
        # same pass. The diff keeps every other command at its current
        # cost.
        if (self._scenes is not None and doc.score is not None
                and (doc.staff_groups != self._applied_groups
                     or dict(doc.text_overrides)
                     != self._applied_text_overrides
                     or doc.hide_empty_staves != self._applied_hide_empty
                     or doc.condense_groups != self._applied_condense)):
            self._reengrave(doc)
        self.playback.set_timing_config(*self._timing_config(doc))
        self._sync_styles(doc)
        self._sync_stage(doc)
        self._sync_hidden(doc)
        self.playback.set_style(doc.style)
        self._sweep.blockSignals(True)
        self._sweep.setChecked(doc.style.reveal_mode
                               is RevealMode.CONTINUOUS)
        self._sweep.blockSignals(False)
        self._offset_spin.blockSignals(True)
        self._offset_spin.setValue(doc.timing.offset_seconds)
        self._offset_spin.blockSignals(False)
        first_tempo = self._initial_tempo_event(doc)
        self._bpm_spin.blockSignals(True)
        self._bpm_spin.setValue(first_tempo.bpm if first_tempo
                                else DEFAULT_BPM)
        self._bpm_spin.blockSignals(False)
        self._swing_spin.blockSignals(True)
        self._swing_spin.setValue(self._global_swing_ratio(doc))
        self._swing_spin.blockSignals(False)
        self._floor_spin.blockSignals(True)
        self._floor_spin.setValue(doc.style.floor_opacity)
        self._floor_spin.blockSignals(False)
        self._systems_mode.blockSignals(True)
        self._systems_mode.setChecked(doc.stage.mode
                                      is PresentationMode.SYSTEM)
        self._systems_mode.blockSignals(False)
        if self._hide_staves_action is not None:
            self._hide_staves_action.blockSignals(True)
            self._hide_staves_action.setChecked(doc.hide_empty_staves)
            self._hide_staves_action.blockSignals(False)
        self._sync_presentation_mode(doc.stage.mode)
        undo_text = self.app_state.undo_text()
        redo_text = self.app_state.redo_text()
        self._undo.setEnabled(self.app_state.can_undo)
        self._undo.setText(f"Undo {undo_text}" if undo_text else "Undo")
        self._redo.setEnabled(self.app_state.can_redo)
        self._redo.setText(f"Redo {redo_text}" if redo_text else "Redo")
        self._sync_title()

    def _sync_stage(self, doc: ProjectDoc) -> None:
        """Diff the document's stage texts onto the scene (Phase 9.1).
        A text edit rebuilds just the stage-text layer — never a
        re-engrave — and refreshes the retained AnimationInputs so
        export follows the edit (inputs.stage is otherwise a load-time
        snapshot, the Phase 7 staleness gotcha)."""
        if self._scenes is None \
                or doc.stage.texts == self._applied_stage_texts:
            return
        self._scenes.set_stage_texts(doc.stage.texts)
        self._applied_stage_texts = doc.stage.texts
        if self._animation_inputs is not None:
            self._animation_inputs = _dc_replace(self._animation_inputs,
                                                 stage=doc.stage)

    def _sync_hidden(self, doc: ProjectDoc) -> None:
        """Diff LayoutOverride.hidden onto the scene (Phase 9.2: tempo
        overlays hide the engraved mark). Execute, undo, and redo all
        arrive here — hide and un-hide ride the same pass."""
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

    def _sync_styles(self, doc: ProjectDoc) -> None:
        """Diff the document's StyleRules onto the scene: part tints,
        then per-element color overrides on top (a part re-tint touches
        every item of the part, so overrides re-apply after it). The
        ghost floor rides along: the trigger-animated side updates via
        playback.set_style → applier re-resolve; the static spanner
        ghosts need this push."""
        if self._scenes is None:
            return
        if self._applied_floor != doc.style.floor_opacity:
            self._scenes.set_ghost_opacity(doc.style.floor_opacity)
            self._applied_floor = doc.style.floor_opacity
        parts_retinted = set()
        for pid in self._part_color_actions:
            rule = doc.style.parts.get(pid)
            color = rule.color if rule is not None else None
            if self._applied_colors.get(pid) != color:
                self._scenes.set_part_color(
                    pid, QColor(color) if color else None)
                self._applied_colors[pid] = color
                parts_retinted.add(pid)
            self._check_part_menu(pid, rule)

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

    def _check_part_menu(self, pid: PartId, rule) -> None:
        color = rule.color if rule is not None else None
        effect = rule.effect if rule is not None else None
        color_actions = self._part_color_actions.get(pid, {})
        for key, action in color_actions.items():
            action.blockSignals(True)
            if key == "custom":
                action.setChecked(color is not None
                                  and color not in color_actions)
            else:
                action.setChecked(color == key)
            action.blockSignals(False)
        effect_actions = self._part_effect_actions.get(pid, {})
        known = effect in effect_actions
        for key, action in effect_actions.items():
            action.blockSignals(True)
            action.setChecked(effect == key if known else key is None)
            action.blockSignals(False)

    def _build_parts_menu(self, parts) -> None:
        """One submenu per part: color swatches (palette + Custom… +
        No Color) and an effect radio group enumerated from the preset
        registry — adding a preset needs no menu code."""
        self._parts_menu.clear()
        self._part_color_actions = {}
        self._part_effect_actions = {}
        self._applied_colors = {}
        self._applied_overrides = {}
        setup_action = QAction("Score Setup…", self._parts_menu)
        setup_action.triggered.connect(self._open_score_setup_dialog)
        self._parts_menu.addAction(setup_action)
        groups_action = QAction("Staff Groups…", self._parts_menu)
        groups_action.triggered.connect(self._open_staff_groups_dialog)
        self._parts_menu.addAction(groups_action)
        names_action = QAction("Part Names…", self._parts_menu)
        names_action.triggered.connect(self._open_part_names_dialog)
        self._parts_menu.addAction(names_action)
        # an engraving input like the two above (Phase 10R): toggling
        # re-engraves via the _applied_hide_empty diff, one undo step
        self._hide_staves_action = QAction("Hide Empty Staves",
                                           self._parts_menu)
        self._hide_staves_action.setCheckable(True)
        self._hide_staves_action.setChecked(
            self.app_state.doc.hide_empty_staves)
        self._hide_staves_action.toggled.connect(
            lambda checked: self.app_state.execute(
                SetHideEmptyStaves(checked)))
        self._parts_menu.addAction(self._hide_staves_action)
        self._parts_menu.addSeparator()
        for info in parts:
            pid = PartId(info.part_id)
            menu = self._parts_menu.addMenu(info.name)

            color_group = QActionGroup(menu)
            color_actions: dict = {}
            for c in _PART_COLORS:
                action = QAction(c, menu)
                action.setCheckable(True)
                pm = QPixmap(12, 12)
                pm.fill(QColor(c))
                action.setIcon(QIcon(pm))
                action.triggered.connect(
                    lambda _=False, p=pid, col=c:
                    self.app_state.execute(SetPartColor(p, col)))
                color_group.addAction(action)
                menu.addAction(action)
                color_actions[c] = action
            custom = QAction("Custom…", menu)
            custom.setCheckable(True)
            custom.triggered.connect(
                lambda _=False, p=pid: self._pick_part_color(p))
            color_group.addAction(custom)
            menu.addAction(custom)
            color_actions["custom"] = custom
            no_color = QAction("No Color", menu)
            no_color.setCheckable(True)
            no_color.setChecked(True)
            no_color.triggered.connect(
                lambda _=False, p=pid:
                self.app_state.execute(SetPartColor(p, None)))
            color_group.addAction(no_color)
            menu.addAction(no_color)
            color_actions[None] = no_color
            self._part_color_actions[pid] = color_actions

            menu.addSeparator()
            effect_group = QActionGroup(menu)
            effect_actions: dict = {}
            default_action = QAction(f"Effect: {DEFAULT_EFFECT} (default)",
                                     menu)
            default_action.setCheckable(True)
            default_action.setChecked(True)
            default_action.triggered.connect(
                lambda _=False, p=pid:
                self.app_state.execute(SetPartEffect(p, None)))
            effect_group.addAction(default_action)
            menu.addAction(default_action)
            effect_actions[None] = default_action
            for name in sorted(PRESETS):
                if name == DEFAULT_EFFECT:
                    continue
                action = QAction(f"Effect: {name}", menu)
                action.setCheckable(True)
                action.triggered.connect(
                    lambda _=False, p=pid, n=name:
                    self.app_state.execute(SetPartEffect(p, n)))
                effect_group.addAction(action)
                menu.addAction(action)
                effect_actions[name] = action
            self._part_effect_actions[pid] = effect_actions

    def _pick_part_color(self, pid: PartId) -> None:
        rule = self.app_state.doc.style.parts.get(pid)
        initial = QColor(rule.color) if rule is not None and rule.color \
            else QColor(_PART_COLORS[0])
        color = QColorDialog.getColor(initial, self, "Part color")
        if color.isValid():
            self.app_state.execute(SetPartColor(pid, color.name()))
        else:                                  # cancelled: restore checks
            self._sync_styles(self.app_state.doc)

    def _sync_title(self) -> None:
        star = " *" if self.app_state.is_dirty else ""
        name = f" — {self._score_name}{star}" if self._score_name else ""
        self.setWindowTitle(f"ScoreAnim{name}")

    def _commit_offset(self) -> None:
        value = self._offset_spin.value()
        if abs(value - self.app_state.doc.timing.offset_seconds) > 1e-9:
            self.app_state.execute(SetOffset(value))

    @staticmethod
    def _initial_tempo_event(doc: ProjectDoc):
        events = doc.timing.tempo_events
        return min(events, key=lambda e: e.position) if events else None

    def _commit_bpm(self) -> None:
        """Set the initial (beat-0) tempo through the existing tempo-map
        machinery — MoveTempoEvent on the first event, so a tempo curve's
        later events survive. Drives no-audio playback (FIX 2)."""
        first = self._initial_tempo_event(self.app_state.doc)
        value = self._bpm_spin.value()
        if first is None or abs(value - first.bpm) < 1e-9:
            return
        self.app_state.execute(
            MoveTempoEvent(first.position, first.position, value))

    @staticmethod
    def _global_swing_ratio(doc: ProjectDoc) -> float:
        """v1 reads the single global region; a multi-region doc (from a
        later build or hand edit) shows its first ratio, and committing
        the spinbox collapses it to one global region."""
        regions = doc.timing.swing_regions
        return regions[0].ratio if regions else 0.5

    def _commit_swing(self) -> None:
        value = self._swing_spin.value()
        doc = self.app_state.doc
        if abs(value - self._global_swing_ratio(doc)) < 1e-9:
            return
        measures = self.app_state.measures
        if not measures:
            return
        end_beat = measures[-1].start + measures[-1].quarter_length
        self.app_state.execute(SetGlobalSwing(value, end_beat))

    def _commit_floor(self) -> None:
        value = self._floor_spin.value()
        if abs(value - self.app_state.doc.style.floor_opacity) < 1e-9:
            return
        self.app_state.execute(SetFloorOpacity(value))

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
                         condense_groups=doc.condense_groups)
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
                    condense_groups: tuple = ()
                    ) -> StageConfig:
        """Fresh-load entry: engrave + wire, then reset to page 1."""
        stage = self._engrave_and_wire(path, params, stage, groups,
                                       text_overrides or {},
                                       hide_empty_staves, condense_groups)
        self._page = 1
        self._system = 1
        return stage

    def _reengrave(self, doc: ProjectDoc) -> None:
        """Re-derive the engraved world after a staff-group, part-label,
        or hide-empty-staves change, preserving page/system/zoom (no
        view.fit, no position reset). ~0.6 s on the GUI thread per call
        (engrave + scene rebuild), so these commands must arrive via
        execute(), never preview()."""
        self._engrave_and_wire(Path(doc.score.path), doc.engraving,
                               doc.stage, doc.staff_groups,
                               doc.text_overrides, doc.hide_empty_staves,
                               doc.condense_groups)
        self._show_current()             # install the fresh scene

    def _engrave_and_wire(self, path: Path, params: EngravingParams,
                          stage: StageConfig | None,
                          groups: tuple = (),
                          text_overrides: dict | None = None,
                          hide_empty_staves: bool = False,
                          condense_groups: tuple = ()) -> StageConfig:
        """Engrave + decompose + join + wire the animation. Returns the
        stage config used (seeded from the score's credits when None).
        `groups` is doc.staff_groups — injected as <part-group> at the
        prep seam; `text_overrides` is doc.text_overrides — part labels
        rewritten there (Phase 9.3); `condense_groups` is
        doc.condense_groups — contiguous like parts merged onto one staff
        there (Phase 12.3); geometry re-derives, musical ids survive
        (rule 5, Phases 8/9/12)."""
        text_overrides = dict(text_overrides or {})
        specs = tuple(PartGroupSpec(parts=g.parts, symbol=g.symbol,
                                    join_barlines=g.join_barlines)
                      for g in groups)
        text_specs = tuple(PartTextSpec(part=pid, name=o.name,
                                        abbreviation=o.abbreviation)
                           for pid, o in sorted(text_overrides.items()))
        condense_specs = tuple(
            PartCondenseSpec(parts=g.parts, name=g.name,
                             abbreviation=g.abbreviation)
            for g in condense_groups)
        t0 = time.perf_counter()
        # strict=False (app path, Phase 11.4): an unknown drawable SVG
        # class degrades to a warned static element instead of failing the
        # open. The status bar shows the warning count.
        engraved = VerovioEngravingProvider().load_detailed(
            path, params, specs, text_specs, hide_empty_staves,
            condense_specs, strict=False)
        t1 = time.perf_counter()
        if stage is None:
            stage = default_stage_config(engraved.prepared,
                                         page_content_top(engraved.layout))
        # Constructed at the default; reset_document fires
        # _on_document_changed right after load, and _sync_styles
        # corrects the ghosts to a project-saved floor (same pattern as
        # the applier, built with the pre-reset style then set_style'd).
        self._scenes = ScoreScenes(engraved.layout, stage,
                                   ghost_opacity=FLOOR_OPACITY)
        self._applied_floor = FLOOR_OPACITY
        self._applied_stage_texts = stage.texts
        self._applied_hidden = {}    # fresh scenes: the post-engrave sync
                                     # pass re-applies doc hidden flags
        t2 = time.perf_counter()

        model = build_score_model(engraved.prepared, engraved.timeline)
        report = join_notes(model, engraved.note_records)
        join_note = ""
        if not report.is_complete:
            join_note = (f" · JOIN INCOMPLETE ({len(report.unmatched_score)}"
                         f"/{len(report.unmatched_layout)} unmatched)")
        if engraved.warnings:
            # flag-and-continue (Phase 10 ruling b): e.g. ties the
            # engraver dropped — the score loads, the anomaly is visible
            join_note += f" · {len(engraved.warnings)} load warning(s)"
            for w in engraved.warnings:
                print(f"load warning [{w.code}]: {w.message}",
                      file=sys.stderr)
        schedule = build_trigger_schedule(engraved.layout, report.mapping,
                                          model.measures)
        score_end = max((m.start + m.quarter_length for m in model.measures),
                        default=0.0)
        reveal_tracks = build_reveal_tracks(engraved.layout, schedule,
                                            score_end)
        # retained for export: the private export scenes+applier build
        # from the SAME inputs as the live ones (render/export.py)
        self._animation_inputs = AnimationInputs(
            engraved.layout, stage, schedule, tuple(reveal_tracks))
        self._export_action.setEnabled(True)
        self._texts_action.setEnabled(True)
        applier = AnimationApplier(self._scenes.items, schedule,
                                   TempoMap([TempoEvent(0.0, DEFAULT_BPM)]),
                                   self.app_state.doc.style, reveal_tracks)
        self._applier = applier
        self.playback.set_animation(applier, model.measures)
        # per-system band rects for system-at-a-time framing (Phase 7.4)
        # — derived from the Layout, never persisted (rule 5)
        self._band_by_system = {b.system: b
                                for b in system_bands(engraved.layout)}
        self.app_state.set_measures(model.measures)
        t3 = time.perf_counter()

        self._parts = engraved.prepared.parts
        self._build_parts_menu(engraved.prepared.parts)
        self._applied_groups = groups
        self._applied_text_overrides = text_overrides
        self._applied_hide_empty = hide_empty_staves
        self._applied_condense = condense_groups
        # a system still overflowing its page after repagination means the
        # score needs staff-count reduction — the Score Setup trigger (12.4)
        self._last_overflow = any(w.code == "system-overflow"
                                  for w in engraved.warnings)

        self.statusBar().showMessage(
            f"engrave+decompose {t1 - t0:.2f}s · scene build {t2 - t1:.2f}s · "
            f"animation prep {t3 - t2:.2f}s · "
            f"{len(self._scenes.items)} elements on "
            f"{self._scenes.page_count} pages{join_note}")
        return stage

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

    def _open_texts_dialog(self) -> None:
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

    def _open_export_dialog(self) -> None:
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
        event.accept()

    def show_page(self, page: int) -> None:
        if self._scenes is None:
            return
        self._page = max(1, min(page, self._scenes.page_count))
        self.view.show_scene(self._scenes.scene_for_page(self._page))
        self._page_label.setText(f" {self._page}/{self._scenes.page_count} ")
        self._prev.setEnabled(self._page > 1)
        self._next.setEnabled(self._page < self._scenes.page_count)

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
        self._page_label.setText(
            f" sys {self._system}/{len(self._band_by_system)} ")
        self._prev.setEnabled(self._system > 1)
        self._next.setEnabled(self._system < len(self._band_by_system))

    def _step(self, delta: int) -> None:
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
