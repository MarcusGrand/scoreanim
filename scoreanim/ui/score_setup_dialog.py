"""Score Setup dialog (Phase 12.4): the load-time layout choices a dense
score needs to lay out — condense like parts, bracket groups, hide empty
staves.

Unlike the per-action Staff Groups dialog, this is a BATCH editor (ruling
c): choices accumulate in a pending state and OK applies them as ONE
ApplyScoreSetup command — one undo step and exactly one re-engrave. This
matters because an orchestral score re-engraves slowly (complex2 ~20 s),
so re-engraving per action would stall repeatedly. Cancel discards.

Offered automatically when a freshly opened score overflows its page
(the load already flags 'system-overflow'), and on demand via
Parts → Score Setup….
"""
from __future__ import annotations

import re

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPushButton, QVBoxLayout)

from scoreanim.core.project import ApplyScoreSetup, CondenseGroup
from scoreanim.core.score.identity import PartId
from scoreanim.ui.staff_groups_dialog import _GroupEditor

_SYMBOLS = ("bracket", "brace", "line", "square")


def default_condense_name(names: tuple[str, ...]) -> str:
    """"Flute 1" + "Flute 2" → "Flute 1.2"; falls back to the first name
    when the parts do not share a "<prefix><number>" shape."""
    parsed = [re.match(r"^(.*?)(\d+)\s*$", n.strip()) for n in names]
    if names and all(parsed) and len({m.group(1) for m in parsed}) == 1:
        return parsed[0].group(1) + ".".join(m.group(2) for m in parsed)
    return names[0] if names else ""


class ScoreSetupDialog(QDialog):
    def __init__(self, app_state, parts, parent=None) -> None:
        """`parts`: the loaded score's PartInfos in score order."""
        super().__init__(parent)
        self.setWindowTitle("Score Setup")
        self._app_state = app_state
        self._parts = tuple(parts)
        self._order = tuple(PartId(p.part_id) for p in self._parts)
        self._names = {PartId(p.part_id): p.name for p in self._parts}

        # pending state, seeded from the live document; nothing is applied
        # until OK (batch — ruling c)
        doc = app_state.doc
        self._condense = list(doc.condense_groups)
        self._groups = list(doc.staff_groups)

        self._hide = QCheckBox("Hide staves that are empty for a whole system")
        self._hide.setChecked(doc.hide_empty_staves)

        self._condense_list = QListWidget()
        self._groups_list = QListWidget()

        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "Reduce the staff count so the score lays out: condense like "
            "parts onto one staff, and/or hide empty staves."))
        root.addWidget(self._hide)
        root.addWidget(self._make_manager(
            "Condensed parts (merged onto one staff)", self._condense_list,
            self._on_condense_add, self._on_condense_edit,
            self._on_condense_remove, "_condense_btns"))
        root.addWidget(self._make_manager(
            "Staff groups (brackets / joined barlines)", self._groups_list,
            self._on_group_add, self._on_group_edit, self._on_group_remove,
            "_group_btns"))

        ok = QPushButton("OK")
        ok.setDefault(True)
        cancel = QPushButton("Cancel")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root.addLayout(buttons)
        ok.clicked.connect(self._on_ok)
        cancel.clicked.connect(self.reject)

        self._rebuild()

    # -- manager scaffolding ----------------------------------------------

    def _make_manager(self, title, list_widget, on_add, on_edit, on_remove,
                      btns_attr) -> QGroupBox:
        box = QGroupBox(title)
        add = QPushButton("Add…")
        edit = QPushButton("Edit…")
        remove = QPushButton("Remove")
        add.clicked.connect(lambda: (on_add(), self._rebuild()))
        edit.clicked.connect(lambda: (on_edit(), self._rebuild()))
        remove.clicked.connect(lambda: (on_remove(), self._rebuild()))
        list_widget.itemDoubleClicked.connect(lambda _: (on_edit(),
                                                         self._rebuild()))
        setattr(self, btns_attr, (edit, remove))
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(edit)
        row.addWidget(remove)
        row.addStretch(1)
        inner = QVBoxLayout(box)
        inner.addWidget(list_widget)
        inner.addLayout(row)
        return box

    def _label_span(self, parts) -> str:
        first = self._names.get(parts[0], parts[0])
        last = self._names.get(parts[-1], parts[-1])
        return first if len(parts) == 1 else f"{first} – {last}"

    def _rebuild(self) -> None:
        self._condense_list.clear()
        for g in self._condense:
            name = g.name or self._label_span(g.parts)
            self._condense_list.addItem(f"{self._label_span(g.parts)} → {name}")
        self._groups_list.clear()
        for g in self._groups:
            barlines = "joined" if g.join_barlines else "separate"
            self._groups_list.addItem(
                f"{self._label_span(g.parts)} · {g.symbol} · {barlines}")
        self._condense_btns[0].setEnabled(self._condense_list.currentRow() >= 0)
        self._condense_btns[1].setEnabled(self._condense_list.currentRow() >= 0)
        self._group_btns[0].setEnabled(self._groups_list.currentRow() >= 0)
        self._group_btns[1].setEnabled(self._groups_list.currentRow() >= 0)

    # -- condense actions (pending) ---------------------------------------

    def _on_condense_add(self) -> None:
        editor = _CondenseEditor(self._parts, group=None, parent=self)
        if editor.exec():
            self._condense.append(editor.group())

    def _on_condense_edit(self) -> None:
        i = self._condense_list.currentRow()
        if i < 0:
            return
        editor = _CondenseEditor(self._parts, group=self._condense[i],
                                 parent=self)
        if editor.exec():
            self._condense[i] = editor.group()

    def _on_condense_remove(self) -> None:
        i = self._condense_list.currentRow()
        if i >= 0:
            del self._condense[i]

    # -- staff-group actions (pending) ------------------------------------

    def _on_group_add(self) -> None:
        editor = _GroupEditor(self._parts, group=None, parent=self)
        if editor.exec():
            self._groups.append(editor.group())

    def _on_group_edit(self) -> None:
        i = self._groups_list.currentRow()
        if i < 0:
            return
        editor = _GroupEditor(self._parts, group=self._groups[i], parent=self)
        if editor.exec():
            self._groups[i] = editor.group()

    def _on_group_remove(self) -> None:
        i = self._groups_list.currentRow()
        if i >= 0:
            del self._groups[i]

    # -- commit -----------------------------------------------------------

    def _on_ok(self) -> None:
        """One command → one undo step → one re-engrave (ruling c)."""
        if self._app_state.execute(ApplyScoreSetup(
                tuple(self._condense), tuple(self._groups),
                self._hide.isChecked(), self._order)):
            self.accept()
        # a validation error keeps the dialog open (status bar shows why)


