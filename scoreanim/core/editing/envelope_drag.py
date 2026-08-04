"""What a drag on an envelope's picture MEANS.

The pure half of the envelope editor (`ui/envelope_editor.py`), the
`nudge` stack's shape: this module owns the arithmetic and the policy,
and the widget owns the paint and the mouse.

The picture is the classic synthesizer one. Time runs left to right
across the span the shape plays over, 0 at the left edge and 1 at the
right; level runs bottom to top, 0 at the bottom and 1 at the top. Both
axes are fractions, never seconds and never pixels, so a canvas of any
size draws the same shape (`EnvelopeSpec`).

Four handles, one drag function each:

  attack     the corner where the rise meets the hold — moves sideways
  sustain    the held part — moves up and down
  release    the corner where the hold gives way to the fall — sideways
  swell      the hump's top, when there is one — both ways

**A handle stops at its neighbour, live.** Each drag clamps against
whatever is beside it before it returns, so the shape being shown is
always one that can be played: the user sees the handle stop rather
than seeing a value be corrected after the fact. Every result also goes
through `clamp_spec`, the one authority for the ordering, so an invalid
envelope cannot leave this module even if a caller asks for one.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, replace

from scoreanim.core.animation.envelope_shape import (MIN_GAP, EnvelopeSpec,
                                                     clamp_spec)


class Handle(enum.Enum):
    """The four things a user can take hold of."""
    ATTACK = enum.auto()
    SUSTAIN = enum.auto()
    RELEASE = enum.auto()
    SWELL = enum.auto()


@dataclass(frozen=True)
class Box:
    """The rectangle the curve is drawn in, in whatever units the caller
    paints in (pixels, for the widget). `y` is its TOP edge, the screen
    convention, so level 1 sits at `y` and level 0 at `y + h`."""
    x: float
    y: float
    w: float
    h: float


# -- where a value sits, and what a position means --------------------------
#
# Four functions, two pairs of inverses. `frac_of(x_of(f)) == f` and
# `level_of(y_of(v)) == v` for every value in range, which is what lets
# a drag be expressed in the same units the shape is stored in.

def x_of(frac: float, box: Box) -> float:
    return box.x + frac * box.w


def frac_of(x: float, box: Box) -> float:
    return (x - box.x) / box.w if box.w else 0.0


def y_of(level: float, box: Box) -> float:
    return box.y + (1.0 - level) * box.h


def level_of(y: float, box: Box) -> float:
    return 1.0 - (y - box.y) / box.h if box.h else 0.0


def handle_points(spec: EnvelopeSpec,
                  box: Box) -> dict[Handle, tuple[float, float]]:
    """Where each handle is drawn. The swell is absent while it is off,
    which is what keeps it undraggable without a second rule.

    The attack corner sits at the top of the rise and the release corner
    at the end of the hold, both at the sustain level — so with no
    attack at all the first handle sits on the left edge, which is where
    the shape does start."""
    points = {
        Handle.ATTACK: (x_of(spec.attack, box), y_of(spec.sustain, box)),
        Handle.SUSTAIN: (x_of((spec.attack + 1.0 - spec.release) / 2.0, box),
                         y_of(spec.sustain, box)),
        Handle.RELEASE: (x_of(1.0 - spec.release, box),
                         y_of(spec.sustain, box)),
    }
    if spec.swell_on:
        points[Handle.SWELL] = (x_of(spec.swell_pos, box),
                                y_of(spec.swell_level, box))
    return points


def handle_at(spec: EnvelopeSpec, box: Box, x: float, y: float,
              radius: float) -> Handle | None:
    """Which handle a press at (x, y) takes hold of, or None.

    Order is the policy: the swell point first, because it rides ON the
    hold and would otherwise be buried under it; then the two corners;
    then the held segment, which is grabbed anywhere along its length
    within `radius` of the line rather than at a point."""
    points = handle_points(spec, box)
    for handle in (Handle.SWELL, Handle.ATTACK, Handle.RELEASE):
        point = points.get(handle)
        if point is not None and _near(point, x, y, radius):
            return handle
    left, right = x_of(spec.attack, box), x_of(1.0 - spec.release, box)
    if (left - radius <= x <= right + radius
            and abs(y - y_of(spec.sustain, box)) <= radius):
        return Handle.SUSTAIN
    return None


def _near(point: tuple[float, float], x: float, y: float,
          radius: float) -> bool:
    return abs(point[0] - x) <= radius and abs(point[1] - y) <= radius


# -- the drags ---------------------------------------------------------------

def drag(spec: EnvelopeSpec, handle: Handle, box: Box, x: float,
         y: float) -> EnvelopeSpec:
    """One mouse position, on whichever handle is being held."""
    if handle is Handle.ATTACK:
        return drag_attack(spec, box, x)
    if handle is Handle.RELEASE:
        return drag_release(spec, box, x)
    if handle is Handle.SUSTAIN:
        return drag_sustain(spec, box, y)
    return drag_swell(spec, box, x, y)


def drag_attack(spec: EnvelopeSpec, box: Box, x: float) -> EnvelopeSpec:
    """The rise gets longer or shorter. It stops one gap short of the
    swell point, or of the release corner when there is no swell — so
    the hold can never be squeezed out from the left."""
    ceiling = (spec.swell_pos if spec.swell_on else 1.0 - spec.release)
    return clamp_spec(replace(spec, attack=_between(
        frac_of(x, box), 0.0, max(0.0, ceiling - MIN_GAP))))


def drag_release(spec: EnvelopeSpec, box: Box, x: float) -> EnvelopeSpec:
    """The fall gets longer or shorter, dragged by the corner it starts
    at. It stops one gap past the swell point, or past the attack corner
    when there is no swell."""
    floor = (spec.swell_pos if spec.swell_on else spec.attack)
    hold_end = _between(frac_of(x, box), floor + MIN_GAP, 1.0)
    return clamp_spec(replace(spec, release=1.0 - hold_end))


def drag_sustain(spec: EnvelopeSpec, box: Box, y: float) -> EnvelopeSpec:
    """The held level rises or falls. Nothing else moves with it: the
    swell's own level is separate, so a hump can sit above the hold or
    dip below it."""
    return clamp_spec(replace(spec, sustain=_between(level_of(y, box),
                                                     0.0, 1.0)))


def drag_swell(spec: EnvelopeSpec, box: Box, x: float,
               y: float) -> EnvelopeSpec:
    """The hump's top, both ways at once. It stays strictly inside the
    hold, one gap clear of each corner."""
    if not spec.swell_on:
        return clamp_spec(spec)
    lo, hi = spec.attack + MIN_GAP, 1.0 - spec.release - MIN_GAP
    pos = _between(frac_of(x, box), lo, max(lo, hi))
    return clamp_spec(replace(spec, swell_pos=pos,
                              swell_level=_between(level_of(y, box),
                                                   0.0, 1.0)))


def _between(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))
