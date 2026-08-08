"""The re-timing command: move one element's fire time by hand.

Its own module for the reason `stems.py` is — its own small domain.

NOT an engraving input: the schedule re-derives from the retained load
(no Verovio, no scene rebuild), so this command is cheap and safe to
execute per button press. The beat is ABSOLUTE, on the performance
axis — "this dynamic fires at beat 42.5" — so the element stays where
the user put it even if the schedule rules change later.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from scoreanim.core.project.commands.base import Command, CommandError
from scoreanim.core.project.document import Beats, ProjectDoc
from scoreanim.core.score.identity import ElementId


@dataclass(frozen=True)
class SetTriggerBeat(Command):
    """Move (or reset) when one element's animation fires.

    `beats=None` removes the entry, which hands the element back to
    the automatic schedule — the panel's Reset button, and a sparse
    map's way back to empty.

    Which elements may be re-timed is policy the schedule enforces
    (core/animation/retime.py), not this command: the document stores
    intent, and an id that turns out to be unmovable is inert and
    warned at load rather than rejected here (rule 5's staleness
    trade cuts both ways).
    """
    element_id: ElementId
    beats: Beats | None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not str(self.element_id):
            raise CommandError("no element to move")
        if self.beats is not None:
            if (isinstance(self.beats, bool)
                    or not isinstance(self.beats, (int, float))
                    or not math.isfinite(self.beats)):
                raise CommandError(f"bad trigger beat {self.beats!r}")
        overrides = dict(doc.trigger_overrides)
        if self.beats is None:
            overrides.pop(self.element_id, None)
        else:
            overrides[self.element_id] = float(self.beats)
        return replace(doc, trigger_overrides=overrides)

    def describe(self) -> str:
        # Says what it wrote, not what the key was called (the M3.5 rule)
        return "move onset" if self.beats is not None else "reset onset"
