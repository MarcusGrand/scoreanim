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
"""
from __future__ import annotations

from typing import Callable, Mapping, Sequence

from scoreanim.core.animation.effect import (OFFSET_X, OFFSET_Y, OPACITY,
                                             SCALE, PropertyId)


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
}


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
