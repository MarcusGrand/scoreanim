"""Part-names manager (Phase 9.3): a view over doc.text_overrides.

Each Edit/Reset executes its command immediately (per-action apply, the
staff-groups ruling) — the score re-engraves behind the open dialog
(~0.6 s, the Phase 8 accepted cost) and every action is one undo step,
so there is no Cancel, only Close. The dialog observes document_changed
and rebuilds, which keeps it coherent across undo AND across the
re-engrave that refreshes the effective PartInfos — hence a parts
PROVIDER callable, not a snapshot.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QPushButton,
                               QVBoxLayout)

from scoreanim.core.project import PartTextOverride, SetPartText
from scoreanim.core.score.identity import PartId


class PartNamesDialog(QDialog):
    def __init__(self, app_state, parts_provider, parent=None) -> None:
        """`parts_provider`: () -> current PartInfos in score order (the
        effective, post-override names — refreshed by each re-engrave)."""
        super().__init__(parent)
        self.setWindowTitle("Part Names")
        self._app_state = app_state
        self._parts_provider = parts_provider

        self._list = QListWidget()
        self._edit = QPushButton("Edit…")
        self._reset = QPushButton("Reset to Score")
        close = QPushButton("Close")
        close.setDefault(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self._edit)
        buttons.addWidget(self._reset)
        buttons.addStretch(1)
        buttons.addWidget(close)

        root = QVBoxLayout(self)
        root.addWidget(self._list)
        root.addLayout(buttons)

        self._edit.clicked.connect(self._on_edit)
        self._reset.clicked.connect(self._on_reset)
        self._list.itemSelectionChanged.connect(self._sync_buttons)
        self._list.itemDoubleClicked.connect(lambda _: self._on_edit())
        close.clicked.connect(self.accept)
        app_state.document_changed.connect(self._rebuild)

        self._rebuild()

    # -- doc → list ---------------------------------------------------------

    def _parts(self):
        return tuple(self._parts_provider())

    def _order(self) -> tuple[PartId, ...]:
        return tuple(PartId(p.part_id) for p in self._parts())

    def _override_for(self, part_id: PartId) -> PartTextOverride | None:
        return self._app_state.doc.text_overrides.get(part_id)

    def _label(self, info) -> str:
        overridden = self._override_for(PartId(info.part_id)) is not None
        return (f"{info.name or '(no label)'} · "
                f"abbr: {info.abbreviation or '—'}"
                + (" · overridden" if overridden else ""))

    def _rebuild(self) -> None:
        selected = self._list.currentRow()
        self._list.clear()
        for info in self._parts():
            self._list.addItem(self._label(info))
        if 0 <= selected < self._list.count():
            self._list.setCurrentRow(selected)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        row = self._list.currentRow()
        self._edit.setEnabled(row >= 0)
        parts = self._parts()
        self._reset.setEnabled(
            0 <= row < len(parts)
            and self._override_for(PartId(parts[row].part_id)) is not None)

    # -- actions (each an immediate, individually undoable command) ----------

    def _on_edit(self) -> None:
        row = self._list.currentRow()
        parts = self._parts()
        if not 0 <= row < len(parts):
            return
        info = parts[row]
        editor = _PartTextEditor(info, parent=self)
        if editor.exec():
            name, abbreviation = editor.values()
            self._app_state.execute(
                SetPartText(PartId(info.part_id), name, abbreviation,
                            self._order()))

    def _on_reset(self) -> None:
        row = self._list.currentRow()
        parts = self._parts()
        if 0 <= row < len(parts):
            self._app_state.execute(
                SetPartText(PartId(parts[row].part_id), None, None,
                            self._order()))


class _PartTextEditor(QDialog):
    """One part's label: name + abbreviation, prefilled with the
    EFFECTIVE values (the score's own text until overridden)."""

    def __init__(self, info, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Rename {info.name or info.part_id}")

        self._name = QLineEdit(info.name)
        self._abbreviation = QLineEdit(info.abbreviation)

        form = QFormLayout()
        form.addRow("Name:", self._name)
        form.addRow("Abbreviation:", self._abbreviation)

        ok = QPushButton("OK")
        ok.setDefault(True)
        cancel = QPushButton("Cancel")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(QLabel("The score re-engraves and shifts to fit "
                              "the new label. Empty = no label."))
        root.addLayout(buttons)

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

    def values(self) -> tuple[str, str]:
        return self._name.text(), self._abbreviation.text()
