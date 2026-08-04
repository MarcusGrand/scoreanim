"""One group of knobs: its heading, its rows, and the commands they
commit.

The widget half. What a knob IS — the five types, their defaults, and
the store that says where a group's values live — is
`ui/panels/knob_types.py`; this builds the widgets those types ask for,
keeps them showing what the document says, and turns a gesture on one
of them into exactly one command.

Every knob carries its own default (see `knob_types`), and that default
is what the panel shows, what a no-op guard compares against, and what
tells Reset whether there is anything to clear.

An `Envelope` knob is a canvas rather than a widget with a value, and a
drag on it edits six document keys at once, so the whole of that one
lives in `ui/panels/envelope_row.py`. Here it is built and then
delegated to, like any other row: it resyncs with the rest and hides
with the block.
"""
from __future__ import annotations

from typing import Callable, Iterable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QLabel, QPushButton, QSpinBox, QWidget)

from scoreanim.core.project import Command, ProjectDoc
from scoreanim.ui.app_state import AppState
from scoreanim.ui.live_field import LiveField
from scoreanim.ui.panels.envelope_row import EnvelopeRow
from scoreanim.ui.panels.knob_types import (Check, Choice, Color, Envelope,
                                            Knob, KnobStore, Number)


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
        # An envelope stores nothing of its own, so it has no default to
        # fall back to and never reaches `param`.
        self.defaults = {knob.key: knob.default for knob in self._knobs
                         if not isinstance(knob, Envelope)}
        self.spins: dict[str, QDoubleSpinBox | QSpinBox] = {}
        self.boxes: dict[str, QCheckBox] = {}
        self.fields: dict[str, LiveField] = {}
        self.swatches: dict[str, QPushButton] = {}
        self.combos: dict[str, QComboBox] = {}
        self.envelopes: dict[str, EnvelopeRow] = {}
        for knob in self._knobs:
            if isinstance(knob, Number):
                self._build_number(knob)
            elif isinstance(knob, Check):
                self._build_check(knob)
            elif isinstance(knob, Color):
                self._build_color(knob)
            elif isinstance(knob, Envelope):
                self._build_envelope(knob)
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

    def _build_envelope(self, knob: Envelope) -> None:
        """The canvas and everything it commits, which is a module of
        its own. It reads through THIS group's `param`, so a defaulted
        or forced value reads the same on the picture as in the boxes.
        A group holding one has to be a `MultiKnobStore` (knob_types)."""
        self.envelopes[knob.key] = EnvelopeRow(
            knob, self.store, self._state,   # type: ignore[arg-type]
            self.param, self._on_change)

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
            elif isinstance(knob, Envelope):
                # its own full width, under the header that opens it
                form.addRow(self.envelopes[knob.key].section)
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
        """A knob here is mid-edit, so the block must not be hidden — a
        typed number, or a handle being held on a canvas."""
        return (any(field.previewing() for field in self.fields.values())
                or any(row.dragging() for row in self.envelopes.values()))

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

        A colour, a choice or an envelope has nothing to gray out: none
        of them is ever made obsolete by another knob today."""
        for knob in self._knobs:
            if isinstance(knob, (Color, Choice, Envelope)):
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
        for row in self.envelopes.values():
            row.resync(doc)

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
