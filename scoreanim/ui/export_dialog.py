"""Export dialog: settings → chunked frame walk → encoder sink.

The long-running walk stays on the GUI thread, chunked: each batch
renders frames until a ~40 ms wall budget is spent, then re-arms with
QTimer.singleShot(0, …) so the event loop breathes between batches (the
modal dialog repaints, Cancel arrives) and a batch can never re-enter a
running batch. This matches the codebase's deliberate no-QThread style
(PeakExtractor is event-loop-driven the same way). Rendering and
encoding live in render/export.py and render/encode.py; core is
untouched.

Settings are session memory only (ruling R3): remembered() hands back a
dict the window passes into the next dialog. Nothing enters the project
document.
"""
from __future__ import annotations

import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QProgressBar, QPushButton,
                               QRadioButton, QSpinBox, QVBoxLayout)

from scoreanim.core.animation import StyleRules
from scoreanim.core.project.stage_config import PresentationMode
from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing import SwingRegion, TempoMap
from scoreanim.render.encode import (EncodeError, FrameSink,
                                     PngSequenceSink, ProResFfmpegSink,
                                     find_ffmpeg)
from scoreanim.render.export import (AnimationInputs, ExportFormat,
                                     ExportSpec, FrameRenderer, even_size,
                                     frame_count, measure_span_seconds)

_BATCH_BUDGET_S = 0.040
_FPS_CHOICES = (24, 25, 30, 50, 60)


