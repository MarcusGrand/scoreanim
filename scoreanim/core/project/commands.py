"""Undoable commands over the project document (CLAUDE.md rule 8).

A command is a pure transform ``apply(doc) -> doc`` on the immutable
ProjectDoc — it never mutates, and it raises CommandError on invalid
input. The UndoStack stores (command, doc_before, doc_after) triples;
undo/redo swap document values and never re-run ``apply``. Snapshots
are cheap: the doc is small intent-only frozen data with structural
sharing.

Drag gestures do NOT create a command per mouse-move: the UI previews
(apply against the committed doc, discard) and commits exactly one
command on release — see ui/app_state.py.
"""
from __future__ import annotations

import abc
import math
import re
from dataclasses import dataclass, replace

from scoreanim.core.animation.reveal import RevealMode
from scoreanim.core.animation.style import ElementStyle
from scoreanim.core.project.document import (CondenseGroup, LayoutOverride,
                                             PartTextOverride, ProjectDoc,
                                             StaffGroup)
from scoreanim.core.project.stage_config import (OVERLAY_PREFIX,
                                                 PresentationMode,
                                                 StageTextElement, fit_texts,
                                                 is_header_text)
from scoreanim.core.score.identity import Beats, ElementId, PartId
from scoreanim.core.timing.swing import SwingRegion, validate_regions
from scoreanim.core.timing.taps import TapSession
from scoreanim.core.timing.tempo_map import TempoEvent, TempoMap

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")


class CommandError(ValueError):
    """Invalid command input for the current document."""


class Command(abc.ABC):
    @abc.abstractmethod
    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        """Pure transform; raises CommandError; never mutates ``doc``."""

    @abc.abstractmethod
    def describe(self) -> str:
        """Short lowercase phrase for Edit-menu text ("undo <this>")."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _with_timing(doc: ProjectDoc, **changes) -> ProjectDoc:
    return replace(doc, timing=replace(doc.timing, **changes))


def _validated_events(events: tuple[TempoEvent, ...]
                      ) -> tuple[TempoEvent, ...]:
    """Normalize (sort) and validate through TempoMap — the authority on
    what a legal event set is (bpm > 0, no duplicate positions)."""
    for e in events:
        if not (math.isfinite(e.position) and math.isfinite(e.bpm)):
            raise CommandError(f"tempo event {e} is not finite")
    try:
        TempoMap(list(events))
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    return tuple(sorted(events, key=lambda e: e.position))


def _validated_regions(regions: tuple[SwingRegion, ...]
                       ) -> tuple[SwingRegion, ...]:
    try:
        validate_regions(regions)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    return tuple(sorted(regions, key=lambda r: r.span[0]))


# ---------------------------------------------------------------------------
# tempo events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AddTempoEvent(Command):
    position: Beats
    bpm: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        events = doc.timing.tempo_events + (TempoEvent(self.position,
                                                       self.bpm),)
        return _with_timing(doc, tempo_events=_validated_events(events))

    def describe(self) -> str:
        return "add tempo event"


@dataclass(frozen=True)
class MoveTempoEvent(Command):
    position: Beats              # identifies the event in the current doc
    new_position: Beats
    new_bpm: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        old = doc.timing.tempo_events
        if not any(e.position == self.position for e in old):
            raise CommandError(f"no tempo event at beat {self.position}")
        events = tuple(TempoEvent(self.new_position, self.new_bpm)
                       if e.position == self.position else e for e in old)
        return _with_timing(doc, tempo_events=_validated_events(events))

    def describe(self) -> str:
        return "move tempo event"


@dataclass(frozen=True)
class RemoveTempoEvent(Command):
    position: Beats

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        old = doc.timing.tempo_events
        events = tuple(e for e in old if e.position != self.position)
        if len(events) == len(old):
            raise CommandError(f"no tempo event at beat {self.position}")
        if not events:
            raise CommandError("cannot remove the last tempo event")
        return _with_timing(doc, tempo_events=events)

    def describe(self) -> str:
        return "remove tempo event"


@dataclass(frozen=True)
class SetOffset(Command):
    seconds: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not math.isfinite(self.seconds):
            raise CommandError(f"offset {self.seconds} is not finite")
        return _with_timing(doc, offset_seconds=self.seconds)

    def describe(self) -> str:
        return "set offset"


@dataclass(frozen=True)
class ImportTempoSetup(Command):
    """Sidecar-import semantics: replaces the offset and ALL tempo events
    (what loading a .tempo file always meant). Swing and taps survive."""
    offset_seconds: float
    events: tuple[TempoEvent, ...]
    source_name: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not self.events:
            raise CommandError(f"{self.source_name}: no tempo events")
        if not math.isfinite(self.offset_seconds):
            raise CommandError("offset is not finite")
        return _with_timing(doc, offset_seconds=self.offset_seconds,
                            tempo_events=_validated_events(self.events))

    def describe(self) -> str:
        return f"import tempo ({self.source_name})"


# ---------------------------------------------------------------------------
# taps
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApplyTaps(Command):
    """Record a tap session and splice its derived events into the map:
    existing events inside [span) are replaced, everything outside is
    preserved. One undo step removes the whole derivation AND the
    session's markers."""
    session: TapSession
    events: tuple[TempoEvent, ...]
    span: tuple[Beats, Beats]            # [start, end)
    mode: str                            # "derive" | "lock"

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        start, end = self.span
        if not start < end:
            raise CommandError(f"tap span {self.span} is empty or reversed")
        if not self.events:
            raise CommandError("tap derivation produced no events")
        if not all(start <= e.position < end for e in self.events):
            raise CommandError("derived events fall outside the tap span")
        kept = tuple(e for e in doc.timing.tempo_events
                     if not start <= e.position < end)
        events = _validated_events(kept + self.events)
        sessions = doc.timing.tap_sessions
        if self.session not in sessions:
            sessions = sessions + (self.session,)
        return _with_timing(doc, tempo_events=events, tap_sessions=sessions)

    def describe(self) -> str:
        return ("lock tempo to taps" if self.mode == "lock"
                else "apply tap tempo")


