"""One preset's knobs: its heading, its rows, and the commands they
commit.

Effects are data (rule 6), and so are their knobs. A preset with
options is a `Knobs` list here plus one entry in the panel's table —
never a second code path. Three kinds cover everything the presets ask
for so far:

- `Number` — a spinbox that previews as you type (`ui/live_field.py`).
  `factor` is UI units per document unit, which is how Peak offset
  shows whole milliseconds over seconds in the document.
- `Check` — a checkbox, which has no half-typed state and so commits
  outright. `beside` puts it on another knob's row instead of its own,
  the way "Entire note value" sits beside the duration it replaces.
- `grayed_by` on a Number names the key that renders it obsolete: a
  duration grays out while its "Entire note value" is on (Marcus,
  2026-07-25).

Every knob carries its own default — the value `presets.build_presets`
falls back to when the document is sparse. That default is what the
panel shows, what a no-op guard compares against, and what tells Reset
whether there is anything to clear.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QSpinBox, QWidget)

from scoreanim.core.project import Command, ProjectDoc, SetEffectParam
from scoreanim.ui.app_state import AppState
from scoreanim.ui.live_field import LiveField


@dataclass(frozen=True)
class Number:
    """A number knob. `integer` picks a whole-number box (Peak offset in
    ms); everything else is a two-decimal float box."""
    label: str
    key: str
    default: float
    minimum: float
    maximum: float
    step: float
    tooltip: str
    suffix: str = ""
    factor: float = 1.0             # UI units per document unit
    integer: bool = False
    grayed_by: str | None = None    # the key that makes this knob obsolete


@dataclass(frozen=True)
class Check:
    """A checkbox knob. `beside` names the knob whose row it shares; on
    its own it takes a full row with no label."""
    text: str
    key: str
    default: bool
    tooltip: str
    beside: str | None = None


Knob = Number | Check


class PresetKnobs:
    """The knobs of ONE preset: the widgets, the live fields, and the
    single command each gesture commits. It adds its own rows to the
    panel's form and remembers where they landed, which is what shows
    and hides the block as a unit."""

    def __init__(self, preset: str, title: str, knobs: Iterable[Knob],
                 state: AppState, form: QFormLayout,
                 on_change: Callable[[], None]) -> None:
        self.preset = preset
        self.title = title
        self._knobs = tuple(knobs)
        self._state = state
        self._on_change = on_change
        self._by_key = {knob.key: knob for knob in self._knobs}
        self.defaults = {knob.key: knob.default for knob in self._knobs}
        self.spins: dict[str, QDoubleSpinBox | QSpinBox] = {}
        self.boxes: dict[str, QCheckBox] = {}
        self.fields: dict[str, LiveField] = {}
        for knob in self._knobs:
            if isinstance(knob, Number):
                self._build_number(knob)
            else:
                self._build_check(knob)
        self.rows = self._add_rows(form)

    # -- widgets ---------------------------------------------------------------

    def _build_number(self, knob: Number) -> None:
        spin: QDoubleSpinBox | QSpinBox
        if knob.integer:
            spin = QSpinBox()
            spin.setRange(int(knob.minimum), int(knob.maximum))
            spin.setSingleStep(int(knob.step))
        else:
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setRange(knob.minimum, knob.maximum)
            spin.setSingleStep(knob.step)
        spin.setSuffix(knob.suffix)
        spin.setToolTip(knob.tooltip)
        self.spins[knob.key] = spin
        self.fields[knob.key] = LiveField(
            spin, self._state, lambda value, k=knob: self._edit(k, value),
            self._on_change)

    def _build_check(self, knob: Check) -> None:
        box = QCheckBox(knob.text)
        box.setToolTip(knob.tooltip)
        box.toggled.connect(lambda checked, k=knob: self._commit_check(k,
                                                                      checked))
        self.boxes[knob.key] = box

    def _add_rows(self, form: QFormLayout) -> tuple[int, ...]:
        """A heading plus the knob rows. The heading names the effect the
        block belongs to, which is what keeps two "Duration" rows apart
        when a part rule puts two effects in use at once."""
        self.header = QLabel(self.title)
        font = self.header.font()
        font.setBold(True)
        self.header.setFont(font)
        form.addRow(self.header)
        rows = [form.rowCount() - 1]
        beside = {knob.beside: knob for knob in self._knobs
                  if isinstance(knob, Check) and knob.beside is not None}
        for knob in self._knobs:
            if isinstance(knob, Check) and knob.beside is not None:
                continue                       # drawn on its knob's row
            if isinstance(knob, Check):
                form.addRow(self.boxes[knob.key])
            else:
                companion = beside.get(knob.key)
                widget: QWidget = self.spins[knob.key]
                if companion is not None:
                    widget = _pair(widget, self.boxes[companion.key])
                form.addRow(knob.label, widget)
            rows.append(form.rowCount() - 1)
        return tuple(rows)

    # -- document ---------------------------------------------------------------

    def param(self, doc: ProjectDoc, key: str):
        """This preset's stored value for a knob, or the knob's own
        default. The caller says WHICH document it read: an edit guard
        reads the committed one (`doc` hands a live field back its own
        preview, and it would then never commit), while what is grayed
        out follows what is showing."""
        params = doc.style.effect_params.get(self.preset, {})
        return params.get(key, self.defaults[key])

    def has_params(self, doc: ProjectDoc) -> bool:
        """Anything stored for this preset — what lights Reset up."""
        return self.preset in doc.style.effect_params

    def previewing(self) -> bool:
        """A knob here is mid-edit, so the block must not be hidden."""
        return any(field.previewing() for field in self.fields.values())

    def set_visible(self, form: QFormLayout, visible: bool) -> None:
        """Show or hide the whole block. Never hides a field being typed
        in: hiding drops focus, and focus-out commits — the same trap
        `set_enabled` avoids. The next update after the edit ends puts it
        right."""
        if not visible and self.previewing():
            return
        for row in self.rows:
            form.setRowVisible(row, visible)

    def update_display(self, doc: ProjectDoc) -> None:
        """Gray out the knobs another knob has made obsolete.
        `set_enabled`, not `setEnabled`: a live field is never grayed out
        from under the cursor."""
        for knob in self._knobs:
            if isinstance(knob, Number) and knob.grayed_by is not None:
                self.fields[knob.key].set_enabled(
                    not bool(self.param(doc, knob.grayed_by)))

    def resync(self, doc: ProjectDoc) -> None:
        """Show what the document says; a field with a live edit keeps
        its number (see `LiveField.resync`)."""
        for key, field in self.fields.items():
            knob = self._by_key[key]
            assert isinstance(knob, Number)
            field.resync(float(self.param(doc, key)) * knob.factor)
        for key, box in self.boxes.items():
            box.blockSignals(True)
            box.setChecked(bool(self.param(doc, key)))
            box.blockSignals(False)

    # -- what a value means (one command per gesture) ---------------------------

    def _edit(self, knob: Number, value: float) -> Command | None:
        """The one function both a number knob's preview and its commit
        call, so the two can never ask for different edits. None means
        "changes nothing"."""
        stored = value / knob.factor
        if abs(stored - float(self.param(self._state.committed,
                                         knob.key))) < 1e-9:
            return None
        return SetEffectParam(self.preset, knob.key, stored)

    def _commit_check(self, knob: Check, checked: bool) -> None:
        if checked == bool(self.param(self._state.committed, knob.key)):
            return
        self._state.execute(SetEffectParam(self.preset, knob.key, checked))
        self._on_change()


def _pair(spin: QWidget, box: QCheckBox) -> QWidget:
    """Two controls on one line: type a number, or hand the job to the
    checkbox beside it."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(spin)
    layout.addWidget(box)
    layout.addStretch(1)
    return row