class ExportDialog(QDialog):
    def __init__(self, inputs: AnimationInputs, style: StyleRules,
                 tempo_map: TempoMap, swing: tuple[SwingRegion, ...],
                 measures: tuple[MeasureInfo, ...],
                 offset_seconds: float, duration_seconds: float,
                 score_name: str,
                 mode: PresentationMode = PresentationMode.PAGED,
                 overrides: dict | None = None,
                 settings: dict | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Video")
        self._inputs = inputs
        self._style = style
        # document intent, read from the LIVE doc at dialog open (never
        # from inputs.stage — that is a load-time snapshot and goes
        # stale after a SetPresentationMode command)
        self._mode = mode
        # doc.layout_overrides, same live-at-open reasoning (Phase 9.2:
        # hidden tempo marks stay hidden in the export)
        self._overrides = dict(overrides or {})
        self._tempo_map = tempo_map
        self._swing = swing
        self._measures = tuple(measures)
        self._offset = offset_seconds
        self._duration = duration_seconds
        self._stem = Path(score_name).stem or "score"

        self._running = False
        self._cancel_requested = False
        self._renderer: FrameRenderer | None = None
        self._sink: FrameSink | None = None
        self._frame = 0
        self._recent: deque[tuple[int, float]] = deque(maxlen=50)

        self._build_ui()
        if settings:
            self._restore(settings)
        self._refresh_summary()

    # -- UI ---------------------------------------------------------------------

    def _build_ui(self) -> None:
        form = QFormLayout()

        self._fps = QComboBox()
        for fps in _FPS_CHOICES:
            self._fps.addItem(str(fps), fps)
        self._fps.setCurrentText("60")
        form.addRow("Frame rate:", self._fps)

        self._format = QComboBox()
        self._format.addItem("ProRes 4444 (.mov, alpha)",
                             ExportFormat.PRORES_4444)
        self._format.addItem("PNG sequence (alpha)",
                             ExportFormat.PNG_SEQUENCE)
        if find_ffmpeg() is None:
            self._format.model().item(0).setEnabled(False)
            self._format.setCurrentIndex(1)
            self._format.setToolTip("ProRes needs ffmpeg on PATH "
                                    "(brew install ffmpeg)")
        form.addRow("Format:", self._format)

        geo = self._inputs.layout.pages[0]
        self._page_aspect = (geo.width, geo.height)
        # both modes share the page-aspect canvas (Phase 10R ruling:
        # the frame never changes shape; system mode centers the single
        # system vertically inside it)
        self._height = QSpinBox()
        self._height.setRange(240, 4320)
        self._height.setSingleStep(2)
        self._height.setValue(2160)
        self._height.setSuffix(" px high")
        # aspect is the page's own and stays locked: width follows
        # the height, the 🔗 makes the coupling visible
        self._width_label = QLabel()
        size_row = QHBoxLayout()
        size_row.addWidget(self._height)
        size_row.addWidget(QLabel("🔗"))
        size_row.addWidget(self._width_label)
        size_row.addStretch(1)
        form.addRow("Size:", size_row)

        self._whole = QRadioButton(
            f"Whole recording ({self._duration:.2f} s)")
        self._whole.setChecked(True)
        self._span = QRadioButton("Measures:")
        numbers = [m.number for m in self._measures]
        self._span_from = QSpinBox()
        self._span_to = QSpinBox()
        for spin, value in ((self._span_from, numbers[0]),
                            (self._span_to, numbers[-1])):
            spin.setRange(numbers[0], numbers[-1])
            spin.setPrefix("m")
            spin.setValue(value)
            spin.setEnabled(False)
        span_row = QHBoxLayout()
        span_row.addWidget(self._span)
        span_row.addWidget(self._span_from)
        span_row.addWidget(QLabel("to"))
        span_row.addWidget(self._span_to)
        form.addRow("Range:", self._whole)
        form.addRow("", span_row)

        self._path = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self._path)
        path_row.addWidget(browse)
        form.addRow("Output:", path_row)

        self._summary = QLabel()
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._status = QLabel("")
        self._export_btn = QPushButton("Export")
        self._export_btn.setDefault(True)
        self._export_btn.clicked.connect(self._start)
        self._cancel_btn = QPushButton("Close")
        self._cancel_btn.clicked.connect(self._cancel_or_close)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._export_btn)
        buttons.addWidget(self._cancel_btn)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self._summary)
        root.addWidget(self._progress)
        root.addWidget(self._status)
        root.addLayout(buttons)

        self._span.toggled.connect(self._on_span_toggled)
        self._fps.currentIndexChanged.connect(self._refresh_summary)
        self._format.currentIndexChanged.connect(self._on_format_changed)
        for spin in self._size_widgets():
            spin.valueChanged.connect(self._refresh_summary)
        self._span_from.valueChanged.connect(self._refresh_summary)
        self._span_to.valueChanged.connect(self._refresh_summary)
        self._on_format_changed()

    def _size_widgets(self) -> tuple[QSpinBox, ...]:
        return (self._height,)

    def _output_size(self) -> tuple[int, int]:
        """Pixel size the current settings produce (evened, like the
        renderer will) — page aspect in both modes (Phase 10R)."""
        return even_size(*self._page_aspect, self._height.value())

    def _on_span_toggled(self, span: bool) -> None:
        self._span_from.setEnabled(span)
        self._span_to.setEnabled(span)
        self._refresh_summary()

    def _on_format_changed(self) -> None:
        if not self._path.isModified():
            self._path.setText(self._default_path())
        self._refresh_summary()

    def _default_path(self) -> str:
        if self._chosen_format() is ExportFormat.PRORES_4444:
            return str(Path.home() / "Movies" / f"{self._stem}-overlay.mov")
        return str(Path.home() / "Movies" / f"{self._stem}-overlay")

    def _chosen_format(self) -> ExportFormat:
        return self._format.currentData()

    def _range(self) -> tuple[float, float]:
        """Audio seconds [start, end) — a measure span converts through
        measure_span_seconds; the frame math downstream is untouched."""
        if self._whole.isChecked():
            return 0.0, self._duration
        return measure_span_seconds(self._measures,
                                    self._span_from.value(),
                                    self._span_to.value(),
                                    self._tempo_map, self._swing,
                                    self._offset)

    def _browse(self) -> None:
        if self._chosen_format() is ExportFormat.PRORES_4444:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export video", self._path.text(),
                "QuickTime movie (*.mov)")
        else:
            path = QFileDialog.getExistingDirectory(
                self, "PNG sequence folder", self._path.text())
        if path:
            self._path.setText(path)
            self._path.setModified(True)

    def _refresh_summary(self) -> None:
        w, h = self._output_size()
        self._width_label.setText(f"{w} px wide")
        try:
            start, end = self._range()
            frames = frame_count(start, end, self._fps.currentData())
        except ValueError:
            self._summary.setText("empty range")
            self._export_btn.setEnabled(False)
            return
        self._summary.setText(f"{frames} frames · {w}×{h} · video t=0 is "
                              f"recording t={start:.2f} s")
        self._export_btn.setEnabled(not self._running)

    def _restore(self, settings: dict) -> None:
        self._fps.setCurrentText(str(settings.get("fps", 60)))
        fmt = settings.get("format")
        if fmt is ExportFormat.PNG_SEQUENCE:
            self._format.setCurrentIndex(1)
        # one height for both modes (Phase 10R: the frame keeps the page
        # aspect everywhere); stale canvas_w/canvas_h session keys from
        # the removed free-form system canvas are simply ignored
        self._height.setValue(settings.get("height", 2160))
        if settings.get("path"):
            self._path.setText(settings["path"])
            self._path.setModified(True)

    def remembered(self) -> dict:
        """Session memory only (R3)."""
        return {"fps": self._fps.currentData(),
                "format": self._chosen_format(),
                "path": self._path.text() if self._path.isModified() else "",
                "height": self._height.value()}

    # -- the run ----------------------------------------------------------------

    def _start(self) -> None:
        start, end = self._range()
        fps = self._fps.currentData()
        out = Path(self._path.text()).expanduser()
        if not self._path.text().strip():
            self._status.setText("choose an output path")
            return
        spec = ExportSpec(fps=fps, height=self._height.value(),
                          mode=self._mode,
                          start_seconds=start, end_seconds=end,
                          offset_seconds=self._offset,
                          format=self._chosen_format(), out_path=out)
        self._status.setText("building scene…")
        self.repaint()
        self._renderer = FrameRenderer(self._inputs, self._style,
                                       self._tempo_map, self._swing, spec,
                                       overrides=self._overrides)
        w, h = self._renderer.size
        try:
            if spec.format is ExportFormat.PRORES_4444:
                out.parent.mkdir(parents=True, exist_ok=True)
                self._sink = ProResFfmpegSink(out, w, h, fps, find_ffmpeg())
            else:
                self._sink = PngSequenceSink(out, self._stem)
        except OSError as exc:
            self._fail(str(exc))
            return

        self._running = True
        self._cancel_requested = False
        self._frame = 0
        self._recent.clear()
        self._progress.setRange(0, self._renderer.frame_count)
        self._progress.setValue(0)
        self._set_inputs_enabled(False)
        self._export_btn.setEnabled(False)
        self._cancel_btn.setText("Cancel")
        self._status.setText("exporting…")
        QTimer.singleShot(0, self._render_batch)

    def _render_batch(self) -> None:
        if not self._running:
            return
        assert self._renderer is not None and self._sink is not None
        if self._cancel_requested:
            self._sink.abort()
            self._finish_ui("export cancelled — partial output removed")
            return
        t0 = time.perf_counter()
        total = self._renderer.frame_count
        try:
            while (self._frame < total
                   and time.perf_counter() - t0 < _BATCH_BUDGET_S):
                image = self._renderer.render_frame(self._frame)
                self._sink.write(self._frame, image)
                self._frame += 1
        except EncodeError as exc:
            self._sink.abort()
            self._fail(str(exc))
            return
        self._recent.append((self._frame, time.perf_counter()))
        self._progress.setValue(self._frame)
        self._status.setText(self._eta_text(total))
        if self._frame >= total:
            try:
                self._sink.finish()
            except EncodeError as exc:
                self._fail(str(exc))
                return
            self._progress.setValue(total)
            self._finish_ui(f"wrote {self._out_display()}")
            self.accept()                     # success closes the dialog
            return
        QTimer.singleShot(0, self._render_batch)

    def _eta_text(self, total: int) -> str:
        if len(self._recent) < 2:
            return "exporting…"
        (f0, t0), (f1, t1) = self._recent[0], self._recent[-1]
        if t1 <= t0 or f1 <= f0:
            return "exporting…"
        rate = (f1 - f0) / (t1 - t0)
        remaining = (total - self._frame) / rate
        return (f"frame {self._frame}/{total} · {rate:.0f} fps · "
                f"~{remaining:.0f} s left")

    def _out_display(self) -> str:
        return self._path.text()

    def _fail(self, message: str) -> None:
        self._finish_ui(f"export failed: {message}")

    def _finish_ui(self, message: str) -> None:
        self._running = False
        self._renderer = None
        self._sink = None
        self._status.setText(message)
        self._set_inputs_enabled(True)
        self._export_btn.setEnabled(True)
        self._cancel_btn.setText("Close")

    def _set_inputs_enabled(self, enabled: bool) -> None:
        for widget in (self._fps, self._format, self._whole,
                       self._span, self._path, *self._size_widgets()):
            widget.setEnabled(enabled)
        span = enabled and self._span.isChecked()
        self._span_from.setEnabled(span)
        self._span_to.setEnabled(span)

    # -- cancel / close routing ---------------------------------------------------

    def _cancel_or_close(self) -> None:
        if self._running:
            self._cancel_requested = True
        else:
            self.reject()

    def reject(self) -> None:                        # Esc while running
        if self._running:
            self._cancel_requested = True
            return
        super().reject()

    def closeEvent(self, event) -> None:             # noqa: N802 (Qt naming)
        if self._running:
            self._cancel_requested = True
            event.ignore()
            return
        super().closeEvent(event)
