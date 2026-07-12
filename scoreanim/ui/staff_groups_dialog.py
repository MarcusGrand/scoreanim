"""Staff-groups manager (Phase 8): a view over doc.staff_groups.

Each Add/Edit/Remove executes its command immediately (ruling at the
Phase 8 plan review: apply per action) — the bracket re-engraves behind
the open dialog and every action is one undo step, so there is no
Cancel, only Close. The dialog observes document_changed and rebuilds
its list, which keeps it coherent when the user undoes while it is
open. Group intent lives in the document; nothing here is remembered
session-side.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout,
                               QHBoxLayout, QLabel, QListWidget,
                               QPushButton, QVBoxLayout)

from scoreanim.core.project import (AddStaffGroup, EditStaffGroup,
                                    RemoveStaffGroup, StaffGroup)
from scoreanim.core.score.identity import PartId

# MusicXML group-symbol vocabulary, bracket first (the default)
_SYMBOLS = ("bracket", "brace", "line", "square")


class StaffGroupsDialog(QDialog):
    def __init__(self, app_state, parts, parent=None) -> None:
        """`parts`: the loaded score's PartInfos in score order (the
        part_order every command needs — the doc stores intent only)."""
        super().__init__(parent)
        self.setWindowTitle("Staff Groups")
        self._app_state = app_state
        self._parts = tuple(parts)
        self._order = tuple(PartId(p.part_id) for p in self._parts)
        self._names = {PartId(p.part_id): p.name for p in self._parts}

        self._list = QListWidget()
        self._add = QPushButton("Add…")
        self._edit = QPushButton("Edit…")
        self._remove = QPushButton("Remove")
        close = QPushButton("Close")
        close.setDefault(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self._add)
        buttons.addWidget(self._edit)
        buttons.addWidget(self._remove)
        buttons.addStretch(1)
        buttons.addWidget(close)

        root = QVBoxLayout(self)
        root.addWidget(self._list)
        root.addLayout(buttons)

        self._add.clicked.connect(self._on_add)
        self._edit.clicked.connect(self._on_edit)
        self._remove.clicked.connect(self._on_remove)
        self._list.itemSelectionChanged.connect(self._sync_buttons)
        self._list.itemDoubleClicked.connect(lambda _: self._on_edit())
        close.clicked.connect(self.accept)
        app_state.document_changed.connect(self._rebuild)

        self._rebuild()

    # -- doc → list ---------------------------------------------------------

    def _groups(self) -> tuple[StaffGroup, ...]:
        return self._app_state.doc.staff_groups

    def _label(self, group: StaffGroup) -> str:
        first = self._names.get(group.parts[0], group.parts[0])
        last = self._names.get(group.parts[-1], group.parts[-1])
        span = first if len(group.parts) == 1 else f"{first} – {last}"
        barlines = "joined barlines" if group.join_barlines \
            else "separate barlines"
        return f"{span} · {group.symbol} · {barlines}"

    def _rebuild(self) -> None:
        selected = self._list.currentRow()
        self._list.clear()
        for group in self._groups():
            self._list.addItem(self._label(group))
        if 0 <= selected < self._list.count():
            self._list.setCurrentRow(selected)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        has_selection = self._list.currentRow() >= 0
        self._edit.setEnabled(has_selection)
        self._remove.setEnabled(has_selection)

    # -- actions (each an immediate, individually undoable command) ----------

    def _on_add(self) -> None:
        editor = _GroupEditor(self._parts, group=None, parent=self)
        if editor.exec():
            self._app_state.execute(
                AddStaffGroup(editor.group(), self._order))

    def _on_edit(self) -> None:
        index = self._list.currentRow()
        if index < 0:
            return
        editor = _GroupEditor(self._parts, group=self._groups()[index],
                              parent=self)
        if editor.exec():
            self._app_state.execute(
                EditStaffGroup(index, editor.group(), self._order))

    def _on_remove(self) -> None:
        index = self._list.currentRow()
        if index >= 0:
            self._app_state.execute(RemoveStaffGroup(index))


class _GroupEditor(QDialog):
    """One group: a From/To part range (contiguous by construction),
    symbol, and the joined-barlines flag."""

    def __init__(self, parts, group: StaffGroup | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Staff Group" if group else "Add Staff Group")
        self._parts = tuple(parts)

        self._from = QComboBox()
        self._to = QComboBox()
        for p in self._parts:
            self._from.addItem(p.name, PartId(p.part_id))
            self._to.addItem(p.name, PartId(p.part_id))
        self._symbol = QComboBox()
        for s in _SYMBOLS:
            self._symbol.addItem(s)
        self._join = QCheckBox("Join barlines through the group")
        self._join.setChecked(True)

        form = QFormLayout()
        form.addRow("From part:", self._from)
        form.addRow("To part:", self._to)
        form.addRow("Symbol:", self._symbol)
        form.addRow("", self._join)

        ok = QPushButton("OK")
        ok.setDefault(True)
        cancel = QPushButton("Cancel")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(QLabel("Grouped parts must be adjacent in the "
                              "score; a part can be in one group only."))
        root.addLayout(buttons)

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

        if group is not None:
            pids = [self._from.itemData(i)
                    for i in range(self._from.count())]
            self._from.setCurrentIndex(pids.index(group.parts[0]))
            self._to.setCurrentIndex(pids.index(group.parts[-1]))
            self._symbol.setCurrentText(group.symbol)
            self._join.setChecked(group.join_barlines)

    def group(self) -> StaffGroup:
        lo = min(self._from.currentIndex(), self._to.currentIndex())
        hi = max(self._from.currentIndex(), self._to.currentIndex())
        return StaffGroup(
            parts=tuple(PartId(p.part_id) for p in self._parts[lo:hi + 1]),
            symbol=self._symbol.currentText(),
            join_barlines=self._join.isChecked(),
        )
