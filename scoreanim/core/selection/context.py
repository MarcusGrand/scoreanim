"""Selection: the object the user picked, and the context it carries.

CLAUDE.md rule 13 — selection is OBJECT-first. The user picks a notehead,
a dynamic, a hairpin, a text, a barline; a measure is never itself a
selection target. Picking an object implicitly carries two more levels:
the measure it sits in, and the part whose staff it sits on.

Both are DERIVED, and derived on read — this type stores exactly one
thing, the object's identity, and computes the rest from the element id
grammar (via ``measure_ordinal_of``) and from the identity's own part
field. That is the whole point of the type: there is one source of truth
for "which measure is this in", never a second field to keep in step and
never a geometric answer that could disagree with the id.

Consumers: the Selection panel reads all three levels (object primary,
measure and part as context — the stage shows only the object, ruling
2026-07-27); M3 keys a per-element style override off ``obj.element_id``;
M5 reads a barline's ``measure_ordinal``. Nothing here is document
state — selection is transient (rule 13, and rule 5 behind it).
"""

from __future__ import annotations

from dataclasses import dataclass

from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)
from scoreanim.core.selection.policy import measure_ordinal_of


@dataclass(frozen=True)
class Selection:
    """One selected object, plus the context that follows from it."""

    obj: ElementIdentity

    # -- the object --------------------------------------------------------

    @property
    def element_id(self) -> ElementId:
        return self.obj.element_id

    @property
    def kind(self) -> ElementKind:
        return self.obj.kind

    # -- what it carries ---------------------------------------------------

    @property
    def part(self) -> PartId | None:
        """The part whose staff the object sits on. None for score-level
        ink (barlines, staff lines, page furniture) — carried, never
        chosen, so it is read straight off the identity the adapter
        minted rather than looked up by position."""
        return self.obj.part

    @property
    def part_name(self) -> str | None:
        return self.obj.part_name

    @property
    def measure_ordinal(self) -> int | None:
        """The 1-based document-order measure the object sits in, parsed
        out of its id. None for ids that genuinely have no measure —
        system-scoped ink and page furniture (a part label). NOT the
        printed number: a Dorico "X0" pickup makes the two differ for a
        whole score, so callers wanting the label look the ordinal up in
        the measure table (the Selection panel does)."""
        return measure_ordinal_of(self.obj.element_id)
