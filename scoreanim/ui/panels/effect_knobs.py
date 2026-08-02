"""One group of knobs: its heading, its rows, and the commands they
commit.

Effects are data (rule 6), and so are their knobs. A preset with
options is a `Knobs` list here plus one entry in the panel's table —
never a second code path. Four kinds cover everything the presets ask
for so far:

- `Number` — a spinbox that previews as you type (`ui/live_field.py`).
  `factor` is UI units per document unit, which is how Peak offset
  shows whole milliseconds over seconds in the document.
- `Check` — a checkbox, which has no half-typed state and so commits
  outright. `beside` puts it on another knob's row instead of its own,
  the way "Entire note value" sits beside the duration it replaces.
- `Color` — a swatch button that opens the colour dialog, storing
  "#rrggbb" (the selection panel's pattern). Like a checkbox it has no
  half-chosen state: the dialog either returns a colour or it does not.
- `Choice` — a dropdown over a few named options, storing the chosen
  option's own word — the glow's two shapes.
- `grayed_by` on a Number names the key that renders it obsolete: a
  duration grays out while its "Entire note value" is on (Marcus,
  2026-07-25). `enabled_by` is its mirror — the knob is live only while
  another key is on, which is how Quiet and Loud wait for Amount.
- `forced_by` on a Check names the key that turns it on regardless: the
  box then shows checked and grayed, because that IS what the effect is
  doing (Marcus, 2026-08-01 — "Follow volume" forces "Entire note
  value"). The document is left alone; core is still the one that
  decides, and this only stops the panel from saying otherwise.

Every knob carries its own default — the value the consumer falls back
to when the document is sparse. That default is what the panel shows,
what a no-op guard compares against, and what tells Reset whether there
is anything to clear.

WHERE a group's values live is the group's `store`. A preset's knobs
read `style.effect_params[preset]` and commit `SetEffectParam`; the
volume response reads `style.volume` and commits `SetVolumeParam`. Same
widgets, same live-field rules, same one-command-per-gesture — only the
document field differs, so it is a small object, not a second class.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Protocol

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QLabel, QPushButton, QSpinBox, QWidget)

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
    enabled_by: str | None = None   # the key that has to be on for this one


@dataclass(frozen=True)
class Check:
    """A checkbox knob. `beside` names the knob whose row it shares; on
    its own it takes a full row with no label. `forced_by` names the key
    that turns this one on whatever the document says."""
    text: str
    key: str
    default: bool
    tooltip: str
    beside: str | None = None
    forced_by: str | None = None


@dataclass(frozen=True)
class Color:
    """A colour knob: a swatch showing the colour, opening the colour
    dialog. Stored as "#rrggbb"."""
    label: str
    key: str
    default: str
    tooltip: str
    title: str = "Colour"           # the dialog's own title


@dataclass(frozen=True)
class Choice:
    """A few named options, one of them stored. `options` is
    (what the document holds, what the user reads)."""
    label: str
    key: str
    default: str
    options: tuple[tuple[str, str], ...]
    tooltip: str


Knob = Number | Check | Color | Choice


class KnobStore(Protocol):
    """Where one group's values live in the document, and what one edit
    of them costs — the only thing that differs between groups."""

    def stored(self, doc: ProjectDoc) -> Mapping[str, object]:
        """This group's raw entry; empty when the document is silent."""

    def has_values(self, doc: ProjectDoc) -> bool:
        """Anything stored at all — what lights Reset up."""

    def command(self, key: str, value: float | int | bool | None) -> Command:
        """The ONE command a gesture on this group commits."""


@dataclass(frozen=True)
class EffectParamStore:
    """One preset's knobs: the sparse `style.effect_params` map."""
    preset: str

    def stored(self, doc: ProjectDoc) -> Mapping[str, object]:
        return doc.style.effect_params.get(self.preset, {})

    def has_values(self, doc: ProjectDoc) -> bool:
        return self.preset in doc.style.effect_params

    def command(self, key: str,
                value: float | int | bool | None) -> Command:
        return SetEffectParam(self.preset, key, value)


