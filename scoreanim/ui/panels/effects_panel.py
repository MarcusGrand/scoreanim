"""Effects panel (M4.8): the *Appearance & Effects* section's body.

Document-wide effect controls: the Effect dropdown (enumerates the
preset registry, sets `default_effect`), pop's knobs (Amplitude,
Duration, Peak offset — ms in the UI, seconds in the doc), fade's
(Duration), plus Floor opacity and Sweep, moved in from the inspector.
Every control commits exactly ONE command per user gesture. The number
fields preview as you type (`ui/live_field.py`): the stage shows the
amplitude, the durations, the shift and the ghost opacity on every
keystroke, and the typing session still lands as one undo entry. The
checkboxes and the dropdown have no half-typed state, so they commit
outright. `sync_from_document` resyncs and never re-executes.

Each preset's knobs read their own entry in `style.effect_params`
through one `_param` reader over the `_DEFAULTS` table — a preset with
knobs is a table entry plus its widgets, never a second code path.
Every effect says "Duration" for how long it runs, and "Entire note
value" sits on the duration's own row, as the alternative to typing one
(Marcus, 2026-07-31).

Three Marcus rulings. A preset's options only show while something
resolves to that preset (2026-07-31, `_update_display`): the panel
shows the effect in use, not every effect there is. Within a group,
options another option renders obsolete gray out (2026-07-25): a
duration while its "Entire note value" is on. And Reset restores the
pre-M4 defaults as ONE undo step (ResetEffectSettings, which clears
every knobbed preset together; Floor opacity and Sweep predate the
options and stay put).
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QLabel, QPushButton,
                               QSpinBox, QWidget)

from scoreanim.core.animation import DEFAULT_EFFECT, PRESETS, RevealMode
from scoreanim.core.project import (Command, ProjectDoc, ResetEffectSettings,
                                    SetDefaultEffect, SetEffectParam,
                                    SetFloorOpacity, SetRevealMode)
from scoreanim.ui.app_state import AppState
from scoreanim.ui.live_field import LiveField

# The authored defaults of every preset with knobs here, mirrored for
# display when the doc is sparse (the values presets.build_presets falls
# back to). Reset clears exactly these presets' params.
_DEFAULTS: dict[str, dict[str, object]] = {
    "pop": {"scale": 1.25, "settle": 0.25, "peak_offset": 0.0,
            "note_value": False},
    "fade": {"duration": 0.4, "note_value": False},
}


class EffectsPanel(QWidget):
    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state

        # Document default effect: element override > part rule > THIS.
        self._effect_combo = QComboBox()
        for name in sorted(PRESETS):
            self._effect_combo.addItem(name)
        self._effect_combo.setCurrentText(DEFAULT_EFFECT)
        self._effect_combo.setToolTip(
            "Default effect for every element; per-part and per-element "
            "rules still win")
        # activated fires on USER action only — programmatic resyncs
        # cannot loop back into a command
        self._effect_combo.activated.connect(self._commit_effect)

        self._amplitude_spin = QDoubleSpinBox()
        self._amplitude_spin.setDecimals(2)
        self._amplitude_spin.setRange(0.1, 10.0)
        self._amplitude_spin.setSingleStep(0.05)
        self._amplitude_spin.setToolTip(
            "Pop scale factor at the onset (1.0 = no bump)")

        # The document calls this one "settle"; the UI says Duration,
        # the word every effect uses for how long it runs.
        self._settle_spin = QDoubleSpinBox()
        self._settle_spin.setDecimals(2)
        self._settle_spin.setRange(0.01, 5.0)
        self._settle_spin.setSingleStep(0.05)
        self._settle_spin.setSuffix(" s")
        self._settle_spin.setToolTip(
            "Seconds the pop takes to relax back to 1.0 — inactive "
            "while 'Entire note value' is on (each note then settles "
            "over its own length)")

        self._note_value_box = QCheckBox("Entire note value")
        self._note_value_box.setToolTip(
            "Use each note's own length as the duration — a whole note "
            "relaxes slowly, an eighth pops and settles at once")
        self._note_value_box.toggled.connect(self._commit_note_value)

        # ms in the UI, seconds in the document. The tooltip states the
        # F3 consequence verbatim: the opacity step rides the shift.
        self._peak_spin = QSpinBox()
        self._peak_spin.setRange(-500, 500)
        self._peak_spin.setSingleStep(10)
        self._peak_spin.setSuffix(" ms")
        self._peak_spin.setToolTip(
            "Shifts the whole pop, including when the note appears — at "
            "a negative offset every note becomes visible that early")

        # fade's two knobs: the same duration pair, one preset over.
        self._fade_spin = QDoubleSpinBox()
        self._fade_spin.setDecimals(2)
        self._fade_spin.setRange(0.01, 5.0)
        self._fade_spin.setSingleStep(0.05)
        self._fade_spin.setSuffix(" s")
        self._fade_spin.setToolTip(
            "Seconds the fade takes to rise from the floor to full — "
            "inactive while 'Entire note value' is on (each note then "
            "fades over its own length)")

        self._fade_note_value_box = QCheckBox("Entire note value")
        self._fade_note_value_box.setToolTip(
            "Use each note's own length as the duration — a whole note "
            "rises slowly, an eighth is up at once")
        self._fade_note_value_box.toggled.connect(self._commit_fade_note_value)

        # Floor opacity + Sweep: moved in from the inspector (M1.4).
        self._floor_spin = QDoubleSpinBox()
        self._floor_spin.setDecimals(2)
        self._floor_spin.setSingleStep(0.05)
        self._floor_spin.setRange(0.0, 1.0)
        self._floor_spin.setToolTip("Opacity of unrevealed animated ink; "
                                    "0 hides it until onset")

        self._sweep_box = QCheckBox("Sweep")
        self._sweep_box.setToolTip("Continuous reveal sweep; unchecked "
                                   "steps at musical onsets")
        self._sweep_box.toggled.connect(
            lambda checked: self._state.execute(SetRevealMode(
                RevealMode.CONTINUOUS if checked else RevealMode.STEPPED)))

        # Reset (Marcus, 2026-07-25): back to the pre-M4 defaults —
        # effect "appear", pop params cleared — as ONE undo step.
        # Floor opacity and Sweep predate the M4 options and stay put.
        self._reset_button = QPushButton("Reset")
        self._reset_button.setToolTip(
            "Restore the effect settings to their defaults (appear, "
            "amplitude 1.25, pop duration 0.25 s, peak offset 0, fade "
            "duration 0.4 s) — one undo step; Floor opacity and Sweep "
            "are untouched")
        self._reset_button.clicked.connect(self._commit_reset)

        self._amplitude = LiveField(self._amplitude_spin, app_state,
                                    self._amplitude_edit, self._update_display)
        self._settle = LiveField(self._settle_spin, app_state,
                                 self._settle_edit, self._update_display)
        self._peak = LiveField(self._peak_spin, app_state, self._peak_edit,
                               self._update_display)
        self._fade = LiveField(self._fade_spin, app_state, self._fade_edit,
                               self._update_display)
        self._floor = LiveField(self._floor_spin, app_state, self._floor_edit,
                                self._update_display)
        # the tuple is what holds the fields alive, and the test scans it
        self.live_fields = (self._amplitude, self._settle, self._peak,
                            self._fade, self._floor)
        # which live fields belong to which preset — the visibility guard
        # asks them whether an edit is running
        self._fields_by_preset = {"pop": (self._amplitude, self._settle,
                                          self._peak),
                                  "fade": (self._fade,)}

        self._form = QFormLayout(self)
        self._form.setContentsMargins(8, 2, 8, 6)
        self._form.addRow("Effect", self._effect_combo)
        # Each preset's rows, remembered so they can be shown and hidden
        # as a group. The header names the effect they belong to, which
        # is what keeps two "Duration" rows apart when a part rule puts
        # two effects in use at once.
        self._rows_by_preset = {
            "pop": self._add_group("Pop", (
                ("Amplitude", self._amplitude_spin),
                ("Duration", self._duration_row(self._settle_spin,
                                                self._note_value_box)),
                ("Peak offset", self._peak_spin))),
            "fade": self._add_group("Fade", (
                ("Duration", self._duration_row(self._fade_spin,
                                                self._fade_note_value_box)),)),
        }
        self._form.addRow(self._reset_button)
        self._form.addRow("Floor opacity", self._floor_spin)
        self._form.addRow(self._sweep_box)
        self._update_display()

    # -- form building ---------------------------------------------------------

    def _duration_row(self, spin: QDoubleSpinBox,
                      note_value: QCheckBox) -> QWidget:
        """The duration and its alternative on one line: type a number
        of seconds, or hand the job to the note's own length."""
        row = QWidget()
        box = QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(spin)
        box.addWidget(note_value)
        box.addStretch(1)
        return row

    def _add_group(self, title: str,
                   rows: tuple[tuple[str, QWidget], ...]) -> tuple[int, ...]:
        """A preset's own block: a heading plus its rows. Returns the row
        numbers, which is what shows and hides the block."""
        header = QLabel(title)
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        self._form.addRow(header)
        indexes = [self._form.rowCount() - 1]
        for label, widget in rows:
            self._form.addRow(label, widget)
            indexes.append(self._form.rowCount() - 1)
        return tuple(indexes)

    # -- document sync ---------------------------------------------------------

    def _param(self, doc: ProjectDoc, preset: str, key: str):
        """Always says WHICH document it read. The two callers need
        different ones: an edit guard reads the committed document (`doc`
        hands a live field back its own preview, and it would then never
        commit), while what is grayed out follows what is showing."""
        params = doc.style.effect_params.get(preset, {})
        return params.get(key, _DEFAULTS[preset][key])

    def _in_use(self, doc: ProjectDoc, preset: str) -> bool:
        """Does anything resolve to this preset — the document default,
        a part rule or an element rule? Its params apply to all three."""
        style = doc.style
        return (style.default_effect == preset
                or any(r.effect == preset for r in style.parts.values())
                or any(r.effect == preset for r in style.elements.values()))

    def _update_display(self) -> None:
        """What the panel shows, in two layers.

        A preset's whole block is hidden while NOTHING resolves to it —
        no document default, no part or element rule (Marcus,
        2026-07-31): you see the options of the effect you are using,
        not every effect there is. Inside a block, an option another
        option renders obsolete grays out (Marcus, 2026-07-25): the
        duration under "Entire note value", where every stretchable
        element runs over its own engraved length instead (an element
        without a duration keeps timescale 1.0, but none of those are
        scalable kinds, so the pop knob has no visible effect there).

        The stored values are untouched either way — this is display
        state only."""
        doc = self._state.doc
        for preset in _DEFAULTS:
            self._set_group_visible(preset, self._in_use(doc, preset))
        # set_enabled, not setEnabled: a live field is never grayed out
        # from under the cursor (disabling drops focus, and focus-out
        # commits).
        self._settle.set_enabled(
            not bool(self._param(doc, "pop", "note_value")))
        self._fade.set_enabled(
            not bool(self._param(doc, "fade", "note_value")))
        self._reset_button.setEnabled(not self._at_defaults(doc))

    def _set_group_visible(self, preset: str, visible: bool) -> None:
        """Show or hide one preset's block. Never hides a field being
        typed in: hiding drops focus, and focus-out commits — the same
        trap set_enabled avoids. The next update after the edit ends
        puts it right."""
        if not visible and any(field.previewing()
                               for field in self._fields_by_preset[preset]):
            return
        for row in self._rows_by_preset[preset]:
            self._form.setRowVisible(row, visible)

    def _at_defaults(self, doc: ProjectDoc) -> bool:
        """Nothing for Reset to do: no document default, and no stored
        params for any preset with knobs here."""
        style = doc.style
        return (style.default_effect is None
                and not any(name in style.effect_params for name in _DEFAULTS))

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Resync every control (execute, undo, redo, and load all
        arrive here via the inspector); never re-executes."""
        name = doc.style.default_effect or DEFAULT_EFFECT
        self._effect_combo.blockSignals(True)
        if self._effect_combo.findText(name) < 0:
            # a name from a newer build: show the stored intent rather
            # than silently displaying the wrong preset
            self._effect_combo.addItem(name)
        self._effect_combo.setCurrentText(name)
        self._effect_combo.blockSignals(False)

        # a field with a live edit keeps its number — see LiveField.resync
        for field, preset, key, factor in (
                (self._amplitude, "pop", "scale", 1.0),
                (self._settle, "pop", "settle", 1.0),
                (self._peak, "pop", "peak_offset", 1000.0),
                (self._fade, "fade", "duration", 1.0)):
            field.resync(float(self._param(doc, preset, key)) * factor)
        for box, preset in ((self._note_value_box, "pop"),
                            (self._fade_note_value_box, "fade")):
            box.blockSignals(True)
            box.setChecked(bool(self._param(doc, preset, "note_value")))
            box.blockSignals(False)

        self._floor.resync(doc.style.floor_opacity)
        self._sweep_box.blockSignals(True)
        self._sweep_box.setChecked(doc.style.reveal_mode
                                   is RevealMode.CONTINUOUS)
        self._sweep_box.blockSignals(False)
        self._update_display()

    # -- what each number field means by a value -------------------------------
    #
    # One function per field, called by both its preview and its commit,
    # so the two can never ask for different edits. All five read the
    # COMMITTED document (see _param). None means "changes nothing".

    def _amplitude_edit(self, value: float) -> Command | None:
        if abs(value - float(self._param(self._state.committed,
                                         "pop", "scale"))) < 1e-9:
            return None
        return SetEffectParam("pop", "scale", value)

    def _settle_edit(self, value: float) -> Command | None:
        if abs(value - float(self._param(self._state.committed,
                                         "pop", "settle"))) < 1e-9:
            return None
        return SetEffectParam("pop", "settle", value)

    def _peak_edit(self, value: float) -> Command | None:
        """ms in the UI, seconds in the document — the one place a typed
        peak offset becomes document intent."""
        seconds = value / 1000.0
        if abs(seconds - float(self._param(self._state.committed,
                                           "pop", "peak_offset"))) < 1e-9:
            return None
        return SetEffectParam("pop", "peak_offset", seconds)

    def _fade_edit(self, value: float) -> Command | None:
        if abs(value - float(self._param(self._state.committed,
                                         "fade", "duration"))) < 1e-9:
            return None
        return SetEffectParam("fade", "duration", value)

    def _floor_edit(self, value: float) -> Command | None:
        if abs(value - self._state.committed.style.floor_opacity) < 1e-9:
            return None
        return SetFloorOpacity(value)

    # -- commit handlers (one command per user gesture) ------------------------

    def _commit_effect(self) -> None:
        name = self._effect_combo.currentText()
        if name == (self._state.doc.style.default_effect or DEFAULT_EFFECT):
            return
        self._state.execute(SetDefaultEffect(name))
        self._update_display()

    def _commit_note_value(self, checked: bool) -> None:
        if checked == bool(self._param(self._state.committed,
                                       "pop", "note_value")):
            return
        self._state.execute(SetEffectParam("pop", "note_value", checked))
        self._update_display()

    def _commit_fade_note_value(self, checked: bool) -> None:
        if checked == bool(self._param(self._state.committed,
                                       "fade", "note_value")):
            return
        self._state.execute(SetEffectParam("fade", "note_value", checked))
        self._update_display()

    def _commit_reset(self) -> None:
        if self._at_defaults(self._state.doc):
            return                       # already at defaults: no-op
        self._state.execute(ResetEffectSettings())
        self.sync_from_document(self._state.doc)
