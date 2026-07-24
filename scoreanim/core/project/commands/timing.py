"""Timing commands: tempo events, sidecar import, taps, swing."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from scoreanim.core.project.commands.base import Command, CommandError
from scoreanim.core.project.document import ProjectDoc
from scoreanim.core.score.identity import Beats
from scoreanim.core.timing.swing import SwingRegion, validate_regions
from scoreanim.core.timing.taps import TapSession
from scoreanim.core.timing.tempo_map import TempoEvent, TempoMap


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
