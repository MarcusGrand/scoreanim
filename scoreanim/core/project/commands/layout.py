"""Layout commands: staff groups, condense groups, the Score Setup
batch, and part-label overrides — the changes that re-engrave via the
loader's applied-input diff — plus SetLayoutOverride (M3.2), which is
the one that does NOT re-engrave: a nudge is a delta applied on top of
the engraving, not an input to it."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from scoreanim.core.project.commands.base import Command, CommandError
from scoreanim.core.project.document import (CondenseGroup, LayoutOverride,
                                             PartTextOverride, ProjectDoc,
                                             StaffGroup, SystemBreak)
from scoreanim.core.score.identity import ElementId, PartId

# MusicXML group-symbol vocabulary ("none" excluded: removing the group
# is what RemoveStaffGroup is for)
_GROUP_SYMBOLS = frozenset({"bracket", "brace", "line", "square"})


def _validated_groups(groups: tuple[StaffGroup, ...],
                      part_order: tuple[PartId, ...]
                      ) -> tuple[StaffGroup, ...]:
    """Validate against the score's part order (runtime data — the doc
    stores intent only, so the UI supplies the order, like
    SetGlobalSwing.end_beat) and normalize by first-part position so
    the prep-seam injection order is deterministic regardless of the
    order groups were added in."""
    index = {pid: i for i, pid in enumerate(part_order)}
    claimed: dict[PartId, int] = {}
    for g_i, group in enumerate(groups):
        if not group.parts:
            raise CommandError("staff group has no parts")
        if group.symbol not in _GROUP_SYMBOLS:
            raise CommandError(
                f"bad group symbol {group.symbol!r} "
                f"(want one of {'/'.join(sorted(_GROUP_SYMBOLS))})")
        if len(set(group.parts)) != len(group.parts):
            raise CommandError(f"duplicate part in group {group.parts}")
        for pid in group.parts:
            if pid not in index:
                raise CommandError(f"unknown part {pid!r}")
            if pid in claimed:
                raise CommandError(f"part {pid!r} is already in "
                                   f"another staff group")
            claimed[pid] = g_i
        positions = [index[pid] for pid in group.parts]
        if positions != list(range(positions[0], positions[0] + len(positions))):
            raise CommandError("staff group parts must be contiguous "
                               f"in score order, got {group.parts}")
    return tuple(sorted(groups, key=lambda g: index[g.parts[0]]))


def _group_at(doc: ProjectDoc, group_index: int) -> StaffGroup:
    if not 0 <= group_index < len(doc.staff_groups):
        raise CommandError(f"no staff group #{group_index}")
    return doc.staff_groups[group_index]


@dataclass(frozen=True)
class AddStaffGroup(Command):
    """Grouped staves get a bracket/brace and (optionally) joined
    barlines, re-derived by <part-group> injection at the prep seam —
    the doc stores only this intent (rule 5)."""
    group: StaffGroup
    part_order: tuple[PartId, ...]     # score order, from the loaded score

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        groups = _validated_groups(doc.staff_groups + (self.group,),
                                   self.part_order)
        return replace(doc, staff_groups=groups)

    def describe(self) -> str:
        return "add staff group"


@dataclass(frozen=True)
class EditStaffGroup(Command):
    index: int                         # position in doc.staff_groups
    group: StaffGroup
    part_order: tuple[PartId, ...]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        _group_at(doc, self.index)
        groups = tuple(self.group if i == self.index else g
                       for i, g in enumerate(doc.staff_groups))
        return replace(doc,
                       staff_groups=_validated_groups(groups,
                                                      self.part_order))

    def describe(self) -> str:
        return "edit staff group"


@dataclass(frozen=True)
class RemoveStaffGroup(Command):
    index: int

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        _group_at(doc, self.index)
        groups = tuple(g for i, g in enumerate(doc.staff_groups)
                       if i != self.index)
        return replace(doc, staff_groups=groups)

    def describe(self) -> str:
        return "remove staff group"


# ---------------------------------------------------------------------------
# condense groups (Phase 12.3)
# ---------------------------------------------------------------------------

def _validated_condense_groups(groups: tuple[CondenseGroup, ...],
                               part_order: tuple[PartId, ...]
                               ) -> tuple[CondenseGroup, ...]:
    """Validate against the score's part order (runtime data — the
    part_order idiom) and normalize by first-part position so the prep-seam
    merge order is deterministic. A part may be in at most one condense
    group; parts must be contiguous and there must be >= 2 of them."""
    index = {pid: i for i, pid in enumerate(part_order)}
    claimed: dict[PartId, int] = {}
    for g_i, group in enumerate(groups):
        if len(group.parts) < 2:
            raise CommandError(
                f"condense group needs >= 2 parts, got {group.parts}")
        if len(set(group.parts)) != len(group.parts):
            raise CommandError(f"duplicate part in condense group {group.parts}")
        for pid in group.parts:
            if pid not in index:
                raise CommandError(f"unknown part {pid!r}")
            if pid in claimed:
                raise CommandError(f"part {pid!r} is already in "
                                   f"another condense group")
            claimed[pid] = g_i
        positions = [index[pid] for pid in group.parts]
        if positions != list(range(positions[0], positions[0] + len(positions))):
            raise CommandError("condense group parts must be contiguous "
                               f"in score order, got {group.parts}")
    return tuple(sorted(groups, key=lambda g: index[g.parts[0]]))


def _condense_at(doc: ProjectDoc, group_index: int) -> CondenseGroup:
    if not 0 <= group_index < len(doc.condense_groups):
        raise CommandError(f"no condense group #{group_index}")
    return doc.condense_groups[group_index]


@dataclass(frozen=True)
class AddCondenseGroup(Command):
    """Merge contiguous like parts onto one staff (one voice per player),
    re-derived by rewriting the part-list at the prep seam — the doc stores
    only this intent (rule 5). ElementIds shift, like a part rename."""
    group: CondenseGroup
    part_order: tuple[PartId, ...]     # score order, from the loaded score

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        groups = _validated_condense_groups(
            doc.condense_groups + (self.group,), self.part_order)
        return replace(doc, condense_groups=groups)

    def describe(self) -> str:
        return "condense parts"


@dataclass(frozen=True)
class EditCondenseGroup(Command):
    index: int                         # position in doc.condense_groups
    group: CondenseGroup
    part_order: tuple[PartId, ...]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        _condense_at(doc, self.index)
        groups = tuple(self.group if i == self.index else g
                       for i, g in enumerate(doc.condense_groups))
        return replace(doc, condense_groups=_validated_condense_groups(
            groups, self.part_order))

    def describe(self) -> str:
        return "edit condense group"


@dataclass(frozen=True)
class RemoveCondenseGroup(Command):
    index: int

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        _condense_at(doc, self.index)
        groups = tuple(g for i, g in enumerate(doc.condense_groups)
                       if i != self.index)
        return replace(doc, condense_groups=groups)

    def describe(self) -> str:
        return "uncondense parts"


@dataclass(frozen=True)
class ApplyScoreSetup(Command):
    """Batch the load-time layout choices — condense groups, staff groups,
    and hide-empty-staves — into ONE undoable step (ruling c, Phase 12.4).
    The Score Setup dialog gathers all choices and applies them together,
    so a score that re-engraves slowly (complex2 ~20 s) re-engraves ONCE
    instead of once per change. There is no generic macro command; this is
    the 'fat apply' idiom (AddTempoOverlay's shape). Both group sets are
    validated against the score's part order (runtime data)."""
    condense_groups: tuple[CondenseGroup, ...]
    staff_groups: tuple[StaffGroup, ...]
    hide_empty_staves: bool
    part_order: tuple[PartId, ...]
    hide_first_system: bool = False

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return replace(
            doc,
            condense_groups=_validated_condense_groups(
                self.condense_groups, self.part_order),
            staff_groups=_validated_groups(self.staff_groups, self.part_order),
            hide_empty_staves=self.hide_empty_staves,
            hide_first_system=self.hide_first_system,
        )

    def describe(self) -> str:
        return "apply score setup"


# ---------------------------------------------------------------------------
# part texts (Phase 9.3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SetPartText(Command):
    """Part-label override — an ENGRAVING INPUT like staff_groups: the
    window re-engraves on the text_overrides diff (~0.6 s, so this
    arrives via execute(), never preview()). One wholesale entry per
    part (the editor edits both fields in one OK); None keeps the
    score's own text, "" is an explicit blank (Verovio suppresses the
    label — spikes/NOTES.md "Phase 9"); None+None clears the entry so
    the doc stays sparse (the SetElementStyle idiom). `known_parts` is
    runtime data from the loaded score (the part_order trust model)."""
    part: PartId
    name: str | None
    abbreviation: str | None
    known_parts: tuple[PartId, ...]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if self.part not in self.known_parts:
            raise CommandError(f"unknown part {self.part!r}")
        overrides = dict(doc.text_overrides)
        if self.name is None and self.abbreviation is None:
            overrides.pop(self.part, None)
        else:
            overrides[self.part] = PartTextOverride(
                name=self.name, abbreviation=self.abbreviation)
        return replace(doc, text_overrides=overrides)

    def describe(self) -> str:
        return "set part name"


# ---------------------------------------------------------------------------
# system breaks (M5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SetSystemBreak(Command):
    """Force or suppress the system break at one measure — the app's first
    layout-INTENT edit, and an ENGRAVING INPUT like staff_groups: the
    window re-engraves on the system_break_overrides diff (measured 0.25 s
    on testscore, 1.28 s on bigband1 — brief §3.6 F4), so this arrives via
    execute(), never preview().

    `ordinal` is the 1-based document-order ordinal of the measure that
    would START the system (D2), never a printed number — the same
    identity `_repaginate`'s break_measures use, so the two break
    mechanisms read the same way at the seam.

    `mode=None` POPS the entry, returning that measure to whatever the
    file encodes, so the doc stays sparse (the SetElementStyle idiom) and
    the gesture is perfectly reversible. Ordinals are validated as >= 1
    only: the command deliberately does NOT know the engraved layout (no
    command does), so an ordinal past the end of the score is stored and
    left inert, with the load-time warning of D10 doing the telling —
    rule 5's stated staleness trade, and `_repaginate`'s own behaviour
    for an out-of-range plan entry.
    """
    ordinal: int
    mode: SystemBreak | None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if self.ordinal < 1:
            raise CommandError(f"measure ordinal {self.ordinal} is not >= 1")
        overrides = dict(doc.system_break_overrides)
        if self.mode is None:
            overrides.pop(self.ordinal, None)
        else:
            overrides[self.ordinal] = self.mode
        return replace(doc, system_break_overrides=overrides)

    def describe(self) -> str:
        if self.mode is None:
            return "clear system break"
        if self.mode is SystemBreak.FORCE:
            return "force system break"
        return "suppress system break"


@dataclass(frozen=True)
class SetLayoutOverride(Command):
    """Nudge one element by a dx/dy delta (M3.2) — the first consumer of
    `LayoutOverride.dx/dy`, which have been schema slots since Phase 4.

    Deltas are in PAGE units and keyed by musical ElementId, never
    absolute pixels (rule 5): the engraved position re-derives on every
    load and the delta rides on top of whatever it turns out to be.
    Override staleness across a re-engrave stays the accepted trade
    (ARCHITECTURE §4) — an id that no longer exists is simply skipped
    when the overrides are applied.

    ONE command per gesture, not per mouse-move (rule 8): a drag
    previews by moving the item and executes this once on release, so a
    drag is a single undo entry. The delta is ABSOLUTE, not incremental,
    which is what lets that work — the preview can move freely and the
    commit still describes the whole gesture.

    `hidden` is preserved: a nudged tempo mark that is hidden behind its
    overlay must stay hidden. The entry disappears entirely when it is
    back at the default (the SetElementStyle sparse-doc idiom)."""
    element_id: ElementId
    dx: float
    dy: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not (math.isfinite(self.dx) and math.isfinite(self.dy)):
            raise CommandError(f"nudge ({self.dx!r}, {self.dy!r}) not finite")
        overrides = dict(doc.layout_overrides)
        updated = replace(overrides.get(self.element_id, LayoutOverride()),
                          dx=float(self.dx), dy=float(self.dy))
        if updated == LayoutOverride():
            overrides.pop(self.element_id, None)
        else:
            overrides[self.element_id] = updated
        return replace(doc, layout_overrides=overrides)

    def describe(self) -> str:
        return "move element"