@dataclass(frozen=True)
class RemoveTapSession(Command):
    """Drop a session's markers; tempo events derived from it stay."""
    index: int

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        sessions = doc.timing.tap_sessions
        if not 0 <= self.index < len(sessions):
            raise CommandError(f"no tap session #{self.index}")
        return _with_timing(doc, tap_sessions=sessions[:self.index]
                            + sessions[self.index + 1:])

    def describe(self) -> str:
        return "remove tap markers"


# ---------------------------------------------------------------------------
# swing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SetGlobalSwing(Command):
    """Phase 4 authoring surface (ruling 2026-07-11): ONE swing ratio for
    the whole piece — replaces every swing region with a single region
    covering [0, end_beat), or none at 0.5 (straight). The region model
    underneath is unchanged; per-region authoring returns later
    (BACKLOG 7)."""
    ratio: float
    end_beat: Beats              # score end — runtime data the UI supplies

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not 0.5 <= self.ratio < 1.0:
            raise CommandError(f"swing ratio {self.ratio} outside "
                               f"[0.5, 1.0)")
        if self.ratio == 0.5:
            return _with_timing(doc, swing_regions=())
        end = float(math.ceil(self.end_beat))
        if end <= 0:
            raise CommandError("no score extent to swing")
        regions = (SwingRegion((0.0, end), self.ratio),)
        return _with_timing(doc, swing_regions=_validated_regions(regions))

    def describe(self) -> str:
        return "set swing"


@dataclass(frozen=True)
class AddSwingRegion(Command):
    region: SwingRegion

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        regions = doc.timing.swing_regions + (self.region,)
        return _with_timing(doc, swing_regions=_validated_regions(regions))

    def describe(self) -> str:
        return "add swing region"


@dataclass(frozen=True)
class SetSwingRegion(Command):
    span: tuple[Beats, Beats]    # identifies the region in the current doc
    region: SwingRegion

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        old = doc.timing.swing_regions
        if not any(r.span == self.span for r in old):
            raise CommandError(f"no swing region at {self.span}")
        regions = tuple(self.region if r.span == self.span else r
                        for r in old)
        return _with_timing(doc, swing_regions=_validated_regions(regions))

    def describe(self) -> str:
        return "edit swing region"


