"""CollapsibleSection: titled header that shows/hides a content widget.

Qt has no built-in collapsible group, so the inspector's sections (M1.4)
compose this. Expanded/collapsed is per-section UI state — M1.8 persists
it via QSettings alongside dock geometry; nothing here touches the
document (rule 5).

The header is a flat full-width band, not a button (A3): a chevron, a
small bold label, and a hover highlight across the whole width, so a
section reads as a heading you can click rather than as a control. A
`QPushButton` under the hood because it is the one Qt button whose text
can be pinned to the left; everything that makes it look like a band is
in the app-wide QSS, under the name `SectionHeader`.

The band is also the seam between two sections: it is a shade darker
than the body under it and carries a 1px line along its top, so a dock
with every section open still reads as a stack of blocks. That is one
rule in the theme, so every section gets it — nothing here, and nothing
in a panel, paints a divider of its own.

The one thing this widget decides is whether to draw that line at all.
It is a separator, so the section sitting at the top of its stack does
not get one: there is nothing above it to divide it from, and in a dock
the line would land straight on the title bar's own. The section works
that out from its place in its parent's layout and hands the answer to
the theme as the `topmost` property.
"""
from __future__ import annotations

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from scoreanim.ui.theme import icons


class CollapsibleSection(QWidget):
    """A header band over a content widget.

    Clicking the header toggles the content's visibility. Sections start
    expanded; `expanded` / `set_expanded` expose the state for QSettings
    persistence (M1.8).
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._header = QPushButton(self)
        # the app-wide theme styles headers by this name (ui/theme)
        self._header.setObjectName("SectionHeader")
        self._header.setText(title)
        self._header.setCheckable(True)
        self._header.setChecked(True)
        self._header.setFlat(True)
        self._header.setIconSize(icons.BUTTON_SIZE)
        # A header is not a default button: without this, putting one in
        # a dialog would make Return click it.
        self._header.setAutoDefault(False)
        self._header.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Fixed)
        self._header.toggled.connect(self._on_toggled)
        self._show_chevron(True)
        # Written before the theme ever reads it, so the selector that
        # drops the separator has something to match on from the start.
        self._header.setProperty("topmost", False)

        self._content: QWidget | None = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
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

    def showEvent(self, event: QShowEvent) -> None:
        """Last chance to see where we ended up: by now the section is
        in its parent's layout, so it can tell whether it is the one at
        the top of the stack."""
        super().showEvent(event)
        self._refresh_separator()

    # -- the line above the band ----------------------------------------------

    def _refresh_separator(self) -> None:
        """Tell the theme whether to draw our separator.

        Qt reads a dynamic property in a selector once, when it polishes
        the widget — changing the value later does nothing until the
        widget is polished again, which is what the two calls below are
        for.
        """
        topmost = self._is_first_in_parent()
        if self._header.property("topmost") == topmost:
            return
        self._header.setProperty("topmost", topmost)
        self._header.style().unpolish(self._header)
        self._header.style().polish(self._header)

    def _is_first_in_parent(self) -> bool:
        """Are we the first widget in the layout we were put in?

        A section with no parent layout says no: on its own it cannot
        know what sits above it, and drawing the line is the safe answer
        — one line too many is tidier than a stack with no seam in it.
        """
        parent = self.parentWidget()
        layout = parent.layout() if parent is not None else None
        if layout is None:
            return False
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()
            if widget is not None:          # skip spacers and stretches
                return widget is self
        return False

    def _on_toggled(self, checked: bool) -> None:
        self._show_chevron(checked)
        if self._content is not None:
            self._content.setVisible(checked)

    def _show_chevron(self, expanded: bool) -> None:
        """Down while the body is showing, right while it is folded away
        — the disclosure triangle everyone already knows, drawn from the
        same vendored set as every other icon."""
        self._header.setIcon(
            icons.plain_icon("chevron-down" if expanded else "chevron-right"))