class _CondenseEditor(QDialog):
    """One condense group: a From/To part range (contiguous by
    construction) plus the combined label (defaulted from the parts)."""

    def __init__(self, parts, group: CondenseGroup | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Condensed Parts" if group
                            else "Condense Parts")
        self._parts = tuple(parts)

        self._from = QComboBox()
        self._to = QComboBox()
        for p in self._parts:
            self._from.addItem(p.name, PartId(p.part_id))
            self._to.addItem(p.name, PartId(p.part_id))
        self._name = QLineEdit()
        self._abbr = QLineEdit()
        self._from.currentIndexChanged.connect(self._refresh_default_name)
        self._to.currentIndexChanged.connect(self._refresh_default_name)

        form = QFormLayout()
        form.addRow("From part:", self._from)
        form.addRow("To part:", self._to)
        form.addRow("Label:", self._name)
        form.addRow("Abbreviation:", self._abbr)

        ok = QPushButton("OK")
        ok.setDefault(True)
        cancel = QPushButton("Cancel")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(QLabel("Merged parts must be adjacent in the score; "
                              "each becomes one voice on a shared staff."))
        root.addLayout(buttons)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

        if group is not None:
            pids = [self._from.itemData(i) for i in range(self._from.count())]
            self._from.setCurrentIndex(pids.index(group.parts[0]))
            self._to.setCurrentIndex(pids.index(group.parts[-1]))
            self._name.setText(group.name)
            self._abbr.setText(group.abbreviation)
        else:
            self._refresh_default_name()

    def _span(self) -> tuple:
        lo = min(self._from.currentIndex(), self._to.currentIndex())
        hi = max(self._from.currentIndex(), self._to.currentIndex())
        return self._parts[lo:hi + 1]

    def _refresh_default_name(self) -> None:
        span = self._span()
        self._name.setText(default_condense_name(tuple(p.name for p in span)))
        self._abbr.setText(default_condense_name(
            tuple(p.abbreviation for p in span)))

    def group(self) -> CondenseGroup:
        span = self._span()
        return CondenseGroup(
            parts=tuple(PartId(p.part_id) for p in span),
            name=self._name.text().strip(),
            abbreviation=self._abbr.text().strip(),
        )