@dataclass(frozen=True)
class RemoveSwingRegion(Command):
    span: tuple[Beats, Beats]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        old = doc.timing.swing_regions
        regions = tuple(r for r in old if r.span != self.span)
        if len(regions) == len(old):
            raise CommandError(f"no swing region at {self.span}")
        return _with_timing(doc, swing_regions=regions)

    def describe(self) -> str:
        return "remove swing region"


# ---------------------------------------------------------------------------
# style
# ---------------------------------------------------------------------------

def _merge_rule(rules: dict, key, color=..., effect=...) -> dict:
    """Field-wise update of one ElementStyle entry; empty entries are
    dropped so the doc stays sparse. ``...`` = leave the field alone."""
    current = rules.get(key, ElementStyle())
    updated = ElementStyle(
        color=current.color if color is ... else color,
        effect=current.effect if effect is ... else effect,
    )
    if updated.is_empty:
        rules.pop(key, None)
    else:
        rules[key] = updated
    return rules


@dataclass(frozen=True)
class SetPartColor(Command):
    part: PartId
    color: str | None            # "#rrggbb" | None = back to default

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if self.color is not None and not _HEX_COLOR.match(self.color):
            raise CommandError(f"bad color {self.color!r} (want #rrggbb)")
        parts = _merge_rule(dict(doc.style.parts), self.part,
                            color=self.color)
        return replace(doc, style=replace(doc.style, parts=parts))

    def describe(self) -> str:
        return "set part color"


@dataclass(frozen=True)
class SetPartEffect(Command):
    part: PartId
    effect: str | None           # preset name | None = default effect

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if self.effect is not None and not self.effect.strip():
            raise CommandError("empty effect name")
        parts = _merge_rule(dict(doc.style.parts), self.part,
                            effect=self.effect)
        return replace(doc, style=replace(doc.style, parts=parts))

    def describe(self) -> str:
        return "set part effect"


@dataclass(frozen=True)
class SetElementStyle(Command):
    """Per-element override rule — higher priority than the part rule.
    No editing UI yet in Phase 5 (needs click-to-select); the model,
    command, and serialization are the 5.3 deliverable. On a spanner
    broken across systems this targets ONE segment (ids are
    per-segment)."""
    element_id: ElementId
    style: ElementStyle | None   # None removes the override

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        elements = dict(doc.style.elements)
        if self.style is None or self.style.is_empty:
            elements.pop(self.element_id, None)
        else:
            if (self.style.color is not None
                    and not _HEX_COLOR.match(self.style.color)):
                raise CommandError(f"bad color {self.style.color!r} "
                                   f"(want #rrggbb)")
            elements[self.element_id] = self.style
        return replace(doc, style=replace(doc.style, elements=elements))

    def describe(self) -> str:
        return "set element style"


@dataclass(frozen=True)
class SetRevealMode(Command):
    mode: RevealMode

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not isinstance(self.mode, RevealMode):
            raise CommandError(f"bad reveal mode {self.mode!r}")
        return replace(doc, style=replace(doc.style, reveal_mode=self.mode))

    def describe(self) -> str:
        return "set reveal mode"


@dataclass(frozen=True)
class SetFloorOpacity(Command):
    """Ghost-score floor (Phase 7.2). 0 is a value, not an error:
    unrevealed animated ink invisible on the always-visible scaffold."""
    value: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not (isinstance(self.value, (int, float))
                and math.isfinite(self.value)
                and 0.0 <= self.value <= 1.0):
            raise CommandError(f"floor opacity {self.value!r} "
                               f"not in [0, 1]")
        return replace(doc, style=replace(doc.style,
                                          floor_opacity=float(self.value)))

    def describe(self) -> str:
        return "set floor opacity"


