"""The break-overrides readout (M6.7): what the two maps hold, and a
per-entry clear.

The layout zone's second half, its own widget module rather than a limb
on the dock (D9). What it shows is the document's authored break INTENT —
both sparse maps, merged into one list in measure order, because the user
authored them in one pass down the score and thinks of them that way. It
deliberately does NOT show the engraved result: where the systems and
pages actually fall is derived (rule 5), it is on screen already, and a
readout that mixed the two would make an override look like a fact.

The clear needs **no new command** (D12): `mode=None` already pops an
entry, so a row's button is the same `SetPageBreak` / `SetSystemBreak`
the toggle sends, arriving through `execute()` on exactly the path that
re-engraves, re-anchors the view and restores the selection. No special
case, no second path to keep in sync.

Document-driven, so it resyncs through the window's `sync_from_document`
pass like `EffectsPanel` — not through a subscription of its own, which
is the `SelectionPanel` shape and would be wrong here: an override is
document state, not transient state.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from scoreanim.core.project import (PageBreak, ProjectDoc, SetPageBreak,
                                    SetSystemBreak, SystemBreak)
from scoreanim.ui.app_state import AppState

_EMPTY = "No break overrides"

# One phrase per (axis, mode). Says what the override ASKS FOR, in the
# same words the action labels use, so a row and the button that wrote it
# read the same way.
_PHRASE = {
    (False, SystemBreak.FORCE): "force system break",
    (False, SystemBreak.SUPPRESS): "remove system break",
    (True, PageBreak.FORCE): "force page break",
    (True, PageBreak.SUPPRESS): "remove page break",
}


class BreakOverridesList(QWidget):
    """Both override maps in measure order, each row with a clear."""

    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(2)
        self._empty = QLabel(_EMPTY)
        self._empty.setEnabled(False)
        self._column.addWidget(self._empty)
        self._rows: list[QWidget] = []
        self.sync_from_document(app_state.doc)

    # -- what is stored -----------------------------------------------------

    @staticmethod
    def entries(doc: ProjectDoc) -> tuple[tuple[int, bool, object], ...]:
        """`(ordinal, is_page, mode)` for every override in BOTH maps, in
        measure order and systems-before-pages within an ordinal.

        Pure and static so a test can assert the readout's content
        without going through widgets — and so the widget below has
        nothing to get wrong beyond drawing it.
        """
        rows = [(ordinal, False, mode)
                for ordinal, mode in doc.system_break_overrides.items()]
        rows += [(ordinal, True, mode)
                 for ordinal, mode in doc.page_break_overrides.items()]
        return tuple(sorted(rows, key=lambda row: (row[0], row[1])))

    @staticmethod
    def describe(ordinal: int, is_page: bool, mode) -> str:
        return f"m{ordinal}: {_PHRASE[(is_page, mode)]}"

    # -- document sync ------------------------------------------------------

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Rebuild the rows wholesale.

        A diff would buy nothing: the list is a handful of rows, it only
        changes when a break command runs, and that command has just
        re-engraved the whole score. Rebuilding also means a row's
        captured ordinal can never go stale behind its button.
        """
        for row in self._rows:
            self._column.removeWidget(row)
            row.deleteLater()
        self._rows = []
        for ordinal, is_page, mode in self.entries(doc):
            row = self._row(ordinal, is_page, mode)
            self._rows.append(row)
            self._column.addWidget(row)
        self._empty.setVisible(not self._rows)

    def _row(self, ordinal: int, is_page: bool, mode) -> QWidget:
        row = QWidget(self)
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        label = QLabel(self.describe(ordinal, is_page, mode))
        label.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Preferred)
        line.addWidget(label)
        clear = QPushButton("✕")
        clear.setFixedWidth(24)
        clear.setToolTip(f"Clear this override (measure {ordinal})")
        clear.clicked.connect(lambda _=False, o=ordinal, p=is_page:
                              self._clear(o, p))
        line.addWidget(clear)
        return row

    def _clear(self, ordinal: int, is_page: bool) -> None:
        """`mode=None` pops the entry — the same command the toggle
        sends, through the same `execute()` (D12)."""
        command = (SetPageBreak(ordinal, None) if is_page
                   else SetSystemBreak(ordinal, None))
        self._state.execute(command)
