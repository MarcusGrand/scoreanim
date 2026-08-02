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

from scoreanim.core.animation import (GLOW_COLOR, GLOW_POP, GLOW_RADIUS,
                                      GLOW_SWELL)
from scoreanim.ui.panels.effect_knobs import Check, Choice, Color, Knob, Number

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
               "about 18. A wider radius spreads the same light "
               "thinner, so it reaches further but dims"),
        Number("Strength", "strength", 1.0, 0.0, 1.0, 0.05,
               "How brightly the halo burns at its brightest (0 = no "
               "glow at all)"),
        # Peak has no knob on purpose: the swell shape's top sits
        # halfway through unless a hand-edited file says otherwise.
        Choice("Shape", "shape", GLOW_POP,
               ((GLOW_POP, "Pop"), (GLOW_SWELL, "Swell")),
               "Pop lights the note fully at the onset and fades out; "
               "Swell grows the light to a peak partway through and back "
               "down again"),
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