# ---------------------------------------------------------------------------
# stage
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SetPresentationMode(Command):
    """Paged (default) vs system-at-a-time framing (Phase 7.4). Stage
    intent only — the Layout is identical in both modes."""
    mode: PresentationMode

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not isinstance(self.mode, PresentationMode):
            raise CommandError(f"bad presentation mode {self.mode!r}")
        return replace(doc, stage=replace(doc.stage, mode=self.mode))

    def describe(self) -> str:
        return "set presentation mode"


@dataclass(frozen=True)
class SetHideEmptyStaves(Command):
    """Hide staves that are empty for a whole system (Phase 10R).
    Intent only — the hidden layout re-derives at the engraving seam,
    like staff groups; the window re-engraves on the doc diff."""
    value: bool

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not isinstance(self.value, bool):
            raise CommandError(f"bad hide_empty_staves {self.value!r}")
        return replace(doc, hide_empty_staves=self.value)

    def describe(self) -> str:
        return "hide empty staves" if self.value else "show empty staves"


@dataclass(frozen=True)
class SetHideFirstSystem(Command):
    """Also hide empty staves on the FIRST system (2026-07-24) — off by
    default, since first-system-full is the engraving convention.
    Meaningful only while hide_empty_staves is on; same re-engrave seam."""
    value: bool

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not isinstance(self.value, bool):
            raise CommandError(f"bad hide_first_system {self.value!r}")
        return replace(doc, hide_first_system=self.value)

    def describe(self) -> str:
        return ("hide empty staves on first system" if self.value
                else "show staves on first system")


_TEXT_ANCHORS = frozenset({"start", "middle", "end"})


def _validated_stage_text(text: StageTextElement) -> StageTextElement:
    if not text.content.strip():
        raise CommandError("stage text content is blank")
    if text.anchor not in _TEXT_ANCHORS:
        raise CommandError(f"bad anchor {text.anchor!r} "
                           f"(want start/middle/end)")
    if not (math.isfinite(text.x) and math.isfinite(text.y)):
        raise CommandError(f"stage text position ({text.x!r}, {text.y!r}) "
                           f"not finite")
    if not (isinstance(text.font_size, (int, float))
            and math.isfinite(text.font_size) and text.font_size > 0):
        raise CommandError(f"bad font size {text.font_size!r}")
    if text.color is not None and not _HEX_COLOR.match(text.color):
        raise CommandError(f"bad color {text.color!r} (want #rrggbb)")
    return text


@dataclass(frozen=True)
class EditStageText(Command):
    """Content/position/style of one stage text (Phase 9.1). Never
    re-engraves — stage texts are overlay by construction. `band` is
    runtime data (the SetGlobalSwing.end_beat idiom: the doc stores
    intent only, the UI supplies the derived free space above the top
    staff from page_content_top). When given, the whole header block
    re-fits into it — down-only, sibling texts may rescale/move, all
    one undo step, matching the seed's baked-fit semantics. Overlay
    texts (stage:overlay:*) sit at their engraved position and never
    participate in the refit."""
    element_id: str
    text: StageTextElement           # full replacement (same id, same page)
    band: float | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        old = next((t for t in doc.stage.texts
                    if t.element_id == self.element_id), None)
        if old is None:
            raise CommandError(f"no stage text {self.element_id!r}")
        if self.text.element_id != self.element_id:
            raise CommandError("stage text id cannot change (it is the key)")
        if self.text.page != old.page:
            raise CommandError("stage text page cannot change")
        _validated_stage_text(self.text)
        texts = tuple(self.text if t.element_id == self.element_id else t
                      for t in doc.stage.texts)
        if self.band is not None:
            if not (isinstance(self.band, (int, float))
                    and math.isfinite(self.band) and self.band > 0):
                raise CommandError(f"bad band {self.band!r}")
            header = tuple(t for t in texts if is_header_text(t))
            fitted = dict(zip((t.element_id for t in header),
                              fit_texts(header, float(self.band))))
            texts = tuple(fitted.get(t.element_id, t) for t in texts)
        return replace(doc, stage=replace(doc.stage, texts=texts))

    def describe(self) -> str:
        return "edit stage text"


