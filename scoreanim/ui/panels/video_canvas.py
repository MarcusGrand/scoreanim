"""The Video canvas block: the export frame, previewed live.

Three document controls (rule 8, one command each): a preset dropdown
for the frame, Width/Height for a custom one, and Scale for how big
the score sits inside it. Width, Height and Scale are LiveFields —
every keystroke previews on the stage and the typing session lands as
one undo entry.

The preview-background control is different in kind: it says what the
LIVE stage paints behind the overlay (the video it will sit on), which
is view state, not document intent — it rides QSettings and a signal
to the window, never a command, and export never sees it (ruling R1).
"""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QPushButton, QSpinBox, QWidget)

from scoreanim.core.project import (Command, ProjectDoc, SetScoreScale,
                                    SetVideoCanvas, VideoCanvas)
from scoreanim.ui.app_state import AppState
from scoreanim.ui.live_field import LiveField
from scoreanim.ui.window_state import default_settings

_PRESETS: tuple[tuple[int, int], ...] = (
    (1920, 1080), (1080, 1920), (3840, 2160), (2160, 3840))
_CUSTOM = "custom"
_SEED = VideoCanvas(1920, 1080)          # first canvas a fresh doc gets

_PREVIEW_KEY = "stage/overlayPreview"
_COLOR_KEY = "stage/overlayColor"
_DEFAULT_COLOR = "#000000"               # black video, the common case


