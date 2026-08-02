"""How two effects on the same element combine, property by property.

An element may animate with several effects at once — "drop+fade". The
envelopes are never merged: two eased curves cannot be merged exactly at
their keyframes, so each effect keeps its own tracks, its own trigger
shift and its own timescale, and it is the RESULTS that combine, here,
at evaluation time.

One fixed table, one entry per property: an operation and a neutral
value. An effect that carries no track for a property contributes that
property's neutral, so it never has an opinion about a property it does
not animate.

Opacity combines with `min`, not multiply. Every opacity envelope starts
at the document's floor, so multiplying would put a combined ghost at
floor squared — below the floor the user asked for. `min` leaves it
exactly AT the floor, and while the note is coming in the dimmer of the
two wins, which is also the right look.

Every operation here is commutative, so the order of the effects never
matters — "drop+fade" and "fade+drop" animate the same.

The neutral column has a second reader: `modulate_state`, which pulls a
composed state toward or away from rest by a per-trigger gain (the
volume response, core/animation/intensity.py). Rest IS the neutral, so
the two live together.
"""
from __future__ import annotations

from typing import Callable, Mapping, Sequence

from scoreanim.core.animation.effect import (GLOW, OFFSET_X, OFFSET_Y,
                                             OPACITY, SCALE, PropertyId)


def _mul(a: float, b: float) -> float:
    return a * b


def _add(a: float, b: float) -> float:
    return a + b


# property → (how two values combine, the value that changes nothing)
COMPOSE_OPS: Mapping[PropertyId, tuple[Callable[[float, float], float],
                                       float]] = {
    OPACITY: (min, 1.0),
    SCALE: (_mul, 1.0),
    OFFSET_X: (_add, 0.0),
    OFFSET_Y: (_add, 0.0),
    # Two effects glowing at once take the BRIGHTER, they do not stack:
    # light that added would blow past full glow and leave a note
    # brighter than the effect ever asked for. Commutative, like every
    # other operation here.
    GLOW: (max, 0.0),
}


# Which properties a per-trigger gain may push further from rest, or
# hold closer to it. A list, not an if-chain (rule 6).
#
# OPACITY is deliberately not here, and never will be: a quiet note
# still has to become fully visible, or the score would be unreadable
# wherever the playing is soft. Loudness changes how a note MOVES, not
# whether it is there.
#
# GLOW is here: the halo is not what makes a note readable, so a loud
# note may burn brighter and a quiet one may barely light — the same
# thing the response does to a pop's size, on a different property.
MODULATED_PROPERTIES: frozenset[PropertyId] = frozenset({
    SCALE, OFFSET_X, OFFSET_Y, GLOW,
})


def modulate_state(state: Mapping[PropertyId, float],
                   gain: float) -> dict[PropertyId, float]:
    """Scale how far a composed state departs from rest:
    ``value' = neutral + (value - neutral) * gain``.

    Applied ONCE, to the finished state, so an element animating with
    two effects at once is modulated as one thing.

    Gain 1.0 hands the state straight back. That is not an optimization:
    ``n + (v - n) * 1.0`` can round to a different float than ``v``, and
    with the response off every value has to be exactly what it was
    before this feature existed.

    A property not in the table above — opacity, or one from a newer
    build — passes through untouched."""
    if gain == 1.0:
        return dict(state)
    out: dict[PropertyId, float] = {}
    for prop, value in state.items():
        rule = COMPOSE_OPS.get(prop)
        if prop in MODULATED_PROPERTIES and rule is not None:
            neutral = rule[1]
            out[prop] = neutral + (value - neutral) * gain
        else:
            out[prop] = value
    return out


def compose_states(states: Sequence[Mapping[PropertyId, float]]
                   ) -> dict[PropertyId, float]:
    """Combine several effects' states into one. A property any of them
    animates appears in the result; the ones that do not animate it
    contribute its neutral, and a neutral is by definition the value
    that changes nothing, so a silent effect simply drops out. A
    property this table does not know takes the last value given for it
    — the same fail-soft the applier uses for a property it cannot
    apply."""
    if len(states) == 1:
        return dict(states[0])
    out: dict[PropertyId, float] = {}
    for state in states:
        for prop, value in state.items():
            rule = COMPOSE_OPS.get(prop)
            if prop not in out or rule is None:
                out[prop] = value
            else:
                out[prop] = rule[0](out[prop], value)
    return out
