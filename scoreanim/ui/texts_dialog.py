"""Texts manager (Phase 9): a view over doc.stage.texts plus the
layout's engraved tempo marks (text_class == "tempo").

Each action executes its command immediately (per-action apply, the
staff-groups ruling) — one undo step each, no Cancel, only Close. The
dialog observes document_changed and rebuilds its list, which keeps it
coherent when the user undoes while it is open. Text intent lives in
the document; nothing here is remembered session-side. `band` is the
free space above the top staff (page_content_top on the engraved
layout) — runtime data the edit command re-fits the header block into.

Tempo rows (9.2): Edit on a non-overlaid mark seeds a replacement from
the engraved element and executes ONE AddTempoOverlay (seed + tweaks =
one undo step); on an overlaid mark it edits the existing overlay
text; Restore drops the overlay and un-hides the engraved original.
"""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QLineEdit, QListWidget, QPushButton,
                               QVBoxLayout)

from scoreanim.core.engraving.types import RenderedElement
from scoreanim.core.project import (OVERLAY_PREFIX, AddTempoOverlay,
                                    EditStageText, RemoveTempoOverlay,
                                    StageTextElement)
from scoreanim.core.project.stage_config import seed_overlay_text


class TextsDialog(QDialog):
    def __init__(self, app_state, band: float,
                 tempo_elements: tuple[RenderedElement, ...] = (),
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Texts")
        self._app_state = app_state
        self._band = band
        self._tempo_elements = tuple(tempo_elements)

        self._list = QListWidget()
        self._edit = QPushButton("Edit…")
        self._restore = QPushButton("Restore")
        close = QPushButton("Close")
        close.setDefault(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self._edit)
        buttons.addWidget(self._restore)
        buttons.addStretch(1)
        buttons.addWidget(close)

        root = QVBoxLayout(self)
        root.addWidget(self._list)
        root.addLayout(buttons)

        self._edit.clicked.connect(self._on_edit)
        self._restore.clicked.connect(self._on_restore)
        self._list.itemSelectionChanged.connect(self._sync_buttons)
        self._list.itemDoubleClicked.connect(lambda _: self._on_edit())
        close.clicked.connect(self.accept)
        app_state.document_changed.connect(self._rebuild)

        self._rebuild()

    # -- doc → list ---------------------------------------------------------

    def _texts(self) -> tuple[StageTextElement, ...]:
        return self._app_state.doc.stage.texts

    def _overlay_for(self, element: RenderedElement) -> StageTextElement | None:
        overlay_id = OVERLAY_PREFIX + str(element.identity.element_id)
        return next((t for t in self._texts()
                     if t.element_id == overlay_id), None)

    def _label(self, text: StageTextElement) -> str:
        style = "".join(s for s, on in (("B", text.bold), ("I", text.italic))
                        if on)
        return (f"{text.content} · {text.font_size:.0f}u"
                + (f" · {style}" if style else "")
                + f" · page {text.page}")

    def _tempo_label(self, element: RenderedElement) -> str:
        seed = seed_overlay_text(element)
        overlaid = self._overlay_for(element) is not None
        return (f"tempo: {seed.content} · page {element.page}"
                + (" · overlaid" if overlaid else ""))

    def _rebuild(self) -> None:
        """Rows: stage texts (incl. overlay replacements) first, then
        the engraved tempo marks."""
        selected = self._list.currentRow()
        self._list.clear()
        for text in self._texts():
            self._list.addItem(self._label(text))
        for element in self._tempo_elements:
            self._list.addItem(self._tempo_label(element))
        if 0 <= selected < self._list.count():
            self._list.setCurrentRow(selected)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        row = self._list.currentRow()
        self._edit.setEnabled(row >= 0)
        element = self._tempo_at(row)
        self._restore.setEnabled(element is not None
                                 and self._overlay_for(element) is not None)

    def _tempo_at(self, row: int) -> RenderedElement | None:
        index = row - len(self._texts())
        if 0 <= index < len(self._tempo_elements):
            return self._tempo_elements[index]
        return None

    # -- actions (each an immediate, individually undoable command) ----------

    def _on_edit(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        element = self._tempo_at(row)
        if element is None:                      # a stage-text row
            text = self._texts()[row]
            editor = _TextEditor(text, parent=self)
            if editor.exec():
                self._app_state.execute(
                    EditStageText(text.element_id, editor.text(),
                                  self._band))
            return
        overlay = self._overlay_for(element)
        if overlay is not None:                  # already replaced: edit it
            editor = _TextEditor(overlay, parent=self)
            if editor.exec():
                self._app_state.execute(
                    EditStageText(overlay.element_id, editor.text(),
                                  self._band))
            return
        editor = _TextEditor(seed_overlay_text(element), parent=self)
        if editor.exec():                        # seed + tweaks: ONE step
            self._app_state.execute(
                AddTempoOverlay(element.identity.element_id, editor.text()))

    def _on_restore(self) -> None:
        element = self._tempo_at(self._list.currentRow())
        if element is not None and self._overlay_for(element) is not None:
            self._app_state.execute(
                RemoveTempoOverlay(element.identity.element_id))


class _TextEditor(QDialog):
    """One stage text: content, position, anchor, size, weight, color.
    Returns a full replacement StageTextElement via text()."""

    def __init__(self, text: StageTextElement, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Text")
        self._element_id = text.element_id
        self._page = text.page
        self._color = text.color

        self._content = QLineEdit(text.content)
        self._x = QDoubleSpinBox()
        self._x.setRange(-100000.0, 100000.0)
        self._x.setDecimals(1)
        self._x.setValue(text.x)
        self._y = QDoubleSpinBox()
        self._y.setRange(-100000.0, 100000.0)
        self._y.setDecimals(1)
        self._y.setValue(text.y)
        self._anchor = QComboBox()
        for a in ("start", "middle", "end"):
            self._anchor.addItem(a)
        self._anchor.setCurrentText(text.anchor)
        self._size = QDoubleSpinBox()
        self._size.setRange(1.0, 10000.0)
        self._size.setDecimals(1)
        self._size.setValue(text.font_size)
        self._bold = QCheckBox("Bold")
        self._bold.setChecked(text.bold)
        self._italic = QCheckBox("Italic")
        self._italic.setChecked(text.italic)
        self._color_button = QPushButton()
        self._color_button.clicked.connect(self._pick_color)
        default_color = QPushButton("Default")
        default_color.clicked.connect(lambda: self._set_color(None))
        self._set_color(text.color)

        color_row = QHBoxLayout()
        color_row.addWidget(self._color_button)
        color_row.addWidget(default_color)

        form = QFormLayout()
        form.addRow("Text:", self._content)
        form.addRow("X (page units):", self._x)
        form.addRow("Y (baseline):", self._y)
        form.addRow("Anchor:", self._anchor)
        form.addRow("Font size:", self._size)
        form.addRow("", self._bold)
        form.addRow("", self._italic)
        form.addRow("Color:", color_row)

        ok = QPushButton("OK")
        ok.setDefault(True)
        cancel = QPushButton("Cancel")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(buttons)

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

    def _set_color(self, color: str | None) -> None:
        self._color = color
        self._color_button.setText(color if color else "default (black)")

    def _pick_color(self) -> None:
        picked = QColorDialog.getColor(
            QColor(self._color) if self._color else QColor("black"), self)
        if picked.isValid():
            self._set_color(picked.name())

    def text(self) -> StageTextElement:
        return StageTextElement(
            element_id=self._element_id,
            content=self._content.text(),
            page=self._page,
            x=self._x.value(),
            y=self._y.value(),
            anchor=self._anchor.currentText(),
            font_size=self._size.value(),
            color=self._color,
            bold=self._bold.isChecked(),
            italic=self._italic.isChecked(),
        )
