"""The Page block: light mode or dark mode.

Its own inspector section rather than a row in Appearance & Effects, for
two reasons: it applies whether anything animates or not, and that panel
was already at the module size ceiling.

One choice, two radio buttons, one command per click. Per-colour
fine-tuning may come back later; what the document stores today is the
MODE, and the two colours are derived from it (rule 5).
"""
from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QFormLayout, QHBoxLayout,
                               QRadioButton, QWidget)

from scoreanim.core.animation import DARK, LIGHT, read_colors
from scoreanim.core.project import ProjectDoc, SetColorMode
from scoreanim.ui.app_state import AppState

_MODES = ((LIGHT, "Light", "Black score on white — the printed look"),
          (DARK, "Dark", "White score on a dark blue-grey, for overlaying "
                         "on video"))


class PageColorsPanel(QWidget):
    """Light / Dark, applied live."""

    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._buttons: dict[str, QRadioButton] = {}

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        group = QButtonGroup(self)
        for mode, label, tip in _MODES:
            button = QRadioButton(label)
            button.setToolTip(tip)
            # `clicked` is user-only, so a resync can never re-execute a
            # command by moving the dot itself
            button.clicked.connect(lambda _=False, m=mode: self._commit(m))
            group.addButton(button)
            row.addWidget(button)
            self._buttons[mode] = button
        row.addStretch(1)
        box = QWidget()
        box.setLayout(row)

        form = QFormLayout(self)
        form.setContentsMargins(8, 2, 8, 6)
        form.addRow("Colours", box)

        app_state.document_changed.connect(self._resync)
        self.sync_from_document(app_state.doc)

    def _resync(self) -> None:
        self.sync_from_document(self._state.doc)

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Re-derive the choice from the document — execute, undo, redo
        and project load all arrive here, and none of them may
        re-execute anything."""
        mode = read_colors(doc.style.colors).mode
        self._buttons[mode].setChecked(True)

    def _commit(self, mode: str) -> None:
        if mode == read_colors(self._state.doc.style.colors).mode:
            return                           # no-op: not an undo entry
        # light is the default, and the default stores nothing at all —
        # so choosing it REMOVES the key rather than writing "light"
        self._state.execute(SetColorMode(None if mode == LIGHT else mode))
