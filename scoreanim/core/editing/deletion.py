"""What may be deleted, and what "deleted" is allowed to mean.

**Deleting is for engraving and cosmetic cleanup ONLY. It never
rewrites the music.** A delete hides ink: the element stops being drawn
and stops being clickable, and nothing else changes — not the timing,
not the triggers, not the timemap, not how any other element animates.
Everything deleted can be brought back. That single sentence is what
decides the table below, so read it before adding a kind to it: if
removing the ink would change what the music SAYS, it does not belong
here, however convenient it would be.

That is why v1 deletes texts, slurs, hairpins and dynamics and nothing
else. Those four are marks ON the music — an editor's choices about
what to print. A notehead, a rest, a tie or a bar repeat IS the music,
and hiding one would leave the score saying something the recording
does not play. Scaffold (staff lines, barlines, brackets) is the page
itself, not an object anybody points at.

The mechanism is `LayoutOverride.hidden`, a schema slot since Phase 4
and used since Phase 9.2 to hide an engraved text behind its stage
overlay. Which brings the one subtlety in this module: an element
hidden BY an overlay is not a deleted element, and must never appear in
the deleted list — restoring it would put the engraved mark back on
screen underneath the replacement text that is still there. So
`deleted_families` subtracts the overlaid ids, and the overlay keeps
its own restore in the Texts dialog.

Pure policy, the `core/editing/breaks.py` shape: no Qt, no document
writes, no engraving.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Container, Iterable, Mapping

from scoreanim.core.animation.schedule import STATIC_KINDS
from scoreanim.core.editing.segments import source_of
from scoreanim.core.project.document import LayoutOverride
from scoreanim.core.project.stage_config import OVERLAY_PREFIX
from scoreanim.core.score.identity import ElementId, ElementKind
from scoreanim.core.selection.context import Selection
from scoreanim.core.selection.policy import measure_ordinal_of

# The whole deletable set (see the module docstring for why it is these
# four and not more). Marks ON the music, never the music itself.
DELETABLE_KINDS = frozenset({
    ElementKind.TEXT,          # tempo, expression, rehearsal, and the
                               # page furniture: part labels, measure
                               # numbers, headers and footers
    ElementKind.SLUR,
    ElementKind.HAIRPIN,
    ElementKind.DYNAMIC,
})

# Kinds that ARE the music. Split out from the rest only so the
# disabled action can say something true about why (the D1 rider: a
# disabled control names why it is disabled).
MUSIC_KINDS = frozenset({
    ElementKind.NOTEHEAD, ElementKind.STEM, ElementKind.FLAG,
    ElementKind.BEAM, ElementKind.ACCIDENTAL, ElementKind.LEDGER_LINES,
    ElementKind.ARTICULATION, ElementKind.TREMOLO, ElementKind.TIE,
    ElementKind.REST, ElementKind.MREST,
    ElementKind.SLASH, ElementKind.BAR_REPEAT,
})

# Status-tip text, phrased for a status bar and in plain words.
NO_SELECTION = "Select a text, slur, hairpin or dynamic to delete it"
MUSIC_INK = ("Notes, rests and ties stay — deleting tidies the "
             "engraving, it never changes the music")
SCAFFOLD_INK = ("Staff lines, barlines and brackets stay — they are the "
                "page itself, not an object on it")
NOT_DELETABLE = "Only texts, slurs, hairpins and dynamics can be deleted"
ALREADY_DELETED = ("This object is already deleted — restore it in the "
                   "Layout zone")

ENABLED_TIP = ("Hide this object. The music is unchanged — restore it "
               "in the Layout zone.")

_PAGE_RE = re.compile(r":p(\d+):")


@dataclass(frozen=True)
class DeleteAction:
    """What the Delete action should do with the current selection.

    `element_id` is what to hide; the caller fans it out over its `:seg`
    family (a spanner broken across systems is one object) before
    building the command. When `reason` is set the action is disabled
    and `element_id` is meaningless.
    """
    element_id: ElementId | None = None
    reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self.reason is None


def is_deletable(kind: ElementKind | None) -> bool:
    return kind is not None and kind in DELETABLE_KINDS


def reason_for_kind(kind: ElementKind) -> str:
    """Why this kind cannot be deleted, in words that say which rule is
    doing the refusing."""
    if kind in MUSIC_KINDS:
        return MUSIC_INK
    if kind in STATIC_KINDS:
        return SCAFFOLD_INK
    return NOT_DELETABLE


def resolve(selection: Selection | None,
            hidden_ids: Container[ElementId] = ()) -> DeleteAction:
    """The whole policy, in the order the decisions were ruled."""
    if selection is None:
        return DeleteAction(reason=NO_SELECTION)
    if not is_deletable(selection.kind):
        return DeleteAction(reason=reason_for_kind(selection.kind))
    if selection.element_id in hidden_ids:
        # Not reachable by clicking — hidden ink is not hit-testable —
        # but the action can also be triggered from the menu, and a
        # second delete of the same thing should say so rather than
        # write an override that changes nothing.
        return DeleteAction(reason=ALREADY_DELETED)
    return DeleteAction(element_id=selection.element_id)


# -- what has been deleted --------------------------------------------------

def overlaid_ids(stage_text_ids: Iterable[str]) -> frozenset[ElementId]:
    """The engraved ids that a stage overlay is currently standing in
    for — hidden, but replaced rather than deleted."""
    return frozenset(
        ElementId(text_id[len(OVERLAY_PREFIX):])
        for text_id in stage_text_ids
        if str(text_id).startswith(OVERLAY_PREFIX))


def deleted_families(layout_overrides: Mapping[ElementId, LayoutOverride],
                     stage_text_ids: Iterable[str] = ()
                     ) -> tuple[tuple[ElementId, ...], ...]:
    """Every deleted object, one entry per object, in score order.

    An entry is a whole `:seg` family: a hairpin broken over three
    systems is three hidden ids and ONE deleted object, so it is one row
    in the readout and one restore. Ids overlaid by a stage text are
    subtracted (see the module docstring).

    Pure, so the readout has nothing to get wrong beyond drawing it.
    """
    replaced = overlaid_ids(stage_text_ids)
    families: dict[ElementId, list[ElementId]] = {}
    for eid, override in layout_overrides.items():
        if not override.hidden or eid in replaced:
            continue
        families.setdefault(source_of(eid), []).append(eid)
    return tuple(
        tuple(sorted(members, key=str))
        for _, members in sorted(families.items(), key=_family_order))


def deleted_ids(layout_overrides: Mapping[ElementId, LayoutOverride],
                stage_text_ids: Iterable[str] = ()
                ) -> tuple[ElementId, ...]:
    """Every deleted id, flat — what "restore all" writes."""
    return tuple(eid
                 for family in deleted_families(layout_overrides,
                                                stage_text_ids)
                 for eid in family)


def _family_order(item: tuple[ElementId, list[ElementId]]) -> tuple:
    """Score order: by measure, then by id. Ids with no measure (page
    furniture) sort last, together."""
    source = item[0]
    measure = measure_ordinal_of(source)
    return (measure is None, measure or 0, str(source))


def describe(element_id: ElementId) -> str:
    """One readout row's text, read straight off the id grammar.

    Pure and scene-free on purpose: the readout lists what the DOCUMENT
    holds, and an override outlives the engraving it was made against
    (rule 5's accepted staleness), so a row must still describe itself
    when the element is no longer loaded.
    """
    tokens = str(source_of(element_id)).split(":")
    kind = tokens[-2].replace("_", " ") if len(tokens) >= 2 else str(element_id)
    part = tokens[0] if tokens and tokens[0] != "score" else None
    measure = measure_ordinal_of(element_id)
    if measure is not None:
        where = f"m{measure}"
    else:
        page = _PAGE_RE.search(str(element_id))
        where = f"page {page.group(1)}" if page else ""
    if not where:
        return f"{kind} ({part})" if part else kind
    return f"{where}: {kind} ({part})" if part else f"{where}: {kind}"
