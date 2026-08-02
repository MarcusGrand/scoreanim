"""The System pulse block: where its values live, and its knobs.

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

from scoreanim.core.animation.pulse import (DEFAULT_AMOUNT,
                                            DEFAULT_NOTES_FOR_FULL,
                                            DEFAULT_POP_AMOUNT,
                                            DEFAULT_SETTLE_S)
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


# Two ways to move a system, a knob each, and they read as the pair
# they are: one follows the recording, the other follows the notes. Both
# are per cent in the box and a fraction in the document — the swell
# Peak precedent — and both boxes stop at 20 %, because a whole system
# is a big thing to move: 5 % is already a lot of breath. The two
# amounts add, so a page with both on can reach 40 %.
#
# The pop's shape knobs wait on its amount, the way Quiet and Loud wait
# on the volume response's: at 0 they describe a bump nothing is
# drawing.
KNOBS: tuple[Number, ...] = (
    Number("Follow volume", "amount", DEFAULT_AMOUNT, 0, 20, 1,
           "How much the whole page swells with the recording — every "
           "system grows and shrinks together, each around its own "
           "centre. 0 is off, and this half needs a recording loaded",
           suffix=" %", factor=100.0, integer=True),
    Number("Pop amount", "pop_amount", DEFAULT_POP_AMOUNT, 0, 20, 1,
           "How far a system jumps when notes land on it — the more "
           "noteheads on the beat, the bigger the jump. 0 is off; no "
           "recording needed",
           suffix=" %", factor=100.0, integer=True),
    Number("Notes for full", "notes_for_full", DEFAULT_NOTES_FOR_FULL,
           1, 24, 1,
           "How many noteheads at once make the strongest possible "
           "jump — a lone melody note is a slight tick, a chord across "
           "the staves the full amount",
           integer=True, enabled_by="pop_amount"),
    Number("Settle", "settle", DEFAULT_SETTLE_S, 0.01, 5.0, 0.05,
           "Seconds a jump takes to sink back to nothing. Overlapping "
           "jumps never stack — the biggest live one wins",
           suffix=" s", enabled_by="pop_amount"),
)
