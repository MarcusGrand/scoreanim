"""The System pulse block: where its value lives, and its one knob.

The Volume response block's twin, and built the same way — data plus a
small store, riding the `KnobGroup` machinery every preset's options use
(`ui/panels/effect_knobs.py`). Only the document field differs.

Like that block it is always on screen: it is not an effect, so the
"show the options of the effect you are using" rule has nothing to say
about it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from scoreanim.core.animation.pulse import DEFAULT_AMOUNT
from scoreanim.core.project import Command, ProjectDoc, SetPulseParam
from scoreanim.ui.panels.effect_knobs import Number

TITLE = "System pulse"


@dataclass(frozen=True)
class PulseStore:
    """The sparse `style.pulse` map."""

    def stored(self, doc: ProjectDoc) -> Mapping[str, object]:
        return doc.style.pulse

    def has_values(self, doc: ProjectDoc) -> bool:
        return bool(doc.style.pulse)

    def command(self, key: str,
                value: float | int | bool | None) -> Command:
        return SetPulseParam(key, value)


# Per cent in the box, a fraction in the document — the swell Peak
# precedent. The box stops at 20 % because a whole system is a big
# thing to move: 5 % is already a lot of breath.
KNOBS: tuple[Number, ...] = (
    Number("Amount", "amount", DEFAULT_AMOUNT, 0, 20, 1,
           "How much the whole page swells with the recording — every "
           "system grows and shrinks together, each around its own "
           "centre. 0 is off",
           suffix=" %", factor=100.0, integer=True),
)
