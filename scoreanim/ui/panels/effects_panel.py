"""Effects panel (M4.8): the *Appearance & Effects* section's body.

Document-wide effect controls: the Effect dropdown (enumerates the
preset registry, sets `default_effect`), pop's four knobs (Amplitude,
Settle, note-value, Peak offset — ms in the UI, seconds in the doc),
plus Floor opacity and Sweep, moved in from the inspector with their
commit wiring verbatim. Every control commits exactly ONE command per
user gesture (spinboxes on editingFinished with the epsilon no-op
guard); `sync_from_document` resyncs with the blockSignals idiom and
never re-executes — the floor-opacity pattern throughout.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QFormLayout, QSpinBox, QWidget)

from scoreanim.core.animation import DEFAULT_EFFECT, PRESETS, RevealMode
from scoreanim.core.project import (ProjectDoc, SetDefaultEffect,
                                    SetEffectParam, SetFloorOpacity,
                                    SetRevealMode)
from scoreanim.ui.app_state import AppState

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
        self._amplitude_spin.setKeyboardTracking(False)
        self._amplitude_spin.setToolTip(
            "Pop scale factor at the onset (1.0 = no bump)")
        self._amplitude_spin.editingFinished.connect(self._commit_amplitude)

        self._settle_spin = QDoubleSpinBox()
        self._settle_spin.setDecimals(2)
        self._settle_spin.setRange(0.01, 5.0)
        self._settle_spin.setSingleStep(0.05)
        self._settle_spin.setSuffix(" s")
        self._settle_spin.setKeyboardTracking(False)
        self._settle_spin.setToolTip(
            "Seconds the pop takes to relax back to 1.0")
        self._settle_spin.editingFinished.connect(self._commit_settle)

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
        self._peak_spin.setKeyboardTracking(False)
        self._peak_spin.setToolTip(
            "Shifts the whole pop, including when the note appears — at "
            "a negative offset every note becomes visible that early")
        self._peak_spin.editingFinished.connect(self._commit_peak)

        # Floor opacity + Sweep: moved in from the inspector (M1.4
        # wiring verbatim — keyboard tracking off, editingFinished,
        # epsilon guard).
        self._floor_spin = QDoubleSpinBox()
        self._floor_spin.setDecimals(2)
        self._floor_spin.setSingleStep(0.05)
        self._floor_spin.setRange(0.0, 1.0)
        self._floor_spin.setKeyboardTracking(False)
        self._floor_spin.setToolTip("Opacity of unrevealed animated ink; "
                                    "0 hides it until onset")
        self._floor_spin.editingFinished.connect(self._commit_floor)

        self._sweep_box = QCheckBox("Sweep")
        self._sweep_box.setToolTip("Continuous reveal sweep; unchecked "
                                   "steps at musical onsets")
        self._sweep_box.toggled.connect(
            lambda checked: self._state.execute(SetRevealMode(
                RevealMode.CONTINUOUS if checked else RevealMode.STEPPED)))

        form = QFormLayout(self)
        form.setContentsMargins(8, 2, 8, 6)
        form.addRow("Effect", self._effect_combo)
        form.addRow("Amplitude", self._amplitude_spin)
        form.addRow("Settle", self._settle_spin)
        form.addRow(self._note_value_box)
        form.addRow("Peak offset", self._peak_spin)
        form.addRow("Floor opacity", self._floor_spin)
        form.addRow(self._sweep_box)

    # -- document sync ---------------------------------------------------------

    def _pop_param(self, key: str):
        params = self._state.doc.style.effect_params.get("pop", {})
        return params.get(key, _POP_DEFAULTS[key])

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

        params = doc.style.effect_params.get("pop", {})
        for spin, key, factor in ((self._amplitude_spin, "scale", 1.0),
                                  (self._settle_spin, "settle", 1.0),
                                  (self._peak_spin, "peak_offset", 1000.0)):
            spin.blockSignals(True)
            value = float(params.get(key, _POP_DEFAULTS[key])) * factor
            spin.setValue(round(value) if isinstance(spin, QSpinBox)
                          else value)
            spin.blockSignals(False)
        self._note_value_box.blockSignals(True)
        self._note_value_box.setChecked(
            bool(params.get("note_value", False)))
        self._note_value_box.blockSignals(False)

        self._floor_spin.blockSignals(True)
        self._floor_spin.setValue(doc.style.floor_opacity)
        self._floor_spin.blockSignals(False)
        self._sweep_box.blockSignals(True)
        self._sweep_box.setChecked(doc.style.reveal_mode
                                   is RevealMode.CONTINUOUS)
        self._sweep_box.blockSignals(False)

    # -- commit handlers (one command per user gesture) ------------------------

    def _commit_effect(self) -> None:
        name = self._effect_combo.currentText()
        if name == (self._state.doc.style.default_effect or DEFAULT_EFFECT):
            return
        self._state.execute(SetDefaultEffect(name))

    def _commit_amplitude(self) -> None:
        value = self._amplitude_spin.value()
        if abs(value - float(self._pop_param("scale"))) < 1e-9:
            return
        self._state.execute(SetEffectParam("pop", "scale", value))

    def _commit_settle(self) -> None:
        value = self._settle_spin.value()
        if abs(value - float(self._pop_param("settle"))) < 1e-9:
            return
        self._state.execute(SetEffectParam("pop", "settle", value))

    def _commit_note_value(self, checked: bool) -> None:
        if checked == bool(self._pop_param("note_value")):
            return
        self._state.execute(SetEffectParam("pop", "note_value", checked))

    def _commit_peak(self) -> None:
        seconds = self._peak_spin.value() / 1000.0
        if abs(seconds - float(self._pop_param("peak_offset"))) < 1e-9:
            return
        self._state.execute(SetEffectParam("pop", "peak_offset", seconds))

    def _commit_floor(self) -> None:
        value = self._floor_spin.value()
        if abs(value - self._state.doc.style.floor_opacity) < 1e-9:
            return
        self._state.execute(SetFloorOpacity(value))
