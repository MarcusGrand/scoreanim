"""The synthesizer envelope's shape, and the curve it turns into.

One rise, one hold, an optional hump on the hold, one fall. Every time
here is a FRACTION of the span the shape plays over — the note's own
value, or an authored duration — so the shape keeps its proportions
however long that span is, and every level is a fraction of the full
amount.

Nothing here belongs to one effect. The glow's brightness is the first
thing shaped this way (`core/animation/glow.py` reads it out of the
document), and the editor canvas drags these same six values
(`core/editing/envelope_drag.py`), so the shape, the order it has to
keep, and the curve it becomes all live in one place.

`Envelope` refuses keyframes that do not strictly increase in time, so
a shape has to be put in order before it can become one. `clamp_spec`
is that one authority — every reader and every drag goes through it,
which is what makes an invalid envelope unreachable rather than merely
unlikely.
"""
from __future__ import annotations

from dataclasses import dataclass

from scoreanim.core.animation.effect import Easing, Envelope, Keyframe

# The smallest gap between two keyframes, as a fraction of the span.
# Small enough that a clamp is invisible, large enough to survive the
# multiplication by the span.
MIN_GAP = 0.02


@dataclass(frozen=True)
class EnvelopeSpec:
    """The six values that describe the shape, in fractions of the span
    and of the full amount. No defaults on purpose: what a missing value
    means belongs to whoever is reading the document, not here."""
    attack: float           # spent rising from nothing to the hold
    sustain: float          # the held level
    swell_on: bool          # is there a hump riding on the hold?
    swell_pos: float        # where the hump's top sits
    swell_level: float      # how high the hump's top is
    release: float          # spent falling back to nothing at the end


def _unit(value: float) -> float:
    return min(1.0, max(0.0, value))


def clamp_spec(spec: EnvelopeSpec) -> EnvelopeSpec:
    """The same shape, in an order `Envelope` will accept.

    - every value sits in 0-1;
    - the attack and the release cannot fill the span between them. If
      they overflow, both scale down proportionally, so a shape keeps
      the balance it asked for and still leaves a hold;
    - the hump sits strictly inside the hold, and drops out entirely
      when the hold is too narrow to fit one.

    An attack of exactly 0 is allowed and means the level is up at the
    trigger, so no scaling is needed there — a release over the whole
    span is a legal shape.
    """
    attack = _unit(spec.attack)
    release = _unit(spec.release)
    swell_pos = _unit(spec.swell_pos)
    swell_on = spec.swell_on
    if attack > 0.0 and attack + release > 1.0 - MIN_GAP:
        scale = (1.0 - MIN_GAP) / (attack + release)
        attack *= scale
        release *= scale
    hold_end = 1.0 - release
    if swell_on and hold_end - attack > 2.0 * MIN_GAP:
        swell_pos = min(hold_end - MIN_GAP, max(attack + MIN_GAP, swell_pos))
    else:
        swell_on = False
    return EnvelopeSpec(attack=attack, sustain=_unit(spec.sustain),
                        swell_on=swell_on, swell_pos=swell_pos,
                        swell_level=_unit(spec.swell_level), release=release)


def spec_envelope(spec: EnvelopeSpec, amount: float,
                  seconds: float) -> Envelope:
    """The shape as a curve over time: stretched across `seconds` and
    scaled by `amount`.

    It starts and ends at exactly 0 by construction — nothing before the
    trigger and nothing left after the span, which is what keeps a glow
    to the notes that are actually sounding.

    The attack eases out, curling gently into the hold rather than
    meeting it at a corner, and the release eases out too, leaving the
    hold at once and landing softly on nothing the way a note rings out.
    The hump is `presets.swell_scale`'s: up on EASE_IN, gathering pace
    the way a crescendo grows, down on EASE_OUT, so both of its joins
    with the hold are smooth as well (Marcus, 2026-08-03).

    It takes a spec `clamp_spec` has already put in order.
    """
    held = spec.sustain * amount
    top = spec.swell_level * amount
    hold_end = 1.0 - spec.release
    # Times as fractions first, so every reading of the shape is in the
    # units the user authored it in; the span multiplies in at the end.
    if spec.attack > 0.0:
        points = [(0.0, 0.0, Easing.STEP),
                  (spec.attack, held, Easing.EASE_OUT)]
    else:
        points = [(0.0, held, Easing.STEP)]     # up at the trigger
    if spec.swell_on:
        points.append((spec.swell_pos, top, Easing.EASE_IN))
    if hold_end > points[-1][0]:
        points.append((hold_end, held,
                       Easing.EASE_OUT if spec.swell_on else Easing.LINEAR))
    if spec.release > 0.0:
        points.append((1.0, 0.0, Easing.EASE_OUT))
    else:
        # No release asked for, so the last point already sits at the
        # span's end: it drops to nothing there instead of holding.
        at, _value, easing = points[-1]
        points[-1] = (at, 0.0, easing)
    return Envelope(initial=0.0,
                    keyframes=tuple(Keyframe(at * seconds, value, easing)
                                    for at, value, easing in points))
