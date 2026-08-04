"""The stem command: pin one note's stem direction by hand.

Its own module for the reason `breaks.py` is — `layout.py` is already
near the ceiling, and this is its own small domain.

An ENGRAVING INPUT: Verovio draws the stem, so the flip is applied at
the prep seam and the score re-engraves. That means it arrives through
execute(), never preview() — a preview would re-engrave on every frame
of a gesture (PATTERNS, the ~0.25-1.3 s re-engrave).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from scoreanim.core.project.commands.base import Command, CommandError
from scoreanim.core.project.document import ProjectDoc, StemDirection
from scoreanim.core.score.identity import ElementId


@dataclass(frozen=True)
class SetStemDirection(Command):
    """Pin (or unpin) the direction of one stem.

    `direction=None` removes the entry, which hands the note back to the
    automatic rule. Nothing in the UI does that today — `F` cycles up
    and down only (Marcus, 2026-08-03) — but the command is the document
    seam, not the keystroke, and a sparse map wants a way back to empty.

    One id, not a family: a stem mints no `:seg` continuation (the
    FINDING-5 fix), and a chord's heads already share one stem, so there
    is nothing to fan out over.
    """
    element_id: ElementId
    direction: StemDirection | None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not str(self.element_id):
            raise CommandError("no element to flip")
        if (self.direction is not None
                and not isinstance(self.direction, StemDirection)):
            raise CommandError(f"unknown stem direction {self.direction!r}")
        directions = dict(doc.stem_directions)
        if self.direction is None:
            directions.pop(self.element_id, None)
        else:
            directions[self.element_id] = self.direction
        return replace(doc, stem_directions=directions)

    def describe(self) -> str:
        # Says what it wrote, not what the key was called (the M3.5 rule)
        return "flip stem" if self.direction is not None else "reset stem"