class KnobGroup:
    """The knobs of ONE group: the widgets, the live fields, and the
    single command each gesture commits. It adds its own rows to the
    panel's form and remembers where they landed, which is what shows
    and hides the block as a unit."""

    def __init__(self, store: KnobStore, title: str, knobs: Iterable[Knob],
                 state: AppState, form: QFormLayout,
                 on_change: Callable[[], None]) -> None:
        self.store = store
        self.title = title
        self._knobs = tuple(knobs)
        self._state = state
        self._on_change = on_change
        self._by_key = {knob.key: knob for knob in self._knobs}
        self.defaults = {knob.key: knob.default for knob in self._knobs}
        self.spins: dict[str, QDoubleSpinBox | QSpinBox] = {}
        self.boxes: dict[str, QCheckBox] = {}
        self.fields: dict[str, LiveField] = {}
        self.swatches: dict[str, QPushButton] = {}
        self.combos: dict[str, QComboBox] = {}
        for knob in self._knobs:
            if isinstance(knob, Number):
                self._build_number(knob)
            elif isinstance(knob, Check):
                self._build_check(knob)
            elif isinstance(knob, Color):
                self._build_color(knob)
            else:
                self._build_choice(knob)
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

    def _build_color(self, knob: Color) -> None:
        button = QPushButton()
        button.setToolTip(knob.tooltip)
        button.clicked.connect(lambda _=False, k=knob: self._pick_color(k))
        self.swatches[knob.key] = button

    def _build_choice(self, knob: Choice) -> None:
        combo = QComboBox()
        for stored, shown in knob.options:
            combo.addItem(shown, stored)
        combo.setToolTip(knob.tooltip)
        # activated is user-only, so a resync can never re-execute
        combo.activated.connect(lambda _i, k=knob: self._commit_choice(k))
        self.combos[knob.key] = combo

    def _add_rows(self, form: QFormLayout) -> tuple[int, ...]:
        """A heading plus the knob rows. The heading names what the block
        belongs to, which is what keeps two "Duration" rows apart when a
        part rule puts two effects in use at once."""
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
                widget: QWidget = self._widget_for(knob)
                if companion is not None:
                    widget = _pair(widget, self.boxes[companion.key])
                form.addRow(knob.label, widget)
            rows.append(form.rowCount() - 1)
        return tuple(rows)

    def _widget_for(self, knob: Knob) -> QWidget:
        if isinstance(knob, Color):
            return self.swatches[knob.key]
        if isinstance(knob, Choice):
            return self.combos[knob.key]
        return self.spins[knob.key]

    # -- document ---------------------------------------------------------------

    def param(self, doc: ProjectDoc, key: str):
        """This group's stored value for a knob, or the knob's own
        default. The caller says WHICH document it read: an edit guard
        reads the committed one (`doc` hands a live field back its own
        preview, and it would then never commit), while what is grayed
        out follows what is showing.

        A checkbox another knob has forced on reads True whatever is
        stored, so the panel shows what the effect is actually doing —
        and so does everything downstream of it, like the duration that
        grays out while the note value is on."""
        knob = self._by_key[key]
        if (isinstance(knob, Check) and knob.forced_by is not None
                and bool(self.param(doc, knob.forced_by))):
            return True
        return self.store.stored(doc).get(key, self.defaults[key])

    def has_params(self, doc: ProjectDoc) -> bool:
        """Anything stored for this group — what lights Reset up."""
        return self.store.has_values(doc)

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
        """Gray out the knobs another knob has made obsolete, and the
        ones waiting on a knob that is off. `set_enabled`, not
        `setEnabled`: a live field is never grayed out from under the
        cursor. A checkbox has no such trap — there is nothing
        half-typed in it — so a forced one is disabled outright.

        A colour or a choice has nothing to gray out: neither is ever
        made obsolete by another knob today."""
        for knob in self._knobs:
            if isinstance(knob, (Color, Choice)):
                continue
            if isinstance(knob, Check):
                if knob.forced_by is not None:
                    self.boxes[knob.key].setEnabled(
                        not bool(self.param(doc, knob.forced_by)))
                continue
            if knob.grayed_by is not None:
                self.fields[knob.key].set_enabled(
                    not bool(self.param(doc, knob.grayed_by)))
            elif knob.enabled_by is not None:
                self.fields[knob.key].set_enabled(
                    bool(self.param(doc, knob.enabled_by)))

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
        for key, button in self.swatches.items():
            _paint_swatch(button, str(self.param(doc, key)))
        for key, combo in self.combos.items():
            index = combo.findData(str(self.param(doc, key)))
            combo.blockSignals(True)
            # a shape from a newer build, or a hand-edited word: show
            # the first option rather than lying about a match
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)

    # -- what a value means (one command per gesture) ---------------------------

    def _edit(self, knob: Number, value: float) -> Command | None:
        """The one function both a number knob's preview and its commit
        call, so the two can never ask for different edits. None means
        "changes nothing"."""
        stored = value / knob.factor
        if abs(stored - float(self.param(self._state.committed,
                                         knob.key))) < 1e-9:
            return None
        return self.store.command(knob.key, stored)

    def _commit_check(self, knob: Check, checked: bool) -> None:
        if checked == bool(self.param(self._state.committed, knob.key)):
            return
        self._state.execute(self.store.command(knob.key, checked))
        self._on_change()

    def _pick_color(self, knob: Color) -> None:
        """One dialog, one command. Cancel returns an invalid colour and
        nothing is committed — there is no half-chosen state."""
        current = QColor(str(self.param(self._state.committed, knob.key)))
        picked = QColorDialog.getColor(current, self.swatches[knob.key],
                                       knob.title)
        if not picked.isValid() or picked.name() == current.name():
            return
        self._state.execute(self.store.command(knob.key, picked.name()))
        self._on_change()

    def _commit_choice(self, knob: Choice) -> None:
        chosen = self.combos[knob.key].currentData()
        if chosen == str(self.param(self._state.committed, knob.key)):
            return
        self._state.execute(self.store.command(knob.key, chosen))
        self._on_change()


def _paint_swatch(button: QPushButton, color: str) -> None:
    """The button IS the swatch: filled with the colour, labelled with
    it, and with readable text over either a light or a dark fill."""
    shown = QColor(color)
    if not shown.isValid():
        shown = QColor("#000000")       # a hand-edited word, shown plainly
    ink = "#000000" if shown.lightness() > 127 else "#ffffff"
    button.setText(color)
    button.setStyleSheet(f"background-color: {shown.name()}; color: {ink};")


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
