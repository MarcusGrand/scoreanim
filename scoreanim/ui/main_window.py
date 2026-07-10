"""Minimal Phase 2 app shell: open a score, flip pages, zoom/pan, tint
parts (the per-element addressability demo). No playback, no editing —
static paged display only."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QMenu

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio_adapter import VerovioEngravingProvider
from scoreanim.core.project.stage_config import (default_stage_config,
                                                 page_content_top)
from scoreanim.core.score.identity import PartId
from scoreanim.render.scene import ScoreScenes
from scoreanim.ui.stage_view import StageView

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
        self._build_actions()

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

    def _open_dialog(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Open MusicXML score", "",
            "MusicXML (*.musicxml *.xml);;All files (*)")
        if name:
            self.open_score(Path(name))

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
            f"{len(self._scenes.items)} elements on "
            f"{self._scenes.page_count} pages")
        self.show_page(1)
        self.view.fit()

    def show_page(self, page: int) -> None:
        if self._scenes is None:
            return
        self._page = max(1, min(page, self._scenes.page_count))
        self.view.show_scene(self._scenes.scene_for_page(self._page))
        self._page_label.setText(f" {self._page}/{self._scenes.page_count} ")
        self._prev.setEnabled(self._page > 1)
        self._next.setEnabled(self._page < self._scenes.page_count)
