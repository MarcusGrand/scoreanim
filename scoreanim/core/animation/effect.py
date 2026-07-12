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
from typing import Mapping, NewType

PropertyId = NewType("PropertyId", str)

OPACITY = PropertyId("opacity")
SCALE = PropertyId("scale")     # factor around the element's stored anchor


class Easing(enum.Enum):
    STEP = enum.auto()      # hold the previous value; jump AT this keyframe
    LINEAR = enum.auto()    # lerp from the previous keyframe into this one


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
        if nxt is not None and nxt.easing is Easing.LINEAR:
            f = (t_rel - kfs[i].t_rel) / (nxt.t_rel - kfs[i].t_rel)
            return kfs[i].value + f * (nxt.value - kfs[i].value)
        return kfs[i].value


@dataclass(frozen=True)
class Effect:
    name: str
    tracks: Mapping[PropertyId, Envelope]

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
