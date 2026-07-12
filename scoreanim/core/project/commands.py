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
from scoreanim.core.project.document import ProjectDoc
from scoreanim.core.project.stage_config import PresentationMode
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
