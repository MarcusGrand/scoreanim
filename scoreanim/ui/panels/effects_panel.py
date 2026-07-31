"""Effects panel (M4.8): the *Appearance & Effects* section's body.

Document-wide effect controls: the Effect dropdown (enumerates the
preset registry, sets `default_effect`), pop's four knobs (Amplitude,
Settle, note-value, Peak offset — ms in the UI, seconds in the doc),
fade's two (Fade time, note-value), plus Floor opacity and Sweep, moved
in from the inspector. Every control commits exactly ONE command per
user gesture. The number fields preview as you type
(`ui/live_field.py`): the stage shows the amplitude, the settle, the
shift, the fade time and the ghost opacity on every keystroke, and the
typing session still lands as one undo entry. The checkboxes and the
dropdown have no half-typed state, so they commit outright.
`sync_from_document` resyncs and never re-executes.

Each preset's knobs read their own entry in `style.effect_params`
through one `_param` reader over the `_DEFAULTS` table — a preset with
knobs is a table entry plus its widgets, never a second code path.

Two Marcus rulings (2026-07-25): options another option renders
obsolete gray out (`_update_enabled` — a preset's knobs while nothing
resolves to that preset; a duration while its note-value is on), and a
Reset button restores the pre-M4 defaults as ONE undo step
(ResetEffectSettings, which clears every knobbed preset together;
Floor opacity and Sweep predate the options and stay put).
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QFormLayout, QPushButton, QSpinBox, QWidget)

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

        self._settle_spin = QDoubleSpinBox()
        self._settle_spin.setDecimals(2)
        self._settle_spin.setRange(0.01, 5.0)
        self._settle_spin.setSingleStep(0.05)
        self._settle_spin.setSuffix(" s")
        self._settle_spin.setToolTip(
            "Seconds the pop takes to relax back to 1.0 — inactive "
            "while 'Animate entire note value' is on (each note then "
            "settles over its own length)")

        self._note_value_box = QCheckBox("Animate entire note value")
        self._note_value_box.setToolTip(
            "Stretch each note's settle over its own duration — a whole "
            "note relaxes slowly, an eighth pops and settles at once")
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

        # fade's two knobs: the same shape as pop's Settle and its
        # note-value box, one preset over.
        self._fade_spin = QDoubleSpinBox()
        self._fade_spin.setDecimals(2)
        self._fade_spin.setRange(0.01, 5.0)
        self._fade_spin.setSingleStep(0.05)
        self._fade_spin.setSuffix(" s")
        self._fade_spin.setToolTip(
            "Seconds the fade takes to rise from the floor to full — "
            "inactive while fade's 'Animate entire note value' is on "
            "(each note then fades over its own length)")

        self._fade_note_value_box = QCheckBox("Animate entire note value")
        self._fade_note_value_box.setToolTip(
            "Stretch each note's fade over its own duration — a whole "
            "note rises slowly, an eighth is up at once")
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
            "amplitude 1.25, settle 0.25 s, peak offset 0, fade time "
            "0.4 s) — one undo step; Floor opacity and Sweep are "
            "untouched")
        self._reset_button.clicked.connect(self._commit_reset)

        self._amplitude = LiveField(self._amplitude_spin, app_state,
                                    self._amplitude_edit, self._update_enabled)
        self._settle = LiveField(self._settle_spin, app_state,
                                 self._settle_edit, self._update_enabled)
        self._peak = LiveField(self._peak_spin, app_state, self._peak_edit,
                               self._update_enabled)
        self._fade = LiveField(self._fade_spin, app_state, self._fade_edit,
                               self._update_enabled)
        self._floor = LiveField(self._floor_spin, app_state, self._floor_edit,
                                self._update_enabled)
        # the tuple is what holds the fields alive, and the test scans it
        self.live_fields = (self._amplitude, self._settle, self._peak,
                            self._fade, self._floor)

        form = QFormLayout(self)
        form.setContentsMargins(8, 2, 8, 6)
        form.addRow("Effect", self._effect_combo)
        form.addRow("Amplitude", self._amplitude_spin)
        form.addRow("Settle", self._settle_spin)
        form.addRow(self._note_value_box)
        form.addRow("Peak offset", self._peak_spin)
        form.addRow("Fade time", self._fade_spin)
        form.addRow(self._fade_note_value_box)
        form.addRow(self._reset_button)
        form.addRow("Floor opacity", self._floor_spin)
        form.addRow(self._sweep_box)
        self._update_enabled()

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

    def _update_enabled(self) -> None:
        """Gray out options another option renders obsolete (Marcus,
        2026-07-25). A preset's knobs are inert while NOTHING resolves
        to it (no document default, no part/element rule); its duration
        knob is additionally inert under its note-value, where every
        stretchable element runs over its own engraved length (an
        element without a duration keeps timescale 1.0, but none of
        those are scalable kinds, so the pop knob has no visible
        effect). The stored values are untouched — disabling is display
        state only."""
        doc = self._state.doc
        pop_used = self._in_use(doc, "pop")
        note_value = bool(self._param(doc, "pop", "note_value"))
        fade_used = self._in_use(doc, "fade")
        fade_note_value = bool(self._param(doc, "fade", "note_value"))
        # set_enabled, not setEnabled: a live field is never grayed out
        # from under the cursor (disabling drops focus, and focus-out
        # commits).
        self._amplitude.set_enabled(pop_used)
        self._settle.set_enabled(pop_used and not note_value)
        self._note_value_box.setEnabled(pop_used)
        self._peak.set_enabled(pop_used)
        self._fade.set_enabled(fade_used and not fade_note_value)
        self._fade_note_value_box.setEnabled(fade_used)
        self._reset_button.setEnabled(not self._at_defaults(doc))

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
        self._update_enabled()

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
        self._update_enabled()

    def _commit_note_value(self, checked: bool) -> None:
        if checked == bool(self._param(self._state.committed,
                                       "pop", "note_value")):
            return
        self._state.execute(SetEffectParam("pop", "note_value", checked))
        self._update_enabled()

    def _commit_fade_note_value(self, checked: bool) -> None:
        if checked == bool(self._param(self._state.committed,
                                       "fade", "note_value")):
            return
        self._state.execute(SetEffectParam("fade", "note_value", checked))
        self._update_enabled()

    def _commit_reset(self) -> None:
        if self._at_defaults(self._state.doc):
            return                       # already at defaults: no-op
        self._state.execute(ResetEffectSettings())
        self.sync_from_document(self._state.doc)
