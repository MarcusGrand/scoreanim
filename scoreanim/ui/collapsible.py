"""CollapsibleSection: titled header that shows/hides a content widget.

Qt has no built-in collapsible group, so the inspector's sections (M1.4)
compose this. Expanded/collapsed is per-section UI state — M1.8 persists
it via QSettings alongside dock geometry; nothing here touches the
document (rule 5).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    """A header QToolButton (arrow indicator) over a content widget.

    Clicking the header toggles the content's visibility. Sections start
    expanded; `expanded` / `set_expanded` expose the state for QSettings
    persistence (M1.8).
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._header = QToolButton(self)
        self._header.setText(title)
        self._header.setCheckable(True)
        self._header.setChecked(True)
        self._header.setArrowType(Qt.ArrowType.DownArrow)
        self._header.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._header.setAutoRaise(True)
        self._header.toggled.connect(self._on_toggled)

        self._content: QWidget | None = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._layout.addWidget(self._header)

    def set_content(self, widget: QWidget) -> None:
        """Install the section body (replaces any previous one)."""
        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.deleteLater()
        self._content = widget
        self._layout.addWidget(widget)
        widget.setVisible(self._header.isChecked())

    @property
    def expanded(self) -> bool:
        return self._header.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        self._header.setChecked(expanded)

    def _on_toggled(self, checked: bool) -> None:
        self._header.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        if self._content is not None:
            self._content.setVisible(checked)
