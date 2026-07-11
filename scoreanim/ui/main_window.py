"""App shell: open a score, flip pages, zoom/pan, tint parts, and (Phase
3) play a recording against it — notes at floor opacity going full at
onset, transport bar with seek, tempo sidecar, page follow."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QLabel, QMainWindow, QMenu,
                               QMessageBox, QSlider, QToolBar)

from scoreanim.core.animation import appear, build_trigger_schedule
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio_adapter import VerovioEngravingProvider
from scoreanim.core.project.stage_config import (default_stage_config,
                                                 page_content_top)
from scoreanim.core.score.identity import PartId
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.model import build_score_model
from scoreanim.core.timing import TempoEvent, TempoMap
from scoreanim.render.animate import AnimationApplier
from scoreanim.render.scene import ScoreScenes
from scoreanim.ui.playback import PlaybackController
from scoreanim.ui.stage_view import StageView

FLOOR_OPACITY = 0.3

# Demo tint palette, by part index (recolor-one-part, PHASES 2.1).
_PART_COLORS = ["#cc2222", "#1a7a2e", "#1c4fd6", "#b26b00",
                "#8422b8", "#0b7f7f", "#c22276"]


class MainWindow(QMainWindow):
    def __init__(self, score_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("ScoreAnim")
        self.resize(1000, 1200)
        self.view = StageView()
        self.setCentralWidget(self.view)

        self._scenes: ScoreScenes | None = None
        self._page = 1
        self._page_label = QLabel("–/–")

        self.playback = PlaybackController(self)
        self.playback.page_changed.connect(self.show_page)
        self.playback.status_message.connect(
            lambda msg: self.statusBar().showMessage(msg))
        self.playback.time_changed.connect(self._on_time)
        self.playback.transport.playing_changed.connect(self._on_playing)

        self._build_actions()
        self._build_transport_bar()

        if score_path is not None:
            self.open_score(score_path)

    # -- chrome --------------------------------------------------------------

    def _build_actions(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)

        open_action = QAction("Open…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_dialog)

        self._prev = QAction("◀", self)
        self._prev.setShortcut(QKeySequence.StandardKey.MoveToPreviousPage)
        self._prev.triggered.connect(lambda: self.show_page(self._page - 1))
        self._next = QAction("▶", self)
        self._next.setShortcut(QKeySequence.StandardKey.MoveToNextPage)
        self._next.triggered.connect(lambda: self.show_page(self._page + 1))

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

        self._parts_menu = QMenu("&Parts", self)
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(open_action)
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(fit)
        view_menu.addAction(self._prev)
        view_menu.addAction(self._next)
        menubar.addMenu(self._parts_menu)

    def _build_transport_bar(self) -> None:
        bar = QToolBar("Transport")
        bar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, bar)

        open_audio = QAction("Open Audio…", self)
        open_audio.triggered.connect(self._open_audio_dialog)
        open_tempo = QAction("Open Tempo…", self)
        open_tempo.triggered.connect(self._open_tempo_dialog)
        reload_tempo = QAction("Reload Tempo", self)
        reload_tempo.setShortcut("F5")
        reload_tempo.triggered.connect(
            lambda: self._tempo_result(self.playback.reload_tempo()))

        self._play = QAction("▶ Play", self)
        self._play.setShortcut(Qt.Key.Key_Space)
        self._play.triggered.connect(self.playback.toggle_play)

        self._follow = QAction("Follow", self)
        self._follow.setCheckable(True)
        self._follow.setChecked(True)
        self._follow.toggled.connect(self.playback.set_follow)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setSingleStep(100)        # ms
        self._slider.setPageStep(2000)
        self._slider.sliderMoved.connect(
            lambda ms: self.playback.seek(ms / 1000.0))
        self._slider.valueChanged.connect(self._on_slider_value)
        self._time_label = QLabel(" 0:00.0 / 0:00.0 ")

        bar.addAction(open_audio)
        bar.addAction(open_tempo)
        bar.addAction(reload_tempo)
        bar.addSeparator()
        bar.addAction(self._play)
        bar.addWidget(self._slider)
        bar.addWidget(self._time_label)
        bar.addAction(self._follow)
        # window-level so shortcuts fire regardless of focus
        self.addAction(self._play)
        self.addAction(reload_tempo)

    def _open_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Open MusicXML score", "",
            "MusicXML (*.musicxml *.xml);;All files (*)")
        if name:
            self.open_score(Path(name))

    def _open_audio_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Open recording", "",
            "Audio (*.wav *.mp3 *.m4a *.flac);;All files (*)")
        if name:
            self.playback.open_audio(Path(name))

    def _open_tempo_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Open tempo file", "",
            "Tempo files (*.tempo *.txt);;All files (*)")
        if name:
            self._tempo_result(self.playback.load_tempo(Path(name)))

    def _tempo_result(self, error: str | None) -> None:
        if error is not None:
            QMessageBox.warning(self, "Tempo file", error)

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

    def _on_slider_value(self, ms: int) -> None:
        # keyboard/page-step changes (sliderMoved covers drags)
        if not self._slider.isSliderDown():
            self.playback.seek(ms / 1000.0)

    def _on_playing(self, playing: bool) -> None:
        self._play.setText("⏸ Pause" if playing else "▶ Play")

    # -- score ---------------------------------------------------------------

    def open_score(self, path: Path) -> None:
        t0 = time.perf_counter()
        engraved = VerovioEngravingProvider().load_detailed(
            path, EngravingParams())
        t1 = time.perf_counter()
        stage = default_stage_config(engraved.prepared,
                                     page_content_top(engraved.layout))
        self._scenes = ScoreScenes(engraved.layout, stage)
        t2 = time.perf_counter()

        model = build_score_model(engraved.prepared)
        report = join_notes(model, engraved.note_records)
        join_note = ""
        if not report.is_complete:
            join_note = (f" · JOIN INCOMPLETE ({len(report.unmatched_score)}"
                         f"/{len(report.unmatched_layout)} unmatched)")
        schedule = build_trigger_schedule(engraved.layout, report.mapping)
        applier = AnimationApplier(self._scenes.items, schedule,
                                   TempoMap([TempoEvent(0.0, 120.0)]),
                                   appear(FLOOR_OPACITY))
        self.playback.set_animation(applier, model.measures)
        t3 = time.perf_counter()

        self._parts_menu.clear()
        for info in engraved.prepared.parts:
            action = QAction(info.name, self)
            action.setCheckable(True)
            color = _PART_COLORS[info.index % len(_PART_COLORS)]
            action.toggled.connect(
                lambda checked, pid=info.part_id, c=color:
                self._scenes.set_part_color(
                    PartId(pid), QColor(c) if checked else None))
            self._parts_menu.addAction(action)

        self.setWindowTitle(f"ScoreAnim — {path.name}")
        self.statusBar().showMessage(
            f"engrave+decompose {t1 - t0:.2f}s · scene build {t2 - t1:.2f}s · "
            f"animation prep {t3 - t2:.2f}s · "
            f"{len(self._scenes.items)} elements on "
            f"{self._scenes.page_count} pages{join_note}")
        self.show_page(1)
        self.view.fit()

        sidecar = path.with_suffix(".tempo")
        if sidecar.exists():
            self._tempo_result(self.playback.load_tempo(sidecar))

    def show_page(self, page: int) -> None:
        if self._scenes is None:
            return
        self._page = max(1, min(page, self._scenes.page_count))
        self.view.show_scene(self._scenes.scene_for_page(self._page))
        self._page_label.setText(f" {self._page}/{self._scenes.page_count} ")
        self._prev.setEnabled(self._page > 1)
        self._next.setEnabled(self._page < self._scenes.page_count)
