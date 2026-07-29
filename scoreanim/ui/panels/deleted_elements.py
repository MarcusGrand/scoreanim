"""The deleted-elements readout: what has been hidden, and a way back.

The `panels/break_overrides.py` template, one dock section down. What it
shows is the document's delete INTENT, and its job is as much wording as
listing: "Delete" is a strong word for something that only hides ink, so
the section says plainly that the music is unchanged and gives every row
a restore.

Deleted ink is not clickable — that is what hiding does — so this list
is the ONLY way back other than undo. That is why it exists at all, and
why it is a readout in the layout zone rather than a dialog: it should
be visible while you work, next to the break overrides you authored the
same way.

One row per OBJECT, not per id: a hairpin broken across three systems is
three hidden ids and one deleted hairpin, so `deleted_families` groups
them and the row restores the whole family in one step.

The restore needs no new command (the D12 idiom): `SetElementsHidden`
with `hidden=False` is what a row's button and "Restore all" both send,
through the same `execute()` the Delete action uses.

Document-driven, so it resyncs through the zone's `sync_from_document`
pass rather than a subscription of its own — a deletion is document
state, not transient state.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from scoreanim.core.editing.deletion import (deleted_families, deleted_ids,
                                             describe)
from scoreanim.core.project import ProjectDoc, SetElementsHidden
from scoreanim.core.score.identity import ElementId
from scoreanim.ui.app_state import AppState

_EMPTY = "Nothing deleted"
_NOTE = "Hidden, not removed — the music is unchanged."
_RESTORE_ALL = "Restore all"


class DeletedElementsList(QWidget):
    """Every deleted object, with a per-row restore and a restore-all."""

    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(2)
        note = QLabel(_NOTE)
        note.setWordWrap(True)
        note.setEnabled(False)
        self._column.addWidget(note)
        self._empty = QLabel(_EMPTY)
        self._empty.setEnabled(False)
        self._column.addWidget(self._empty)
        self._rows: list[QWidget] = []
        self.restore_all_button = QPushButton(_RESTORE_ALL)
        self.restore_all_button.setToolTip("Bring every deleted object back")
        self.restore_all_button.clicked.connect(self._restore_all)
        self._column.addWidget(self.restore_all_button)
        self.sync_from_document(app_state.doc)

    # -- what is stored -----------------------------------------------------

    @staticmethod
    def entries(doc: ProjectDoc) -> tuple[tuple[ElementId, ...], ...]:
        """One entry per deleted object, in score order. Pure and static
        so a test can assert the readout's content without going through
        widgets."""
        return deleted_families(doc.layout_overrides,
                                [t.element_id for t in doc.stage.texts])

    # -- document sync ------------------------------------------------------

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Rebuild the rows wholesale — a handful of rows that only move
        when a delete or restore runs, and rebuilding means a row's
        captured ids can never go stale behind its button."""
        for row in self._rows:
            self._column.removeWidget(row)
            row.deleteLater()
        self._rows = []
        for index, family in enumerate(self.entries(doc)):
            row = self._row(family)
            self._rows.append(row)
            # keep the restore-all button last
            self._column.insertWidget(index + 2, row)
        self._empty.setVisible(not self._rows)
        self.restore_all_button.setEnabled(bool(self._rows))

    def _row(self, family: tuple) -> QWidget:
        row = QWidget(self)
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        label = QLabel(describe(family[0]))
        label.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Preferred)
        line.addWidget(label)
        restore = QPushButton("↺")
        restore.setFixedWidth(24)
        restore.setToolTip("Restore this object")
        restore.clicked.connect(lambda _=False, f=family: self._restore(f))
        line.addWidget(restore)
        return row

    def _restore(self, family: tuple) -> None:
        self._state.execute(SetElementsHidden(tuple(family), False))

    def _restore_all(self) -> None:
        """One command, so bringing everything back is ONE undo entry."""
        doc = self._state.doc
        ids = deleted_ids(doc.layout_overrides,
                          [t.element_id for t in doc.stage.texts])
        if ids:
            self._state.execute(SetElementsHidden(ids, False))
