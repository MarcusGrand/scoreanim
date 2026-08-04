"""The glow effect's data: a halo's colour and size, and its shape over
time.

A sounding note carries an outer glow — a soft coloured halo around the
ink, the Photoshop outer-glow look — that lights when the note sounds
and dies when it stops.

The effect splits cleanly in two, and this module keeps both halves
because both are data:

- the **styling** half, `read_glow` — what colour the halo is, how far
  it reaches, and how solid the light in it is. It changes when the
  document changes, never per frame, so render reads it once and pushes
  it to the items. It lives here rather than in `presets.py` so render
  can have those numbers without importing the preset registry.
- the **animation** half, `read_glow_shape` — one ordinary float
  envelope on the GLOW property, 0 = no glow, 1 = full glow. Nothing
  downstream knows this envelope belongs to an effect called "glow"
  (rule 6). The shape itself, and the curve it becomes, are
  `core/animation/envelope_shape.py`: they belong to no one effect, and
  the editor canvas drags the same six values.

Both halves are fail-soft, like `read_colors` next door: anything they
cannot read falls back to the default rather than raising. A hand-edited
file must not be able to produce something nobody can see, and it must
not be able to produce an envelope that raises either — `clamp_spec`
next door is what keeps the keyframes legal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from typing import Mapping

from scoreanim.core.animation.envelope_shape import (EnvelopeSpec, clamp_spec,
                                                     spec_envelope)

# The two SUPERSEDED shape words. Until 2026-08-03 the glow's brightness
# curve was a switch between these two: "pop" stepped to full light at
# the trigger and eased out, "swell" was the swell's own hump applied to
# light instead of size. They are read but never written now — a stored
# one maps onto the envelope params below (`glow_defaults`).
GLOW_POP = "pop"
GLOW_SWELL = "swell"

# Defaults for the document's sparse effect_params["glow"].
GLOW_COLOR = "#ffcc66"      # a warm gold
# Scene units, and about a notehead's height: one is 18 units tall on
# testscore. Measured on that fixture (spikes/glow.py), a wider radius
# spreads the same light thinner, so the halo goes further but dims:
# at 18 / 24 / 36 / 60 it reaches 7 / 8 / 8 / 11 units past the ink and
# changes the brightest pixel it touches by 74 / 66 / 49 / 28 of 255.
# Rendered all of them on a dark page and looked: 18 is tight enough to
# read as a bright rim on the ink rather than a halo around it, and 36
# is noticeably foggy. 24 is the halo.
GLOW_RADIUS = 24.0
GLOW_STRENGTH = 1.0
GLOW_S = 0.4
# The one preset besides swell that stretches to the note by default,
# and for the same reason turned up a notch: a glow that dies exactly
# when the note's value ends is the whole point, because that is what
# makes only SOUNDING notes glow.
GLOW_NOTE_VALUE = True
GLOW_PEAK = 0.5             # superseded: the old swell shape's top
GLOW_DENSITY = 0.0          # a plain blur, the soft default

# The envelope's own shape, the synthesizer's four names. Every one of
# these is a FRACTION of the effect's span — the note's own value with
# "Entire note value" on, the authored duration with it off — so the
# shape keeps its proportions however long the note is (the swell Peak
# precedent). The defaults are a quick rise, a hold while the note
# sounds, and a release that lands on nothing as the note stops.
GLOW_ATTACK = 0.10          # spent rising from nothing to the hold
GLOW_SUSTAIN = 1.0          # the held level, 1 being full Strength
GLOW_SWELL_ON = False       # the optional hump riding on the hold
GLOW_SWELL_POS = 0.5        # where the hump's top sits
GLOW_SWELL_LEVEL = 1.0      # how bright the hump's top is
GLOW_RELEASE = 0.20         # spent falling back to nothing at the end

# Scene units, clamped where the radius is consumed (below). The far
# end is a whole staff's height of light, which is already far more
# than anybody wants.
_RADIUS_RANGE = (0.0, 500.0)

# How many times over the light is laid down at density 1. Each pass
# puts the same halo over the one below it, so the alpha at a point
# goes 1 - (1 - a)ⁿ: the light nearest the ink fills in first and the
# faint outer tail follows. Measured on testscore
# (spikes/glow_density.py): at 32 the halo is a solid block of colour
# around the note with a short gradient at its edge, which is as solid
# as anybody asked for, and going further only fills in a tail nobody
# is looking at. It never spreads past the blur's own reach — that is
# what the radius is for.
_DENSITY_PASSES = 32.0

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class GlowStyle:
    """What the halo looks like: a lowercase "#rrggbb" string a caller
    can hand straight to QColor, a radius in SCENE units, and how solid
    the light is (0 = the plain blur, 1 = a solid colour)."""
    color: str = GLOW_COLOR
    radius: float = GLOW_RADIUS
    density: float = GLOW_DENSITY

    @property
    def passes(self) -> float:
        """How many times over the light is laid down. 1 is the plain
        blur, and the count climbs a curve rather than a line: the first
        few passes are what fill the halo in, so an even spread of them
        over the knob would waste its top half."""
        return _DENSITY_PASSES ** self.density


def read_glow(raw: Mapping[str, object] | None) -> GlowStyle:
    """The styling half of the document's sparse effect_params["glow"],
    made safe. Anything unreadable — a missing key, a colour that is not
    #rrggbb, a radius that is not a finite number — falls back to the
    default."""
    entry = raw or {}
    color = entry.get("color")
    if not (isinstance(color, str) and _HEX.match(color.strip())):
        color = GLOW_COLOR
    else:
        color = color.strip().lower()
    radius = _number(entry.get("radius", GLOW_RADIUS), GLOW_RADIUS,
                     *_RADIUS_RANGE)
    density = _number(entry.get("density", GLOW_DENSITY), GLOW_DENSITY,
                      0.0, 1.0)
    return GlowStyle(color=color, radius=radius, density=density)


def _number(raw: object, fallback: float, lo: float, hi: float) -> float:
    """One stored number, made safe: anything that is not a finite
    number falls back, and the rest is clamped into range."""
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if value != value or value in (float("inf"), float("-inf")):
        return fallback
    return min(hi, max(lo, value))


# The glow's brightness curve is an ordinary envelope, so the shape and
# the curve are the shared ones next door. The two old names stay as
# they were: this module is still where the glow asks for them.
GlowShape = EnvelopeSpec
glow_track = spec_envelope


def glow_defaults(raw: Mapping[str, object] | None) -> dict[str, object]:
    """What each shape key falls back to when the document is silent
    about it — the module defaults, unless the entry still carries the
    superseded `shape`, in which case the old look becomes the default
    instead. That way a project saved before the envelope existed opens
    looking exactly as it did, and one key edited by hand leaves the
    rest of the old shape standing.

    The `setdefault` idiom the v1 `part_colors` fold already uses: an
    explicit new key always wins over the mapped old one. This is the
    one authority for the mapping — the panel reads it too, so its boxes
    show what the effect is actually doing."""
    defaults: dict[str, object] = {
        "attack": GLOW_ATTACK, "sustain": GLOW_SUSTAIN,
        "swell_on": GLOW_SWELL_ON, "swell_pos": GLOW_SWELL_POS,
        "swell_level": GLOW_SWELL_LEVEL, "release": GLOW_RELEASE}
    entry = raw or {}
    if "shape" not in entry:
        return defaults
    if entry.get("shape") == GLOW_SWELL:
        # The old hump: dark at the onset, up to full light partway
        # through and back down to dark at the end. That is this
        # envelope with nothing held and the hump doing all the work.
        defaults.update(attack=0.0, sustain=0.0, swell_on=True,
                        swell_pos=_number(entry.get("peak", GLOW_PEAK),
                                          GLOW_PEAK, 0.0, 1.0),
                        swell_level=1.0, release=0.0)
    else:
        # The old pop — and any unknown word, which used to fail soft to
        # a pop: full light at once, then the whole span spent fading.
        defaults.update(attack=0.0, sustain=1.0, swell_on=False,
                        release=1.0)
    return defaults


def read_glow_shape(raw: Mapping[str, object] | None) -> GlowShape:
    """The animation half of the document's sparse
    effect_params["glow"], made safe. Every value falls back the way
    `read_glow` does, and then `clamp_spec` puts the six in an order
    `Envelope` will accept — the attack and the release scaled down
    together when they overflow, the hump kept strictly inside the hold
    or dropped."""
    entry = raw or {}
    defaults = glow_defaults(entry)

    def frac(key: str) -> float:
        fallback = float(defaults[key])            # type: ignore[arg-type]
        return _number(entry.get(key, fallback), fallback, 0.0, 1.0)

    return clamp_spec(EnvelopeSpec(
        attack=frac("attack"), sustain=frac("sustain"),
        swell_on=bool(entry.get("swell_on", defaults["swell_on"])),
        swell_pos=frac("swell_pos"), swell_level=frac("swell_level"),
        release=frac("release")))