class VideoCanvasPanel(QWidget):
    """Preset + W/H + Scale (document), preview background (view)."""

    preview_changed = Signal(bool, QColor)

    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None,
                 settings=None) -> None:
        super().__init__(parent)
        self._state = app_state
        # injectable for tests (the window_state functions' pattern)
        self._settings = settings if settings is not None \
            else default_settings()

        self._preset = QComboBox()
        self._preset.addItem("Page aspect (no canvas)", None)
        for w, h in _PRESETS:
            shape = "portrait" if h > w else "landscape"
            self._preset.addItem(f"{w} × {h} ({shape})", (w, h))
        self._preset.addItem("Custom…", _CUSTOM)
        self._preset.setToolTip("The video frame the export will fill, "
                                "shown live on the stage")
        # activated is user-only, so a resync can never re-execute
        self._preset.activated.connect(self._on_preset)

        self._width = QSpinBox()
        self._height = QSpinBox()
        for spin in (self._width, self._height):
            spin.setRange(16, 8192)
            spin.setSingleStep(2)
            spin.setSuffix(" px")
        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.addWidget(self._width)
        size_row.addWidget(self._height)
        size_box = QWidget()
        size_box.setLayout(size_row)

        self._scale = QDoubleSpinBox()
        self._scale.setRange(10.0, 800.0)
        self._scale.setDecimals(0)
        self._scale.setSingleStep(5.0)
        self._scale.setSuffix(" %")
        self._scale.setToolTip("How big the score sits in the frame — "
                               "100 % fits the page, more crops at the "
                               "frame edge")

        self.live_fields = (
            LiveField(self._width, app_state,
                      lambda v: self._edit_side(width=int(v))),
            LiveField(self._height, app_state,
                      lambda v: self._edit_side(height=int(v))),
            LiveField(self._scale, app_state, self._edit_scale),
        )

        # -- preview background: view state, never the document --------
        self._preview_box = QCheckBox("Preview on video")
        self._preview_box.setToolTip(
            "Paint the frame with a video color behind the overlay — "
            "live only, the export stays transparent")
        self._swatch = QPushButton()
        self._swatch.setFixedSize(28, 20)
        self._swatch.clicked.connect(self._pick_color)
        preview_row = QHBoxLayout()
        preview_row.setContentsMargins(0, 0, 0, 0)
        preview_row.addWidget(self._preview_box)
        preview_row.addWidget(self._swatch)
        preview_row.addStretch(1)
        preview_box = QWidget()
        preview_box.setLayout(preview_row)

        form = QFormLayout(self)
        form.setContentsMargins(8, 2, 8, 6)
        form.addRow("Frame", self._preset)
        form.addRow("Size", size_box)
        form.addRow("Scale", self._scale)
        form.addRow("", preview_box)

        self._preview_box.toggled.connect(self._on_preview_toggled)
        self._show_swatch()

        app_state.document_changed.connect(self._resync)
        self.sync_from_document(app_state.doc)

    # -- document intent ---------------------------------------------------

    def _edit_side(self, **side: int) -> Command | None:
        canvas = self._state.committed.stage.canvas
        if canvas is None:
            return None                  # fields are disabled; belt only
        edited = replace(canvas, **side)
        return None if edited == canvas else SetVideoCanvas(edited)

    def _edit_scale(self, percent: float) -> Command | None:
        canvas = self._state.committed.stage.canvas
        if canvas is None:
            return None
        scale = float(percent) / 100.0
        return None if scale == canvas.scale else SetScoreScale(scale)

    def _on_preset(self, index: int) -> None:
        chosen = self._preset.itemData(index)
        committed = self._state.committed.stage.canvas
        if chosen is None:
            if committed is not None:
                self._state.execute(SetVideoCanvas(None))
        elif chosen == _CUSTOM:
            if committed is None:
                self._state.execute(SetVideoCanvas(_SEED))
        else:
            w, h = chosen
            scale = committed.scale if committed is not None else 1.0
            canvas = VideoCanvas(w, h, scale)
            if canvas != committed:
                self._state.execute(SetVideoCanvas(canvas))

    def _resync(self) -> None:
        self.sync_from_document(self._state.doc)

    def _preset_index(self, data) -> int:
        """findData by Python equality — Qt's own findData compares
        QVariants and never matches a tuple."""
        for i in range(self._preset.count()):
            if self._preset.itemData(i) == data:
                return i
        return -1

    def sync_from_document(self, doc: ProjectDoc) -> None:
        canvas = doc.stage.canvas
        self._preset.blockSignals(True)
        if canvas is None:
            self._preset.setCurrentIndex(0)
        else:
            index = self._preset_index((canvas.width, canvas.height))
            self._preset.setCurrentIndex(
                index if index >= 0 else self._preset_index(_CUSTOM))
        self._preset.blockSignals(False)
        width, height = self.live_fields[0], self.live_fields[1]
        scale = self.live_fields[2]
        if canvas is not None:
            width.resync(canvas.width)
            height.resync(canvas.height)
            scale.resync(canvas.scale * 100.0)
        for field in self.live_fields:
            field.set_enabled(canvas is not None)

    # -- preview background (view state) -----------------------------------

    def overlay_preview(self) -> tuple[bool, QColor]:
        """Current preview state, for the window to apply at startup."""
        active = self._settings.value(_PREVIEW_KEY, False, type=bool)
        color = QColor(self._settings.value(_COLOR_KEY, _DEFAULT_COLOR,
                                            type=str))
        if not color.isValid():
            color = QColor(_DEFAULT_COLOR)
        return active, color

    def restore_preview(self) -> None:
        """Reflect QSettings in the checkbox (fires the signal if the
        stored state is on — the window connects before calling this)."""
        active, _ = self.overlay_preview()
        self._preview_box.setChecked(active)

    def _on_preview_toggled(self, checked: bool) -> None:
        self._settings.setValue(_PREVIEW_KEY, checked)
        self.preview_changed.emit(checked, self.overlay_preview()[1])

    def _pick_color(self) -> None:
        current = self.overlay_preview()[1]
        color = QColorDialog.getColor(current, self, "Preview video color")
        if not color.isValid():
            return
        self._settings.setValue(_COLOR_KEY, color.name())
        self._show_swatch()
        self.preview_changed.emit(self._preview_box.isChecked(), color)

    def _show_swatch(self) -> None:
        color = self.overlay_preview()[1]
        self._swatch.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid #888;")
