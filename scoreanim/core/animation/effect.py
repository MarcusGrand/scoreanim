"""Effects are data, not code (CLAUDE.md rule 6).

An Effect is a named bundle of (property, Envelope) tracks evaluated at
t_rel to the element's trigger. Adding an effect or a property means
adding data; the evaluator below never grows branches for it.

``Envelope.initial`` extends the ARCHITECTURE §3 sketch (ruled
2026-07-11): it is the value for t_rel before the first keyframe —
"floor before onset" is inexpressible with finite keyframes under hold
semantics otherwise.
"""
from __future__ import annotations

import enum
from bisect import bisect_right
from dataclasses import dataclass
from typing import Callable, Mapping, NewType

PropertyId = NewType("PropertyId", str)

OPACITY = PropertyId("opacity")
SCALE = PropertyId("scale")     # factor around the element's stored anchor
# How far the element sits from where it was engraved, in scene units:
# 0 is in place, negative y is up the page, positive x is to the right.
# The applier composes these with the document's own nudge, so a moved
# note still animates to the place the user moved it to.
OFFSET_X = PropertyId("offset_x")
OFFSET_Y = PropertyId("offset_y")
# How brightly the element's halo burns: 0 is no glow at all, 1 is full
# glow. An ordinary float track like any other — what the halo is
# COLOURED and how far it reaches are styling, not animation, and live
# in core/animation/glow.py.
GLOW = PropertyId("glow")


class Easing(enum.Enum):
    STEP = enum.auto()      # hold the previous value; jump AT this keyframe
    LINEAR = enum.auto()    # lerp from the previous keyframe into this one
    EASE_OUT = enum.auto()  # like LINEAR, but quick away and slow to arrive
    EASE_IN = enum.auto()   # like LINEAR, but slow away and quick to arrive
    EASE_OUT_BOUNCE = enum.auto()   # arrives early, then bounces to a stop


# The bounce curve, the standard piecewise one: four parabolas of the
# same steepness, each starting where the last one landed. It reaches
# the target at the end of the first, springs back part of the way, and
# settles over two smaller bounces. It never travels PAST the target,
# and it ends exactly on it — which is what makes a bouncing note land
# at exactly its engraved size.
_BOUNCE_N = 7.5625
_BOUNCE_D = 2.75


def _bounce(f: float) -> float:
    if f < 1.0 / _BOUNCE_D:
        return _BOUNCE_N * f * f
    if f < 2.0 / _BOUNCE_D:
        f -= 1.5 / _BOUNCE_D
        return _BOUNCE_N * f * f + 0.75
    if f < 2.5 / _BOUNCE_D:
        f -= 2.25 / _BOUNCE_D
        return _BOUNCE_N * f * f + 0.9375
    f -= 2.625 / _BOUNCE_D
    return _BOUNCE_N * f * f + 0.984375


# How far along the move each curve is at fraction f of the gap between
# the two keyframes. Data, not branches: a new curve is a new entry.
# STEP is absent on purpose — it holds instead of moving.
_CURVES: Mapping[Easing, Callable[[float], float]] = {
    Easing.LINEAR: lambda f: f,
    Easing.EASE_OUT: lambda f: 1.0 - (1.0 - f) ** 3,
    Easing.EASE_IN: lambda f: f ** 3,
    Easing.EASE_OUT_BOUNCE: _bounce,
}


@dataclass(frozen=True)
class Keyframe:
    t_rel: float            # seconds relative to the element's trigger
    value: float
    easing: Easing = Easing.STEP


@dataclass(frozen=True)
class Envelope:
    initial: float                      # value for t_rel < keyframes[0].t_rel
    keyframes: tuple[Keyframe, ...]

    def __post_init__(self) -> None:
        for a, b in zip(self.keyframes, self.keyframes[1:]):
            if b.t_rel <= a.t_rel:
                raise ValueError("keyframes must be strictly increasing in t_rel")
        if self.keyframes and self.keyframes[0].easing is not Easing.STEP:
            raise ValueError("first keyframe must be STEP (nothing to lerp from)")

    def value_at(self, t_rel: float) -> float:
        kfs = self.keyframes
        if not kfs or t_rel < kfs[0].t_rel:
            return self.initial
        i = bisect_right([k.t_rel for k in kfs], t_rel) - 1
        nxt = kfs[i + 1] if i + 1 < len(kfs) else None
        curve = _CURVES.get(nxt.easing) if nxt is not None else None
        if curve is not None:
            f = (t_rel - kfs[i].t_rel) / (nxt.t_rel - kfs[i].t_rel)
            return kfs[i].value + curve(f) * (nxt.value - kfs[i].value)
        return kfs[i].value


@dataclass(frozen=True)
class Effect:
    name: str
    tracks: Mapping[PropertyId, Envelope]
    # M4 scalar data the applier consumes GENERICALLY (rule 6 amendment):
    # neither is ever branched on by effect name.
    # Signed seconds the WHOLE effect (opacity step and scale peak as one
    # unit) moves relative to the trigger — the "Peak offset" knob (F3):
    # negative shifts everything early, including when the note appears.
    # Absolute seconds, applied BEFORE any timescale division.
    trigger_shift: float = 0.0
    # When True the applier stretches this effect's settle to each
    # element's own engraved note value (timescale = dur_seconds /
    # duration, resolved per element — F7); the kernel itself only ever
    # sees the resulting scalar.
    settle_to_note_value: bool = False
    # When True an element carrying this effect is modulated by how loud
    # the recording is RIGHT NOW, instead of by the one average gain
    # over its whole note (core/animation/intensity.py). Like the flag
    # above, the kernel never sees it: it only changes which number
    # reaches modulate_state.
    follow_volume: bool = False

    def state_at(self, t_rel: float) -> dict[PropertyId, float]:
        return {pid: env.value_at(t_rel) for pid, env in self.tracks.items()}

    @property
    def duration(self) -> float:
        """Last keyframe time across all tracks: 0 for pure step effects;
        positive for timed effects, which need re-evaluation within
        [trigger, trigger + duration] (the applier's transition window)."""
        return max((kf.t_rel for env in self.tracks.values()
                    for kf in env.keyframes), default=0.0)


def appear(floor: float) -> Effect:
    """Floor opacity before the trigger, full at and after it (inclusive)."""
    return Effect("appear", {OPACITY: Envelope(
        initial=floor, keyframes=(Keyframe(0.0, 1.0, Easing.STEP),))})
