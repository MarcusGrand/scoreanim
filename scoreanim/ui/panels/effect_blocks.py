"""Every knobbed preset's block of options, as data.

Effects are data (rule 6), and so are their knobs: a preset with options
is one entry here — a title and a list of `Knob`s — and never a second
code path. `ui/panels/effects_panel.py` builds each entry with
`KnobGroup` and owns only what belongs to no single preset. The volume
response and the system pulse have the same shape in their own modules
(`volume_knobs.py`, `pulse_knobs.py`); this is the same idea for the
presets, kept here so the panel stays about the panel.

A knob's default is in DOCUMENT units (seconds for Peak offset, a
fraction for Peak); its range and step are what the box shows
(milliseconds, per cent). Every effect says "Duration" for how long it
runs, and "Entire note value" sits on the duration's own row as the
alternative to typing one (Marcus, 2026-07-31).
"""
from __future__ import annotations

from dataclasses import dataclass

from typing import Mapping

from scoreanim.core.animation import (GLOW_ATTACK, GLOW_COLOR, GLOW_DENSITY,
                                      GLOW_RADIUS, GLOW_RELEASE, GLOW_SUSTAIN,
                                      GLOW_SWELL_LEVEL, GLOW_SWELL_ON,
                                      GLOW_SWELL_POS, glow_defaults)
from scoreanim.core.project import ProjectDoc
from scoreanim.ui.panels.knob_types import (Check, Color, EffectParamStore,
                                            Envelope, Knob, KnobStore, Number)

# (preset name, block title, its knobs), in the order the blocks appear.
BLOCKS: tuple[tuple[str, str, tuple[Knob, ...]], ...] = (
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
    ("swell", "Swell", (
        Number("Amplitude", "size", 1.4, 0.1, 10.0, 0.05,
               "How many times its engraved size the note reaches at "
               "the top of the swell (1.0 = no growth)"),
        # Per cent in the UI, a fraction in the document: pop's Peak
        # offset precedent, where the box shows milliseconds and the
        # document holds seconds.
        Number("Peak", "peak", 0.5, 5, 95, 5,
               "How far through the swell the top lands — 50 % is "
               "halfway, less is an early top, more a late one. "
               "Inactive while 'Follow volume' is on: the top is then a "
               "stretch, not a point",
               suffix=" %", factor=100.0, integer=True,
               grayed_by="follow"),
        Number("Duration", "duration", 0.8, 0.01, 5.0, 0.05,
               "Seconds the whole swell takes — inactive while 'Entire "
               "note value' is on (each note then swells over its own "
               "length)",
               suffix=" s", grayed_by="note_value"),
        Check("Entire note value", "note_value", True,
              "Use each note's own length as the duration — a whole "
              "note swells across its bar, an eighth is a quick breath",
              beside="duration", forced_by="follow"),
        Check("Follow volume", "follow", False,
              "While the note sounds, its size tracks how loud the "
              "recording is: a crescendo grows it, a diminuendo shrinks "
              "it, and it eases back to its engraved size at the end. "
              "Needs a recording loaded and the Volume response turned "
              "up"),
    )),
    ("glow", "Glow", (
        Color("Colour", "color", GLOW_COLOR,
              "The colour of the halo around a sounding note",
              title="Glow colour"),
        Number("Radius", "radius", GLOW_RADIUS, 0.0, 500.0, 4.0,
               "How far the halo reaches, in page units — a notehead is "
               "about 18. Size only: it does not change how bright or "
               "how solid the light is"),
        # Per cent in the UI, a fraction in the document — the Peak
        # precedent. See core/animation/glow.py for the curve it drives.
        Number("Density", "density", GLOW_DENSITY, 0, 100, 10,
               "How solid the light is: 0 % is a soft blur that fades "
               "away from the ink, and at 100 % the halo is a solid "
               "block of the colour around the note. Radius still says "
               "how far it reaches — turn both up for a big solid halo",
               suffix=" %", factor=100.0, integer=True),
        # The picture of the six numbers below, and the other way to
        # author them: drag the corners instead of typing per cents.
        # Closed until asked for (Marcus, 2026-08-04) — the numbers are
        # what the block opens with.
        Envelope("Envelope", "envelope", attack="attack", sustain="sustain",
                 swell_on="swell_on", swell_pos="swell_pos",
                 swell_level="swell_level", release="release",
                 tooltip="Drag the corners to shape the light: the rise, "
                         "the held level, the swell's top, and where the "
                         "fall begins. Time runs across the note, level "
                         "up the side"),
        # The envelope, in per cent of the span the light has to play
        # with — the note's own length while "Entire note value" is on,
        # the Duration below while it is off. The same six values the
        # canvas above draws: edit either, and both follow.
        Number("Attack", "attack", GLOW_ATTACK, 0, 100, 5,
               "How much of the note the light spends coming up, as a "
               "per cent of it — 0 % is lit the instant the note starts",
               suffix=" %", factor=100.0, integer=True),
        Number("Sustain", "sustain", GLOW_SUSTAIN, 0, 100, 5,
               "How brightly the light holds once it is up — 100 % is "
               "the full glow",
               suffix=" %", factor=100.0, integer=True),
        Number("Release", "release", GLOW_RELEASE, 0, 100, 5,
               "How much of the note the light spends dying away at the "
               "end, as a per cent of it. The light always reaches "
               "nothing exactly as the note stops",
               suffix=" %", factor=100.0, integer=True),
        Check("Swell", "swell_on", GLOW_SWELL_ON,
              "One extra rise and fall riding on the held part: the "
              "light eases up from Sustain and back down again while "
              "the note is still sounding"),
        Number("Swell at", "swell_pos", GLOW_SWELL_POS, 0, 100, 5,
               "Where the swell's top sits, as a per cent of the note. "
               "It is always kept inside the held part, between the "
               "attack and the release",
               suffix=" %", factor=100.0, integer=True,
               enabled_by="swell_on"),
        Number("Swell level", "swell_level", GLOW_SWELL_LEVEL, 0, 100, 5,
               "How bright the swell's top is, on the same scale as "
               "Sustain — below it the swell is a dip instead",
               suffix=" %", factor=100.0, integer=True,
               enabled_by="swell_on"),
        Number("Duration", "duration", 0.4, 0.01, 5.0, 0.05,
               "Seconds the glow takes to die away — inactive while "
               "'Entire note value' is on (the light then lasts exactly "
               "as long as the note does)",
               suffix=" s", grayed_by="note_value"),
        Check("Entire note value", "note_value", True,
              "Use each note's own length, so the glow goes out exactly "
              "when the note stops sounding — which is what keeps the "
              "light on the notes that are actually playing",
              beside="duration"),
    )),
)


@dataclass(frozen=True)
class GlowParamStore(EffectParamStore):
    """The glow's knobs, with the superseded shape words folded in.

    A project saved before the envelope existed carries `shape` and
    `peak` and none of the six envelope keys. Core maps those onto the
    envelope when it reads them, so the halo still looks as it did —
    and the boxes have to say the same thing, or the panel would show
    the plain defaults while the note glowed in the old shape. Same
    argument as `Check.forced_by`: what the panel shows is what the
    effect is actually doing, and core stays the one authority for it."""

    def stored(self, doc: ProjectDoc) -> Mapping[str, object]:
        raw = super().stored(doc)
        return {**glow_defaults(raw), **raw}


# The presets whose knobs need something other than the plain store.
STORES: Mapping[str, type[KnobStore]] = {"glow": GlowParamStore}
