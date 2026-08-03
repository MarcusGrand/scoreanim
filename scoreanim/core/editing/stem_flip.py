"""Which stem `F` flips, and which way it is pointing now.

The `deletion.py` shape: a pure `resolve(...) -> FlipAction`, and when
the action is disabled its `reason` says why in plain words (the D1
rider). No Qt, so it is testable headless (rule 1).

Two things make this policy less obvious than the nudge or the delete:

**The user selects a NOTE, but the document keys a STEM.** Clicking
almost always lands on the notehead — the hit policy prefers it, and
deliberately, since a stem's authored Rect has zero width and would
otherwise win every click. So the selected id is usually
`…:note:3` while the thing to flip is `…:stem:1`. The two are joined
through the group the schedule already uses,
`(part, staff, voice, quantized onset)` — the same key `scale_groups`
pivots on. Nothing new is stored and the adapter is untouched.

A chord's heads all share one group and therefore one stem, so it does
not matter which head was clicked: the chord has one stem and it flips
as one. That is also why the command needs no fan-out.

**Nothing records which way a stem points.** The adapter keeps musical
identity, not geometry, so the current direction is READ off the drawn
ink by `scale_groups.stem_is_up` — the same reading the pop pivot and
the stem cap already rely on. `F` then asks for the opposite. That is
what makes the key a flip rather than a toggle between two stored
states: the thing it flips away from is whatever is on the page,
whether that came from the automatic rule or from an earlier press.
"""
from __future__ import annotations

from dataclasses import dataclass

from scoreanim.core.animation.scale_groups import (group_key, heads_by_group,
                                                   stem_is_up)
from scoreanim.core.animation.schedule import STATIC_KINDS
from scoreanim.core.engraving.types import Layout, RenderedElement
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind)
from scoreanim.core.score.musicxml_stems import StemDirection
from scoreanim.core.selection.context import Selection

# Selecting any of these means "this note". They all hang off one
# notehead group, so each resolves to exactly one stem.
FLIPPABLE_KINDS = frozenset({
    ElementKind.NOTEHEAD,
    ElementKind.STEM,
    ElementKind.FLAG,
})

# Status-tip text, phrased for a status bar and in plain words.
NO_SELECTION = "Select a note and press F to flip its stem"
NOT_A_NOTE = "Only a note's stem can be flipped"
SCAFFOLD_INK = ("Staff lines, barlines and brackets have no stem — they "
                "are the page itself, not a note on it")
NO_STEM = "This note has no stem to flip"

ENABLED_TIP = "Point this stem the other way"


@dataclass(frozen=True)
class FlipAction:
    """What `F` should do with the current selection.

    `element_id` is the STEM to pin — never the notehead that was
    clicked — and `direction` is the way to point it, which is always
    the opposite of the way it is drawn now. When `reason` is set the
    action is disabled and the other two are meaningless.
    """
    element_id: ElementId | None = None
    direction: StemDirection | None = None
    reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self.reason is None


def is_flippable(kind: ElementKind | None) -> bool:
    return kind is not None and kind in FLIPPABLE_KINDS


def reason_for_kind(kind: ElementKind) -> str:
    """Why this kind has no stem to flip, naming the rule that refuses."""
    if kind in STATIC_KINDS:
        return SCAFFOLD_INK
    return NOT_A_NOTE


def stem_of(identity: ElementIdentity,
            layout: Layout) -> RenderedElement | None:
    """The one stem belonging to the selected object's note group, or
    None when that note draws no stem (a whole note, a slash).

    Untimed ink — a title, a part label, page furniture — has no onset
    and therefore no group, so it is None before the scan rather than a
    crash inside the quantizer.
    """
    if identity.onset is None:
        return None
    key = group_key(identity)
    for element in layout.elements:
        if (element.identity.kind is ElementKind.STEM
                and group_key(element.identity) == key):
            return element
    return None


def resolve(selection: Selection | None,
            layout: Layout | None) -> FlipAction:
    """The whole policy, in the order the decisions were ruled."""
    if selection is None:
        return FlipAction(reason=NO_SELECTION)
    if not is_flippable(selection.kind):
        return FlipAction(reason=reason_for_kind(selection.kind))
    if layout is None:
        return FlipAction(reason=NO_SELECTION)
    stem = stem_of(selection.obj, layout)
    if stem is None:
        return FlipAction(reason=NO_STEM)
    heads = heads_by_group(layout).get(group_key(stem.identity))
    if not heads:
        # A stem with no notehead in its group is ink we cannot reason
        # about — refuse rather than guess a direction from nothing.
        return FlipAction(reason=NO_STEM)
    now_up = stem_is_up(stem, heads)
    return FlipAction(
        element_id=stem.identity.element_id,
        direction=StemDirection.DOWN if now_up else StemDirection.UP)
