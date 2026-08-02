"""The glow effect's data: a halo's colour and size, and its shape over
time.

A sounding note carries an outer glow — a soft coloured halo around the
ink, the Photoshop outer-glow look — that lights when the note sounds
and dies when it stops.

The effect splits cleanly in two, and this module keeps both halves
because both are data:

- the **styling** half, `read_glow` — what colour the halo is and how
  far it reaches. It changes when the document changes, never per
  frame, so render reads it once and pushes it to the items. It lives
  here rather than in `presets.py` so render can have the two numbers
  without importing the preset registry.
- the **animation** half, `glow_track` — one ordinary float envelope on
  the GLOW property, 0 = no glow, 1 = full glow. Nothing downstream
  knows this envelope belongs to an effect called "glow" (rule 6).

`read_glow` is fail-soft, like `read_colors` next door: a colour or a
radius it cannot read falls back to the default rather than raising. A
hand-edited file must not be able to produce something nobody can see.
`glow_track` is not — it takes scalars its caller has already clamped,
the `presets.swell_scale` arrangement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from typing import Mapping

from scoreanim.core.animation.effect import Easing, Envelope, Keyframe

# The two shapes. "pop" steps to full light at the trigger and eases
# out; "swell" is the swell's own hump, applied to light instead of
# size. Named GLOW_* because two effects are already called pop and
# swell, and these are neither of them.
GLOW_POP = "pop"
GLOW_SWELL = "swell"

# Defaults for the document's sparse effect_params["glow"].
GLOW_COLOR = "#ffcc66"      # a warm gold
# Scene units. Measured 2026-08-02 (spikes/glow.py): the halo's visible
# reach is about HALF the blur radius, so 36 puts about one notehead's
# height of light around the ink — a staff space is 18 units on
# testscore, and a notehead is about one staff space tall.
GLOW_RADIUS = 36.0
GLOW_STRENGTH = 1.0
GLOW_SHAPE = GLOW_POP
GLOW_S = 0.4
# The one preset besides swell that stretches to the note by default,
# and for the same reason turned up a notch: a glow that dies exactly
# when the note's value ends is the whole point, because that is what
# makes only SOUNDING notes glow.
GLOW_NOTE_VALUE = True
GLOW_PEAK = 0.5             # swell shape only

# Scene units, clamped where the radius is consumed (below). The far
# end is a whole staff's height of light, which is already far more
# than anybody wants.
_RADIUS_RANGE = (0.0, 500.0)

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class GlowStyle:
    """What the halo looks like: a lowercase "#rrggbb" string a caller
    can hand straight to QColor, and a radius in SCENE units."""
    color: str = GLOW_COLOR
    radius: float = GLOW_RADIUS


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
    try:
        radius = float(entry.get("radius", GLOW_RADIUS))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        radius = GLOW_RADIUS
    if radius != radius or radius in (float("inf"), float("-inf")):
        radius = GLOW_RADIUS
    radius = min(_RADIUS_RANGE[1], max(_RADIUS_RANGE[0], radius))
    return GlowStyle(color=color, radius=radius)


def glow_track(shape: str, strength: float, peak: float,
               seconds: float) -> Envelope:
    """How bright the halo is over time, in either shape.

    Both start and end at exactly 0: there is no light before the note
    sounds and none left after it stops, which is what keeps a glow to
    the notes that are actually sounding.

    "pop" steps to full light at the trigger and eases out, quick away
    from the top and slow to arrive at nothing — the shape a struck note
    has. "swell" is `presets.swell_scale`'s hump moved onto light: up on
    EASE_IN, gathering pace the way a crescendo grows, down on EASE_OUT,
    with `peak` saying how far through the top lands.

    An unknown shape is a pop, the fail-soft every stored name here
    gets."""
    if shape == GLOW_SWELL:
        return Envelope(initial=0.0,
                        keyframes=(Keyframe(0.0, 0.0, Easing.STEP),
                                   Keyframe(peak * seconds, strength,
                                            Easing.EASE_IN),
                                   Keyframe(seconds, 0.0, Easing.EASE_OUT)))
    return Envelope(initial=0.0,
                    keyframes=(Keyframe(0.0, strength, Easing.STEP),
                               Keyframe(seconds, 0.0, Easing.EASE_OUT)))
