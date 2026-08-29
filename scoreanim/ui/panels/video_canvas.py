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

from scoreanim.core.project import (Command, ProjectDoc, SetLyricsSize,
                                    SetScoreScale, SetStaffLineWidth,
                                    SetVideoCanvas, VideoCanvas)
from scoreanim.ui import panel_style, tips
from scoreanim.ui.app_state import AppState
from scoreanim.ui.live_field import LiveField
from scoreanim.ui.window_state import default_settings

_PRESETS: tuple[tuple[int, int], ...] = (
    (1920, 1080), (1080, 1920), (3840, 2160), (2160, 3840))
_CUSTOM = "custom"
_SEED = VideoCanvas(1920, 1080)          # first canvas a fresh doc gets

# one re-engrave per typing pause, not per keystroke (live_field.py)
_REENGRAVE_DELAY_MS = 400

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
        tips.describe(self._preset,
                      "The video frame the export will fill, shown live "
                      "on the stage")
        # activated is user-only, so a resync can never re-execute
        self._preset.activated.connect(self._on_preset)

        self._width = QSpinBox()
        self._height = QSpinBox()
        for spin, side in ((self._width, "wide"), (self._height, "high")):
            spin.setRange(16, 8192)
            spin.setSingleStep(2)
            spin.setSuffix(" px")
            # two fields sharing one row: neither may be squeezed down
            # to its arrows
            spin.setMinimumWidth(panel_style.min_field_width(spin))
            tips.describe(spin, f"How many pixels {side} the exported "
                                f"frame is")
        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.setSpacing(panel_style.COLUMN_GAP)
        size_row.addWidget(self._width)
        size_row.addWidget(self._height)
        size_box = QWidget()
        size_box.setLayout(size_row)

        # Score scale is an ENGRAVING input (rastral size): a change
        # re-engraves (~0.6 s), so its LiveField is DEBOUNCED — the
        # preview fires once per typing pause, live in the playback
        # (Marcus's call), and the commit is still one undo entry.
        self._scale = QDoubleSpinBox()
        self._scale.setRange(50.0, 300.0)
        self._scale.setDecimals(0)
        self._scale.setSingleStep(5.0)
        self._scale.setSuffix(" %")
        tips.describe(self._scale,
                      "How big the notation is drawn — 100 % is the "
                      "score's own size; bigger notes repaginate, and a "
                      "crowded system is yours to break")

        # Lyrics get their own size — the first thing to crowd when
        # the score grows (Marcus, 2026-08-06). Same debounced
        # re-engraving field as Scale; the engraver saturates outside
        # roughly 45–175 %, which is what the range brackets.
        self._lyrics = QDoubleSpinBox()
        self._lyrics.setRange(50.0, 175.0)
        self._lyrics.setDecimals(0)
        self._lyrics.setSingleStep(5.0)
        self._lyrics.setSuffix(" %")
        tips.describe(self._lyrics,
                      "The lyrics' own size — shrink them when a bigger "
                      "score crowds the verses")

        # Staff line thickness (2026-08-07): heavier lines read better
        # over video. Third engraving knob, same debounced contract.
        self._staff_lines = QDoubleSpinBox()
        self._staff_lines.setRange(70.0, 200.0)
        self._staff_lines.setDecimals(0)
        self._staff_lines.setSingleStep(10.0)
        self._staff_lines.setSuffix(" %")
        tips.describe(self._staff_lines,
                      "Staff line thickness — 100 % is the engraver's "
                      "default; heavier lines hold up over video. "
                      "Barlines follow automatically at a fixed ratio")

        self.live_fields = (
            LiveField(self._width, app_state,
                      lambda v: self._edit_side(width=int(v))),
            LiveField(self._height, app_state,
                      lambda v: self._edit_side(height=int(v))),
            LiveField(self._scale, app_state, self._edit_scale,
                      delay_ms=_REENGRAVE_DELAY_MS),
            LiveField(self._lyrics, app_state, self._edit_lyrics,
                      delay_ms=_REENGRAVE_DELAY_MS),
            LiveField(self._staff_lines, app_state, self._edit_staff_lines,
                      delay_ms=_REENGRAVE_DELAY_MS),
        )

        # -- preview background: view state, never the document --------
        self._preview_box = QCheckBox("Preview on video")
        tips.describe(
            self._preview_box,
            "Paint the frame with a video color behind the overlay — "
            "live only, the export stays transparent")
        self._swatch = QPushButton()
        self._swatch.setFixedSize(28, 20)
        tips.describe(self._swatch,
                      "The color painted behind the overlay while you "
                      "work — never exported")
        self._swatch.clicked.connect(self._pick_color)
        preview_row = QHBoxLayout()
        preview_row.setContentsMargins(0, 0, 0, 0)
        preview_row.addWidget(self._preview_box)
        preview_row.addWidget(self._swatch)
        preview_row.addStretch(1)
        preview_box = QWidget()
        preview_box.setLayout(preview_row)

        form = QFormLayout(self)
        panel_style.style_form(form)
        form.addRow("Frame", self._preset)
        form.addRow("Size", size_box)
        form.addRow("Scale", self._scale)
        form.addRow("Lyrics", self._lyrics)
        form.addRow("Staff lines", self._staff_lines)
        form.addRow("", preview_box)
        panel_style.fix_label_column(form)

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
        scale = float(percent) / 100.0
        committed = self._state.committed.engraving.scale
        return None if scale == committed else SetScoreScale(scale)

    def _edit_lyrics(self, percent: float) -> Command | None:
        factor = float(percent) / 100.0
        committed = self._state.committed.engraving.lyric_size
        return None if factor == committed else SetLyricsSize(factor)

    def _edit_staff_lines(self, percent: float) -> Command | None:
        factor = float(percent) / 100.0
        committed = self._state.committed.engraving.staff_line_width
        return None if factor == committed else SetStaffLineWidth(factor)

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
            canvas = VideoCanvas(*chosen)
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
        width, height, scale, lyrics, staff_lines = self.live_fields
        if canvas is not None:
            width.resync(canvas.width)
            height.resync(canvas.height)
        # W/H need a canvas; the engraving knobs are canvas-independent
        # and stay enabled
        no_canvas = "Pick a frame size above, or Custom…, to set this"
        width.set_enabled(canvas is not None, no_canvas)
        height.set_enabled(canvas is not None, no_canvas)
        scale.resync(doc.engraving.scale * 100.0)
        lyrics.resync(doc.engraving.lyric_size * 100.0)
        staff_lines.resync(doc.engraving.staff_line_width * 100.0)

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
