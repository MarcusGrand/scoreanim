"""Effects panel (M4.8): the *Appearance & Effects* section's body.

Document-wide effect controls: the Effect dropdown (enumerates the
preset registry, sets `default_effect`), pop's four knobs (Amplitude,
Settle, note-value, Peak offset — ms in the UI, seconds in the doc),
plus Floor opacity and Sweep, moved in from the inspector. Every
control commits exactly ONE command per user gesture. The four number
fields preview as you type (`ui/live_field.py`): the stage shows the
amplitude, the settle, the shift and the ghost opacity on every
keystroke, and the typing session still lands as one undo entry. The
checkbox and the dropdown have no half-typed state, so they commit
outright. `sync_from_document` resyncs and never re-executes.

Two Marcus rulings (2026-07-25): options another option renders
obsolete gray out (`_update_enabled` — the pop knobs while nothing
resolves to pop; Settle while note-value is on), and a Reset button
restores the pre-M4 defaults as ONE undo step (ResetEffectSettings;
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

# pop's authored defaults, mirrored for display when the doc is sparse
# (the values presets.build_presets falls back to)
_POP_DEFAULTS = {"scale": 1.25, "settle": 0.25, "peak_offset": 0.0,
                 "note_value": False}


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
            "amplitude 1.25, settle 0.25 s, peak offset 0) — one undo "
            "step; Floor opacity and Sweep are untouched")
        self._reset_button.clicked.connect(self._commit_reset)

        self._amplitude = LiveField(self._amplitude_spin, app_state,
                                    self._amplitude_edit, self._update_enabled)
        self._settle = LiveField(self._settle_spin, app_state,
                                 self._settle_edit, self._update_enabled)
        self._peak = LiveField(self._peak_spin, app_state, self._peak_edit,
                               self._update_enabled)
        self._floor = LiveField(self._floor_spin, app_state, self._floor_edit,
                                self._update_enabled)
        # the tuple is what holds the fields alive, and the test scans it
        self.live_fields = (self._amplitude, self._settle, self._peak,
                            self._floor)

        form = QFormLayout(self)
        form.setContentsMargins(8, 2, 8, 6)
        form.addRow("Effect", self._effect_combo)
        form.addRow("Amplitude", self._amplitude_spin)
        form.addRow("Settle", self._settle_spin)
        form.addRow(self._note_value_box)
        form.addRow("Peak offset", self._peak_spin)
        form.addRow(self._reset_button)
        form.addRow("Floor opacity", self._floor_spin)
        form.addRow(self._sweep_box)
        self._update_enabled()

    # -- document sync ---------------------------------------------------------

    def _pop_param(self, doc: ProjectDoc, key: str):
        """Always says WHICH document it read. The two callers need
        different ones: an edit guard reads the committed document (`doc`
        hands a live field back its own preview, and it would then never
        commit), while what is grayed out follows what is showing."""
        params = doc.style.effect_params.get("pop", {})
        return params.get(key, _POP_DEFAULTS[key])

    def _update_enabled(self) -> None:
        """Gray out options another option renders obsolete (Marcus,
        2026-07-25). The pop knobs are inert while NOTHING resolves to
        pop (no document default, no part/element rule); Settle is
        additionally inert under note-value, where every stretchable
        element settles over its own engraved length (an element
        without a duration keeps timescale 1.0, but none of those are
        scalable kinds, so the knob has no visible effect). The stored
        values are untouched — disabling is display state only."""
        style = self._state.doc.style
        pop_used = (style.default_effect == "pop"
                    or any(r.effect == "pop"
                           for r in style.parts.values())
                    or any(r.effect == "pop"
                           for r in style.elements.values()))
        note_value = bool(self._pop_param(self._state.doc, "note_value"))
        # set_enabled, not setEnabled: a live field is never grayed out
        # from under the cursor (disabling drops focus, and focus-out
        # commits).
        self._amplitude.set_enabled(pop_used)
        self._settle.set_enabled(pop_used and not note_value)
        self._note_value_box.setEnabled(pop_used)
        self._peak.set_enabled(pop_used)
        at_defaults = (style.default_effect is None
                       and "pop" not in style.effect_params)
        self._reset_button.setEnabled(not at_defaults)

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
        for field, key, factor in ((self._amplitude, "scale", 1.0),
                                   (self._settle, "settle", 1.0),
                                   (self._peak, "peak_offset", 1000.0)):
            field.resync(float(self._pop_param(doc, key)) * factor)
        self._note_value_box.blockSignals(True)
        self._note_value_box.setChecked(
            bool(self._pop_param(doc, "note_value")))
        self._note_value_box.blockSignals(False)

        self._floor.resync(doc.style.floor_opacity)
        self._sweep_box.blockSignals(True)
        self._sweep_box.setChecked(doc.style.reveal_mode
                                   is RevealMode.CONTINUOUS)
        self._sweep_box.blockSignals(False)
        self._update_enabled()

    # -- what each number field means by a value -------------------------------
    #
    # One function per field, called by both its preview and its commit,
    # so the two can never ask for different edits. All four read the
    # COMMITTED document (see _pop_param). None means "changes nothing".

    def _amplitude_edit(self, value: float) -> Command | None:
        if abs(value - float(self._pop_param(self._state.committed,
                                             "scale"))) < 1e-9:
            return None
        return SetEffectParam("pop", "scale", value)

    def _settle_edit(self, value: float) -> Command | None:
        if abs(value - float(self._pop_param(self._state.committed,
                                             "settle"))) < 1e-9:
            return None
        return SetEffectParam("pop", "settle", value)

    def _peak_edit(self, value: float) -> Command | None:
        """ms in the UI, seconds in the document — the one place a typed
        peak offset becomes document intent."""
        seconds = value / 1000.0
        if abs(seconds - float(self._pop_param(self._state.committed,
                                               "peak_offset"))) < 1e-9:
            return None
        return SetEffectParam("pop", "peak_offset", seconds)

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
        if checked == bool(self._pop_param(self._state.committed,
                                           "note_value")):
            return
        self._state.execute(SetEffectParam("pop", "note_value", checked))
        self._update_enabled()

    def _commit_reset(self) -> None:
        style = self._state.doc.style
        if style.default_effect is None and "pop" not in style.effect_params:
            return                       # already at defaults: no-op
        self._state.execute(ResetEffectSettings())
        self.sync_from_document(self._state.doc)
