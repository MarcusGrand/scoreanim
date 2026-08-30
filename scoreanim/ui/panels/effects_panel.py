"""Effects panel (M4.8): the *Appearance & Effects* section's body.

Document-wide effect controls: the Effect dropdown (enumerates the
preset registry, sets `default_effect`), a second dropdown for an effect
to run WITH it, each knobbed preset's own block of options, the Volume
response block, plus Reset, Floor opacity, Sweep and Tied notes as
one. Two effects at once are stored as ONE name,
"drop+fade" — the document is unchanged, and a build that does not know
one of the parts still runs the other. Every control commits
exactly ONE command per user gesture. The number fields preview as you
type (`ui/live_field.py`): the stage shows the amplitude, the durations,
the shift and the ghost opacity on every keystroke, and the typing
session still lands as one undo entry. The checkboxes and the dropdown
have no half-typed state, so they commit outright. `sync_from_document`
resyncs and never re-executes.

A block's knobs are DATA — one entry in `ui/panels/effect_blocks.py`,
or a list of its own in `ui/panels/volume_knobs.py` /
`ui/panels/pulse_knobs.py`, built and run by `KnobGroup`
(`ui/panels/effect_knobs.py`). This panel owns what belongs to no single
preset: which effect is the default, which blocks are on screen, Reset,
and the two document-wide controls.

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
                               QFormLayout, QPushButton, QWidget)

from scoreanim.core.animation import (COMBINE_SEP, DEFAULT_EFFECT, PRESETS,
                                      RevealMode, split_effect_name)
from scoreanim.core.project import (Command, ProjectDoc, ResetEffectSettings,
                                    SetDefaultEffect, SetFloorOpacity,
                                    SetRevealMode, SetTiedNotesAsOne)
from scoreanim.ui import panel_style, tips
from scoreanim.ui.app_state import AppState
from scoreanim.ui.live_field import LiveField
from scoreanim.ui.panels.effect_blocks import BLOCKS, STORES
from scoreanim.ui.panels.effect_knobs import KnobGroup
from scoreanim.ui.panels.knob_types import EffectParamStore
from scoreanim.ui.panels import pulse_knobs, volume_knobs

# The "no second effect" entry in the Combine with dropdown. Not a
# preset name, and never stored: the document holds the first effect's
# name alone.
_NO_COMBINE = "(none)"


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
        tips.describe(
            self._effect_combo,
            "Default effect for every element; per-part and per-element "
            "rules still win")
        # activated fires on USER action only — programmatic resyncs
        # cannot loop back into a command
        self._effect_combo.activated.connect(self._commit_effect)

        # A second effect to run WITH the first ("drop+fade"): the two
        # are stored as one name, so nothing about the document changes.
        self._combine_combo = QComboBox()
        tips.describe(
            self._combine_combo,
            "A second effect to run at the same time as the first — the "
            "two are combined property by property")
        self._fill_combine(DEFAULT_EFFECT)
        self._combine_combo.activated.connect(self._commit_effect)

        # Floor opacity + Sweep: moved in from the inspector (M1.4).
        self._floor_spin = QDoubleSpinBox()
        self._floor_spin.setDecimals(2)
        self._floor_spin.setSingleStep(0.05)
        self._floor_spin.setRange(0.0, 1.0)
        tips.describe(self._floor_spin,
                      "Opacity of unrevealed animated ink; 0 hides it "
                      "until onset")

        self._sweep_box = QCheckBox("Sweep")
        tips.describe(self._sweep_box,
                      "Continuous reveal sweep; unchecked steps at "
                      "musical onsets")
        self._sweep_box.toggled.connect(
            lambda checked: self._state.execute(SetRevealMode(
                RevealMode.CONTINUOUS if checked else RevealMode.STEPPED)))

        # Tied notes as one (Marcus, 2026-08-10): a document flag like
        # Sweep, not a style entry — it re-derives the schedule and the
        # reveal tracks, never the engraving.
        self._tied_box = QCheckBox("Tied notes as one")
        tips.describe(
            self._tied_box,
            "A tied chain appears and animates as one note: the whole "
            "held note shows at the chain start and effects run its "
            "full tied length; unchecked fills it in bar by bar")
        self._tied_box.toggled.connect(
            lambda checked: self._state.execute(SetTiedNotesAsOne(checked)))

        # Reset (Marcus, 2026-07-25): back to the pre-M4 defaults —
        # effect "appear", every preset's params cleared — as ONE undo
        # step. Floor opacity and Sweep predate the M4 options and stay
        # put.
        self._reset_button = QPushButton("Reset")
        tips.describe(
            self._reset_button,
            "Restore the effect settings to their defaults — the effect "
            "back to appear, every effect's own options back where they "
            "started, and the volume response and system pulse off — in "
            "one undo step; Floor opacity and Sweep are untouched")
        self._reset_button.clicked.connect(self._commit_reset)

        self._floor = LiveField(self._floor_spin, app_state, self._floor_edit,
                                self._update_display)

        self._form = QFormLayout(self)
        panel_style.style_form(self._form)
        self._form.addRow("Effect", self._effect_combo)
        self._form.addRow("Combine with", self._combine_combo)
        # Each preset's block builds its own rows here, so it can be
        # shown and hidden as a unit.
        self.blocks = {
            preset: KnobGroup(STORES.get(preset, EffectParamStore)(preset),
                              title, knobs,
                              app_state, self._form, self._update_display)
            for preset, title, knobs in BLOCKS}
        # Always on screen, unlike a preset's block: it is not an effect,
        # so "show the options of the effect you are using" says nothing
        # about it.
        self.volume = KnobGroup(volume_knobs.VolumeStore(), volume_knobs.TITLE,
                                volume_knobs.KNOBS, app_state, self._form,
                                self._update_display)
        # Its neighbour, and always on screen for the same reason: the
        # recording moves one note here and the whole page there.
        self.pulse = KnobGroup(pulse_knobs.PulseStore(), pulse_knobs.TITLE,
                               pulse_knobs.KNOBS, app_state, self._form,
                               self._update_display)
        self._form.addRow(self._reset_button)
        self._form.addRow("Floor opacity", self._floor_spin)
        self._form.addRow(self._sweep_box)
        self._form.addRow(self._tied_box)

        # Every row is on screen right now — a preset's block only hides
        # itself on the first resync, below — so this is the widest the
        # panel can ever be. Pinning the label column and taking that
        # width as the panel's minimum here is what stops a row being
        # squeezed into clipping later, whichever blocks are showing.
        panel_style.fix_label_column(self._form)
        self.setMinimumWidth(panel_style.natural_width(self._form))

        # the tuple is what holds the fields alive, and the test scans it
        self.live_fields = tuple(field for block in self.blocks.values()
                                 for field in block.fields.values()) \
            + tuple(self.volume.fields.values()) \
            + tuple(self.pulse.fields.values()) + (self._floor,)
        # Start on the document, so every control shows its default from
        # the first frame — a knob that defaults to ON (Bounce) has to
        # open checked, not wait for the first resync.
        self.sync_from_document(app_state.doc)

    # -- document sync ---------------------------------------------------------

    def _in_use(self, doc: ProjectDoc, preset: str) -> bool:
        """Does anything resolve to this preset — the document default,
        a part rule or an element rule? Its params apply to all three.
        A name may hold several effects at once ("drop+fade"), so this
        asks whether the preset is one PART of the name, through the one
        splitting helper core resolution uses."""
        def holds(name: str | None) -> bool:
            return preset in split_effect_name(name)

        style = doc.style
        return (holds(style.default_effect)
                or any(holds(r.effect) for r in style.parts.values())
                or any(holds(r.effect) for r in style.elements.values()))

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
        for preset, block in self.blocks.items():
            block.set_visible(self._form, self._in_use(doc, preset))
            block.update_display(doc)
        # Quiet and Loud describe a range nothing is being read onto
        # while Amount is 0, so they gray out — the same "an option
        # another option renders obsolete" rule, from the other side.
        self.volume.update_display(doc)
        self.pulse.update_display(doc)
        tips.gate(self._reset_button, not self._at_defaults(doc),
                  "The effect settings are already at their defaults")

    def _fill_combine(self, primary: str,
                      keep: str | None = None) -> None:
        """The second dropdown: nothing, or any preset other than the
        one already chosen. Refilled whenever the first choice moves,
        keeping the second one if it is still on offer."""
        if keep is None:
            keep = self._combine_combo.currentText()
        names = [name for name in sorted(PRESETS) if name != primary]
        self._combine_combo.blockSignals(True)
        self._combine_combo.clear()
        self._combine_combo.addItem(_NO_COMBINE)
        for name in names:
            self._combine_combo.addItem(name)
        self._combine_combo.setCurrentText(keep if keep in names
                                           else _NO_COMBINE)
        self._combine_combo.blockSignals(False)

    def _at_defaults(self, doc: ProjectDoc) -> bool:
        """Nothing for Reset to do: no document default, no stored params
        for any preset with knobs here, no volume response and no
        system pulse."""
        return (doc.style.default_effect is None
                and not self.volume.has_params(doc)
                and not self.pulse.has_params(doc)
                and not any(block.has_params(doc)
                            for block in self.blocks.values()))

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Resync every control (execute, undo, redo, and load all
        arrive here via the inspector); never re-executes."""
        stored = doc.style.default_effect or DEFAULT_EFFECT
        parts = split_effect_name(stored)
        # Two dropdowns hold two effects. A hand-edited name with more
        # than that shows whole in the first box: the stored intent, not
        # a silently shortened version of it.
        primary = stored if len(parts) > 2 else (parts[0] if parts
                                                 else DEFAULT_EFFECT)
        secondary = parts[1] if len(parts) == 2 else None
        self._effect_combo.blockSignals(True)
        if self._effect_combo.findText(primary) < 0:
            # a name from a newer build: show the stored intent rather
            # than silently displaying the wrong preset
            self._effect_combo.addItem(primary)
        self._effect_combo.setCurrentText(primary)
        self._effect_combo.blockSignals(False)
        self._fill_combine(primary, secondary)

        for block in self.blocks.values():
            block.resync(doc)
        self.volume.resync(doc)
        self.pulse.resync(doc)

        self._floor.resync(doc.style.floor_opacity)
        self._sweep_box.blockSignals(True)
        self._sweep_box.setChecked(doc.style.reveal_mode
                                   is RevealMode.CONTINUOUS)
        self._sweep_box.blockSignals(False)
        self._tied_box.blockSignals(True)
        self._tied_box.setChecked(doc.tied_notes_as_one)
        self._tied_box.blockSignals(False)
        self._update_display()

    # -- commit handlers (one command per user gesture) ------------------------

    def _floor_edit(self, value: float) -> Command | None:
        """The one function both the preview and the commit call, so the
        two can never ask for different edits. It reads the COMMITTED
        document: `doc` hands a live field back its own preview, and a
        guard reading it would never commit."""
        if abs(value - self._state.committed.style.floor_opacity) < 1e-9:
            return None
        return SetFloorOpacity(value)

    def _commit_effect(self) -> None:
        """Both dropdowns land here: the two choices are ONE name, and
        one command."""
        primary = self._effect_combo.currentText()
        secondary = self._combine_combo.currentText()
        # the second list depends on the first choice
        self._fill_combine(primary, secondary)
        secondary = self._combine_combo.currentText()
        name = primary if secondary == _NO_COMBINE \
            else primary + COMBINE_SEP + secondary
        if name == (self._state.doc.style.default_effect or DEFAULT_EFFECT):
            return
        self._state.execute(SetDefaultEffect(name))
        self._update_display()

    def _commit_reset(self) -> None:
        if self._at_defaults(self._state.doc):
            return                       # already at defaults: no-op
        self._state.execute(ResetEffectSettings())
        self.sync_from_document(self._state.doc)