@dataclass(frozen=True)
class AddTempoOverlay(Command):
    """Replace an engraved tempo mark (Phase 9.2): hide the engraved
    TEXT element — the first consumer of LayoutOverride.hidden — and
    add its replacement stage text, one intent, ONE undo step. Never
    re-engraves. The doc has no layout, so this cannot verify that
    `element_id` really is a tempo TEXT — the UI guarantees it by
    filtering RenderedElement.text_class == "tempo" (the part_order
    trust model). Editing an existing overlay is EditStageText on the
    overlay id."""
    element_id: ElementId            # the ENGRAVED element to hide
    text: StageTextElement           # id must be OVERLAY_PREFIX + element_id

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        expected = OVERLAY_PREFIX + str(self.element_id)
        if self.text.element_id != expected:
            raise CommandError(f"overlay text id {self.text.element_id!r} "
                               f"must be {expected!r}")
        if any(t.element_id == expected for t in doc.stage.texts):
            raise CommandError(f"element {self.element_id} is already "
                               f"overlaid")
        _validated_stage_text(self.text)
        overrides = dict(doc.layout_overrides)
        overrides[self.element_id] = replace(
            overrides.get(self.element_id, LayoutOverride()), hidden=True)
        return replace(doc, layout_overrides=overrides,
                       stage=replace(doc.stage,
                                     texts=doc.stage.texts + (self.text,)))

    def describe(self) -> str:
        return "replace tempo mark"


@dataclass(frozen=True)
class RemoveTempoOverlay(Command):
    """Restore the engraved original: drop the overlay text and clear
    the hidden flag — the override entry disappears entirely when it is
    back at the default (the SetElementStyle sparse-doc idiom)."""
    element_id: ElementId            # the ENGRAVED element

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        overlay_id = OVERLAY_PREFIX + str(self.element_id)
        if not any(t.element_id == overlay_id for t in doc.stage.texts):
            raise CommandError(f"element {self.element_id} is not overlaid")
        texts = tuple(t for t in doc.stage.texts
                      if t.element_id != overlay_id)
        overrides = dict(doc.layout_overrides)
        restored = replace(overrides.get(self.element_id, LayoutOverride()),
                           hidden=False)
        if restored == LayoutOverride():
            overrides.pop(self.element_id, None)
        else:
            overrides[self.element_id] = restored     # keeps its dx/dy
        return replace(doc, layout_overrides=overrides,
                       stage=replace(doc.stage, texts=texts))

    def describe(self) -> str:
        return "restore tempo mark"


# ---------------------------------------------------------------------------
# staff groups (Phase 8)
# ---------------------------------------------------------------------------

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
# undo stack
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Entry:
    command: Command
    before: ProjectDoc
    after: ProjectDoc


class UndoStack:
    """Linear undo. ``execute`` truncates the redo tail; ``mark_saved``
    pins the current position so ``is_dirty`` can drive the title-bar
    star. Undo/redo return stored document values — ``apply`` never
    re-runs."""

    _NEVER = -1                  # saved position lost to truncation

    def __init__(self) -> None:
        self._entries: list[_Entry] = []
        self._index = 0          # number of applied commands
        self._saved = 0

    def execute(self, command: Command, doc: ProjectDoc) -> ProjectDoc:
        after = command.apply(doc)
        del self._entries[self._index:]
        if self._saved > self._index:
            self._saved = self._NEVER
        self._entries.append(_Entry(command, doc, after))
        self._index += 1
        return after

    def undo(self) -> ProjectDoc:
        if not self.can_undo:
            raise CommandError("nothing to undo")
        self._index -= 1
        return self._entries[self._index].before

    def redo(self) -> ProjectDoc:
        if not self.can_redo:
            raise CommandError("nothing to redo")
        entry = self._entries[self._index]
        self._index += 1
        return entry.after

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._entries)

    def undo_text(self) -> str | None:
        return (self._entries[self._index - 1].command.describe()
                if self.can_undo else None)

    def redo_text(self) -> str | None:
        return (self._entries[self._index].command.describe()
                if self.can_redo else None)

    def mark_saved(self) -> None:
        self._saved = self._index

    @property
    def is_dirty(self) -> bool:
        return self._index != self._saved
