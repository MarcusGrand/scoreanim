"""Export dialog: the settings form, and the UI around a run.

The long-running walk itself lives in ui/export_run.py (ExportRun): the
dialog builds the renderer and the sink from its form, hands them to a
run, and reflects the run's progress callbacks in its own widgets.
Rendering and encoding live in render/export.py and render/encode.py;
core is untouched.

Settings are session memory only (ruling R3): remembered() hands back a
dict the window passes into the next dialog. Nothing enters the project
document.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QProgressBar, QPushButton,
                               QRadioButton, QSpinBox, QVBoxLayout)

from scoreanim.core.animation import StyleRules
from scoreanim.core.audio import PeakCache
from scoreanim.core.project.stage_config import PresentationMode
from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing import SwingRegion, TempoMap
from scoreanim.render.encode import (AlphaMode, PngSequenceSink,
                                     ProResFfmpegSink, find_ffmpeg)
from scoreanim.render.export import (AnimationInputs, ExportFormat,
                                     ExportSpec, FrameRenderer, even_size,
                                     frame_count, measure_span_seconds)
from scoreanim.ui.export_run import ExportRun

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
                 peaks: PeakCache | None = None,
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
        # the decoded audio, live at open like `style` and `overrides`:
        # the volume response has to read the same recording the stage
        # is reading, or the export would animate differently
        self._peaks = peaks
        self._measures = tuple(measures)
        self._offset = offset_seconds
        self._duration = duration_seconds
        self._stem = Path(score_name).stem or "score"

        self._run: ExportRun | None = None

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

        # How the file writes colour beside alpha. Getting this wrong
        # does not break the export — it makes every soft edge, and a
        # glow above all, come out solid once the editor has a clip
        # underneath (render/encode.py).
        self._alpha = QComboBox()
        self._alpha.addItem("Premultiplied — Premiere, most NLEs",
                            AlphaMode.PREMULTIPLIED)
        self._alpha.addItem("Straight (unmatted)", AlphaMode.STRAIGHT)
        self._alpha.setToolTip(
            "If soft edges and glows look too solid over the video "
            "underneath, try the other one.")
        form.addRow("Alpha:", self._alpha)

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
        alpha = settings.get("alpha")
        if alpha is not None:
            index = self._alpha.findData(alpha)
            if index >= 0:
                self._alpha.setCurrentIndex(index)
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
                "alpha": self._alpha.currentData(),
                "path": self._path.text() if self._path.isModified() else "",
                "height": self._height.value()}

    # -- the run (ui/export_run.py owns the walk) --------------------------------

    @property
    def _running(self) -> bool:
        return self._run is not None

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
        renderer = FrameRenderer(self._inputs, self._style,
                                 self._tempo_map, self._swing, spec,
                                 overrides=self._overrides,
                                 peaks=self._peaks)
        w, h = renderer.size
        try:
            alpha = self._alpha.currentData()
            if spec.format is ExportFormat.PRORES_4444:
                out.parent.mkdir(parents=True, exist_ok=True)
                sink = ProResFfmpegSink(out, w, h, fps, find_ffmpeg(),
                                        alpha)
            else:
                sink = PngSequenceSink(out, self._stem, alpha)
        except OSError as exc:
            self._status.setText(f"export failed: {exc}")
            return

        self._run = ExportRun(renderer, sink,
                              on_progress=self._on_run_progress,
                              on_done=self._on_run_done)
        self._progress.setRange(0, self._run.frame_count)
        self._progress.setValue(0)
        self._set_inputs_enabled(False)
        self._export_btn.setEnabled(False)
        self._cancel_btn.setText("Cancel")
        self._status.setText("exporting…")
        self._run.start()

    def _on_run_progress(self, frame: int, total: int, text: str) -> None:
        self._progress.setValue(frame)
        self._status.setText(text)

    def _on_run_done(self, ok: bool, message: str) -> None:
        self._run = None
        self._status.setText(message if not ok
                             else f"wrote {self._path.text()}")
        self._set_inputs_enabled(True)
        self._export_btn.setEnabled(True)
        self._cancel_btn.setText("Close")
        if ok:
            self.accept()                     # success closes the dialog

    def _set_inputs_enabled(self, enabled: bool) -> None:
        for widget in (self._fps, self._format, self._whole,
                       self._span, self._path, *self._size_widgets()):
            widget.setEnabled(enabled)
        span = enabled and self._span.isChecked()
        self._span_from.setEnabled(span)
        self._span_to.setEnabled(span)

    # -- cancel / close routing ---------------------------------------------------

    def _cancel_or_close(self) -> None:
        if self._run is not None:
            self._run.cancel()
        else:
            self.reject()

    def reject(self) -> None:                        # Esc while running
        if self._run is not None:
            self._run.cancel()
            return
        super().reject()

    def closeEvent(self, event) -> None:             # noqa: N802 (Qt naming)
        if self._run is not None:
            self._run.cancel()
            event.ignore()
            return
        super().closeEvent(event)
