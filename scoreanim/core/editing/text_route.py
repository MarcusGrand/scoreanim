"""What does double-clicking a text edit, and through which command?

M3 feature 1 builds an AFFORDANCE, not new document semantics: every
route below lands in a command that already existed before M3.

    part label      SetPartText        (prep-seam re-engrave, Phase 9.3)
    part abbrev.    SetPartText        (the other field of the same entry)
    condensed label EditCondenseGroup  (the merged label, M7 — see below)
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

**Condensed staves (ruling, Marcus 2026-07-30).** When parts are
condensed onto one staff, its label is the condense group's combined name,
and the group is where that name LIVES (`doc.condense_groups`). So editing
such a label rewrites the group, not the kept part's override. Writing
`SetPartText` would work — text overrides are applied after the condense
rewrite at the prep seam, so the override would win — but then the score
would show one label and the Score Setup dialog another. One name, one
place.

The condensed staff resolves to the group's KEPT part (measured,
spikes/label_part.py), so `parts[0]` is the only part that can reach this
route.
"""
from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)

# Engraved TEXT sub-classes that route to the part-name override, and
# which field of it each one carries.
PART_LABEL_CLASSES = {"label": "name", "labelAbbr": "abbreviation"}

# Engraved TEXT sub-classes with no in-place edit in v1 (see module
# docstring). Everything else engraved routes to the overlay mechanism.
FURNITURE_CLASSES = frozenset({"mNum", "pgHead", "pgFoot"})


def flat_part_order(engraved_order: Sequence[PartId],
                    condensed_groups: Sequence[Sequence[PartId]]
                    ) -> tuple[PartId, ...]:
    """The score's own part order, rebuilt from the CONDENSED one.

    Condensing merges parts at the prep seam, so the loaded score reports
    only the surviving parts — a condensed score's part list has no P2 in
    it. But the document's intent still names P2 (a condense group is a
    tuple of the score's parts), and the condense commands validate their
    groups against the part order they are handed. Handing them the
    condensed order makes every such command fail.

    The rewrite keeps each group's FIRST part where it was and drops the
    rest (`_apply_condense`), so putting each group's parts back at its
    kept part's position undoes it exactly.

    Parts the score no longer has are carried through as the document
    wrote them — rule 5 staleness is the document's problem to report,
    not something to silently drop here.
    """
    by_kept = {group[0]: tuple(group) for group in condensed_groups if group}
    out: list[PartId] = []
    for part in engraved_order:
        out.extend(by_kept.get(part, (part,)))
    return tuple(out)


class TextRoute(enum.Enum):
    PART_LABEL = enum.auto()      # SetPartText on `field`
    CONDENSE_LABEL = enum.auto()  # EditCondenseGroup `group` on `field`
    STAGE_TEXT = enum.auto()      # EditStageText on an existing text
    ENGRAVED_OVERLAY = enum.auto()  # AddTempoOverlay, seeded from the ink


@dataclass(frozen=True)
class TextTarget:
    """Everything the UI needs to build the command, and nothing more."""
    route: TextRoute
    element_id: ElementId
    part: PartId | None = None      # PART_LABEL only
    field: str | None = None        # label routes: name | abbreviation
    group: int | None = None        # CONDENSE_LABEL only: index in
                                    # doc.condense_groups


def route_for(identity: ElementIdentity | None,
              element_id: ElementId,
              text_class: str | None = None,
              condensed: Mapping[PartId, int] | None = None
              ) -> TextTarget | None:
    """The route for one hit item, or None when it is not editable text.

    `identity` is None exactly for stage texts (`ElementItem(identity=
    None)`), which is also what makes them unselectable — so the same
    one field separates the two families here.

    `condensed` maps each condense group's KEPT part to the group's index,
    so a merged staff's label edits the group instead of the part.
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
        group = (condensed or {}).get(identity.part)
        if group is not None:
            return TextTarget(TextRoute.CONDENSE_LABEL, element_id,
                              part=identity.part, field=field, group=group)
        return TextTarget(TextRoute.PART_LABEL, element_id,
                          part=identity.part, field=field)

    if text_class in FURNITURE_CLASSES:
        return None

    return TextTarget(TextRoute.ENGRAVED_OVERLAY, element_id)
