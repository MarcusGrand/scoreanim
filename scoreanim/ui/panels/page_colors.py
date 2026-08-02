"""The Page colours block: the paper and the ink, as two swatches.

Its own inspector section rather than two more rows in Appearance &
Effects, for two reasons: that panel was already at the module size
ceiling, and these two are not effect settings — they are what the page
is drawn in, whether anything animates or not.

Two colours, two gestures, two commands. Picking a colour is one
gesture; "Default" is one gesture that DELETES the key rather than
storing the default, which is what keeps an untouched document
byte-identical on save.

No live preview and no spinboxes here, so `ui/live_field.py` is not
involved. QColorDialog's modal `getColor` is used rather than its
`currentColorChanged` signal on purpose: a live preview would recolour
every item on the page on every mouse-move inside the colour wheel.
"""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFormLayout, QHBoxLayout, QPushButton,
                               QWidget)

from scoreanim.core.animation import read_colors
from scoreanim.core.project import ProjectDoc, SetPageColor
from scoreanim.ui.app_state import AppState

# (document key, row label, what the picker dialog is called)
_COLORS = (("background", "Background", "Page background"),
           ("ink", "Ink", "Score ink"))


class PageColorsPanel(QWidget):
    """Background and Ink, each a swatch plus a Default."""

    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._swatches: dict[str, QPushButton] = {}
        self._defaults: dict[str, QPushButton] = {}

        form = QFormLayout(self)
        form.setContentsMargins(8, 2, 8, 6)
        for key, label, title in _COLORS:
            swatch = QPushButton()
            swatch.setToolTip(f"{title} — click to pick a colour")
            swatch.clicked.connect(
                lambda _=False, k=key, t=title: self._pick(k, t))
            default = QPushButton("Default")
            default.setToolTip("Back to white paper and black ink — "
                               "which is also what an untouched project "
                               "stores: nothing at all")
            default.clicked.connect(
                lambda _=False, k=key: self._commit(k, None))
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(swatch, 1)
            row.addWidget(default)
            box = QWidget()
            box.setLayout(row)
            form.addRow(label, box)
            self._swatches[key] = swatch
            self._defaults[key] = default

        app_state.document_changed.connect(self._resync)
        self.sync_from_document(app_state.doc)

    # -- display -----------------------------------------------------------

    def _resync(self) -> None:
        self.sync_from_document(self._state.doc)

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Re-derive both swatches from the document — execute, undo,
        redo and project load all arrive here, and none of them may
        re-execute anything."""
        colors = read_colors(doc.style.colors)
        stored = doc.style.colors
        for key, _, _ in _COLORS:
            value = getattr(colors, key)
            self._swatches[key].setText(
                value if key in stored else f"{value} (default)")
            self._set_swatch_color(self._swatches[key], value)
            # nothing to reset when the key is not there at all
            self._defaults[key].setEnabled(key in stored)

    @staticmethod
    def _set_swatch_color(button: QPushButton, value: str) -> None:
        """Show the colour on the button as well as naming it — the hex
        alone is hard to read as a colour, and this block is the one
        place in the app where the point IS what it looks like."""
        color = QColor(value)
        # black text on a light colour, white on a dark one, so the hex
        # stays readable whatever the user picks
        text = "#000000" if color.lightnessF() > 0.5 else "#ffffff"
        button.setStyleSheet(
            f"QPushButton {{ background-color: {value}; color: {text}; }}")

    # -- writes ------------------------------------------------------------

    def _pick(self, key: str, title: str) -> None:
        from PySide6.QtWidgets import QColorDialog

        current = QColor(getattr(read_colors(self._state.doc.style.colors),
                                 key))
        picked = QColorDialog.getColor(current, self, title)
        if picked.isValid():
            self._commit(key, picked.name())
        else:
            self._resync()                   # cancelled: nothing changed

    def _commit(self, key: str, value: str | None) -> None:
        if value == self._state.doc.style.colors.get(key):
            return                           # no-op: not an undo entry
        self._state.execute(SetPageColor(key, value))
