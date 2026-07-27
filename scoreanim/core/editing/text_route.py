"""What does double-clicking a text edit, and through which command?

M3 feature 1 builds an AFFORDANCE, not new document semantics: every
route below lands in a command that already existed before M3.

    part label      SetPartText        (prep-seam re-engrave, Phase 9.3)
    part abbrev.    SetPartText        (the other field of the same entry)
    stage text      EditStageText      (title/composer/lyricist, 9.1)
    tempo overlay   EditStageText      (an overlay IS a stage text)
    other engraved  AddTempoOverlay    (9.2, generalized — see below)

"The tempo-overlay mechanism generalized" costs nothing: AddTempoOverlay
never looked at `text_class`. Its docstring says so — "the doc has no
layout, so this cannot verify that element_id really is a tempo TEXT —
the UI guarantees it by filtering". And `seed_overlay_text` reads only
`glyph.texts[0]`, which every engraved TEXT has. So a system text or a
rehearsal mark hides behind a replacement stage text by exactly the same
hide-plus-replace shape, in one undo step, with no command edits.

**Ruling (Marcus, 2026-07-27): D5 stands.** Stage texts remain
UNSELECTABLE; double-click resolves through its own path instead. The
two gestures ask different questions — selection asks "which object did
the user pick", and under rule 13 an object carries a measure and a
part, which a stage text has none of; double-click asks "which editable
text is under the cursor", which a stage text plainly is. So the routes
here span both, while `AppState.selection` still never holds one.

Page furniture is deliberately NOT editable in place (v1): measure
numbers are navigation, and the page header/footer is the Dorico
title-block simplification tracked as BACKLOG 4 — editing it here would
half-solve that in a place nobody would look for it.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)

# Engraved TEXT sub-classes that route to the part-name override, and
# which field of it each one carries.
PART_LABEL_CLASSES = {"label": "name", "labelAbbr": "abbreviation"}

# Engraved TEXT sub-classes with no in-place edit in v1 (see module
# docstring). Everything else engraved routes to the overlay mechanism.
FURNITURE_CLASSES = frozenset({"mNum", "pgHead", "pgFoot"})


class TextRoute(enum.Enum):
    PART_LABEL = enum.auto()      # SetPartText on `field`
    STAGE_TEXT = enum.auto()      # EditStageText on an existing text
    ENGRAVED_OVERLAY = enum.auto()  # AddTempoOverlay, seeded from the ink


@dataclass(frozen=True)
class TextTarget:
    """Everything the UI needs to build the command, and nothing more."""
    route: TextRoute
    element_id: ElementId
    part: PartId | None = None      # PART_LABEL only
    field: str | None = None        # PART_LABEL only: name | abbreviation


def route_for(identity: ElementIdentity | None,
              element_id: ElementId,
              text_class: str | None = None) -> TextTarget | None:
    """The route for one hit item, or None when it is not editable text.

    `identity` is None exactly for stage texts (`ElementItem(identity=
    None)`), which is also what makes them unselectable — so the same
    one field separates the two families here.
    """
    if identity is None:
        # a stage text: the header block, or a tempo/text overlay. Both
        # edit through EditStageText on their own id.
        return TextTarget(TextRoute.STAGE_TEXT, element_id)

    if identity.kind is not ElementKind.TEXT:
        return None                              # not text: nothing to edit

    field = PART_LABEL_CLASSES.get(text_class or "")
    if field is not None:
        if identity.part is None:
            return None                          # a label with no part to name
        return TextTarget(TextRoute.PART_LABEL, element_id,
                          part=identity.part, field=field)

    if text_class in FURNITURE_CLASSES:
        return None

    return TextTarget(TextRoute.ENGRAVED_OVERLAY, element_id)
