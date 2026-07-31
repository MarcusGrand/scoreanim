"""Effects panel (M4.8): the *Appearance & Effects* section's body.

Document-wide effect controls: the Effect dropdown (enumerates the
preset registry, sets `default_effect`), a second dropdown for an effect
to run WITH it, each knobbed preset's own block of options, plus Reset,
Floor opacity and Sweep. Two effects at once are stored as ONE name,
"drop+fade" — the document is unchanged, and a build that does not know
one of the parts still runs the other. Every control commits
exactly ONE command per user gesture. The number fields preview as you
type (`ui/live_field.py`): the stage shows the amplitude, the durations,
the shift and the ghost opacity on every keystroke, and the typing
session still lands as one undo entry. The checkboxes and the dropdown
have no half-typed state, so they commit outright. `sync_from_document`
resyncs and never re-executes.

A preset's knobs are DATA here — one entry in `_BLOCKS`, built and run
by `PresetKnobs` (`ui/panels/effect_knobs.py`). This panel owns what
belongs to no single preset: which effect is the default, which blocks
are on screen, Reset, and the two document-wide controls. Every effect
says "Duration" for how long it runs, and "Entire note value" sits on
the duration's own row, as the alternative to typing one (Marcus,
2026-07-31).

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
                                    SetRevealMode)
from scoreanim.ui.app_state import AppState
from scoreanim.ui.live_field import LiveField
from scoreanim.ui.panels.effect_knobs import Check, Number, PresetKnobs

# The "no second effect" entry in the Combine with dropdown. Not a
# preset name, and never stored: the document holds the first effect's
# name alone.
_NO_COMBINE = "(none)"

# Every preset with knobs, in the order its block appears. A knob's
# default is document units (seconds for Peak offset); its range and
# step are what the box shows (milliseconds there).
_BLOCKS: tuple[tuple[str, str, tuple], ...] = (
    ("pop", "Pop", (
        Number("Amplitude", "scale", 1.25, 0.1, 10.0, 0.05,
               "Pop scale factor at the onset (1.0 = no bump)"),
        # The document calls this one "settle"; the UI says Duration,
        # the word every effect uses for how long it runs.
        Number("Duration", "settle", 0.25, 0.01, 5.0, 0.05,
               "Seconds the pop takes to relax back to 1.0 — inactive "
               "while 'Entire note value' is on (each note then settles "
               "over its own length)",
               suffix=" s", grayed_by="note_value"),
        Check("Entire note value", "note_value", False,
              "Use each note's own length as the duration — a whole note "
              "relaxes slowly, an eighth pops and settles at once",
              beside="settle"),
        # ms in the UI, seconds in the document. The tooltip states the
        # F3 consequence verbatim: the opacity step rides the shift.
        Number("Peak offset", "peak_offset", 0.0, -500, 500, 10,
               "Shifts the whole pop, including when the note appears — "
               "at a negative offset every note becomes visible that "
               "early",
               suffix=" ms", factor=1000.0, integer=True),
    )),
    ("fade", "Fade", (
        Number("Duration", "duration", 0.4, 0.01, 5.0, 0.05,
               "Seconds the fade takes to rise from the floor to full — "
               "inactive while 'Entire note value' is on (each note then "
               "fades over its own length)",
               suffix=" s", grayed_by="note_value"),
        Check("Entire note value", "note_value", False,
              "Use each note's own length as the duration — a whole note "
              "rises slowly, an eighth is up at once",
              beside="duration"),
    )),
    ("drop", "Drop", (
        Number("Start size", "start_size", 3.0, 0.1, 10.0, 0.25,
               "How many times its engraved size the note is when it "
               "enters — the bigger it starts, the further away it "
               "looks"),
        Number("Duration", "duration", 0.35, 0.01, 5.0, 0.05,
               "Seconds the note takes to land: to shrink onto its "
               "place and go fully solid",
               suffix=" s"),
        Check("Bounce", "bounce", True,
              "A small settle as the note lands, instead of coming "
              "straight to rest"),
    )),
    ("slide", "Slide", (
        # Degrees, and a whole number of them is plenty. 0 is straight
        # down onto the note's place; the angle turns clockwise from
        # there, so 90 comes in from the right.
        Number("Direction", "direction", 0.0, 0, 359, 15,
               "Where the note comes FROM, in degrees: 0 from above, "
               "90 from the right, 180 from below, 270 from the left",
               suffix="°", integer=True),
        Number("Distance", "distance", 120.0, 0.0, 2000.0, 25.0,
               "How far out the note starts, in page units — 120 is just "
               "clear of its own staff, 200 reaches the staff next door"),
        Number("Duration", "duration", 0.35, 0.01, 5.0, 0.05,
               "Seconds the note takes to travel in to its place",
               suffix=" s"),
        Check("Bounce", "bounce", False,
              "A small settle as the note arrives, instead of coming "
              "straight to rest"),
    )),
)


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

        # A second effect to run WITH the first ("drop+fade"): the two
        # are stored as one name, so nothing about the document changes.
        self._combine_combo = QComboBox()
        self._combine_combo.setToolTip(
            "A second effect to run at the same time as the first — the "
            "two are combined property by property")
        self._fill_combine(DEFAULT_EFFECT)
        self._combine_combo.activated.connect(self._commit_effect)

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
        # effect "appear", every preset's params cleared — as ONE undo
        # step. Floor opacity and Sweep predate the M4 options and stay
        # put.
        self._reset_button = QPushButton("Reset")
        self._reset_button.setToolTip(
            "Restore the effect settings to their defaults — the effect "
            "back to appear, and every effect's own options back where "
            "they started — in one undo step; Floor opacity and Sweep "
            "are untouched")
        self._reset_button.clicked.connect(self._commit_reset)

        self._floor = LiveField(self._floor_spin, app_state, self._floor_edit,
                                self._update_display)

        self._form = QFormLayout(self)
        self._form.setContentsMargins(8, 2, 8, 6)
        self._form.addRow("Effect", self._effect_combo)
        self._form.addRow("Combine with", self._combine_combo)
        # Each preset's block builds its own rows here, so it can be
        # shown and hidden as a unit.
        self.blocks = {
            preset: PresetKnobs(preset, title, knobs, app_state, self._form,
                                self._update_display)
            for preset, title, knobs in _BLOCKS}
        self._form.addRow(self._reset_button)
        self._form.addRow("Floor opacity", self._floor_spin)
        self._form.addRow(self._sweep_box)

        # the tuple is what holds the fields alive, and the test scans it
        self.live_fields = tuple(field for block in self.blocks.values()
                                 for field in block.fields.values()) \
            + (self._floor,)
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
        self._reset_button.setEnabled(not self._at_defaults(doc))

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
        """Nothing for Reset to do: no document default, and no stored
        params for any preset with knobs here."""
        return (doc.style.default_effect is None
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

        self._floor.resync(doc.style.floor_opacity)
        self._sweep_box.blockSignals(True)
        self._sweep_box.setChecked(doc.style.reveal_mode
                                   is RevealMode.CONTINUOUS)
        self._sweep_box.blockSignals(False)
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
