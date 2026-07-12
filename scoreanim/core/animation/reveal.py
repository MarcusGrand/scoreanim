"""Reveal / playhead-x: per-(system, part) stepped tracks (Phase 5
re-plan, rulings A/B 2026-07-12 — supersedes the 5.1 shared-edge model
and ARCHITECTURE §3's original single per-system function).

Per system AND part, the reveal edge is a function of time built from
the part's events — anchors keyed by the trigger schedule's TIE-GATED
beats (``schedule.beats_by_element``), not notated onsets. A tied chain
is therefore ONE event (ruling A): its stop heads and their attachments
carry the chain-start trigger, so the whole group collapses into a
single anchor at (chain start, x2 of the chain's furthest ink); nothing
about the group advances until the chain completes, and the edge's next
advance is the part's next event. The chain's tie curves and broken
``:seg`` segments are folded into the chain-start bucket of the system
they sit in, so a chain broken across systems stands revealed from
chain start on both sides — consistent with tied ink lighting at chain
start (Phase 3).

Edges are per PART so one part's tied group holds only that part's
spanners; another part keeps stepping with its own events. Known limit
(accepted): granularity is per part, not per voice — a moving second
voice under a held tie sits inside the revealed region early (voice
labels relabel per measure, so voice-level keying is unreliable).

Rests and whole-bar rests are events and contribute anchors (ruling B);
dynamics animate via opacity at their attach trigger but do NOT anchor
(attachments, not events).

Sentinels: lead ``(part's previous-system last anchor beat, system left
hull)``; end ``(part's next-system first anchor beat — score end for
the last —, system right hull)``. The hull is the SYSTEM's (all parts),
so every part's edge completes at the margin. Anchor times resolve
through the same swing-aware ``resolve_seconds`` seam as triggers.

CONTINUOUS mode currently lerps over these same anchors; its real
design (a single smooth shared wavefront revealing all ink) is deferred
— BACKLOG 8.
"""
from __future__ import annotations

import enum
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

from scoreanim.core.animation.schedule import (TriggerSchedule,
                                               quantize_beats)
from scoreanim.core.engraving.types import Layout
from scoreanim.core.score.identity import (Beats, ElementKind, PartId)
from scoreanim.core.timing.swing import SwingRegion, resolve_seconds
from scoreanim.core.timing.tempo_map import TempoMap

# Kinds whose (trigger, x) pairs define the reveal edge: struck or
# sounding EVENTS. Rests joined per ruling B (2026-07-12); dynamics
# deliberately absent (attachments).
ANCHOR_KINDS = frozenset({ElementKind.NOTEHEAD, ElementKind.SLASH,
                          ElementKind.REST, ElementKind.MREST})

# Spanner kinds revealed by clip-grow at the reveal edge (Phase 5.2
# ruling: grow REPLACES the Phase 3 step-appear for SLUR/TIE and newly
# covers HAIRPIN per the 5.2 task text; the dynamic letters animate via
# opacity instead — ruling B). Spanner opacity stays 1.0 — the clip
# does all revealing.
REVEALED_KINDS = frozenset({ElementKind.SLUR, ElementKind.TIE,
                            ElementKind.HAIRPIN})


def is_revealed(kind: ElementKind) -> bool:
    return kind in REVEALED_KINDS


class RevealMode(enum.Enum):
    CONTINUOUS = enum.auto()     # lerp x between anchors (pending BACKLOG 8)
    STEPPED = enum.auto()        # step function; jumps at part events


@dataclass(frozen=True)
class SystemRevealTrack:
    """Beat-domain reveal anchors for one (system, part): strictly
    increasing beats (lead + events + end sentinel), monotone
    non-decreasing x."""
    system: int
    part: PartId | None
    beats: tuple[Beats, ...]
    xs: tuple[float, ...]
    x_left: float                # reveal-0 edge (left of all ink)

    def __post_init__(self) -> None:
        if len(self.beats) != len(self.xs) or len(self.beats) < 2:
            raise ValueError("track needs matching beats/xs, at least "
                             "lead + end sentinel")
        if any(b1 <= b0 for b0, b1 in zip(self.beats, self.beats[1:])):
            raise ValueError(f"system {self.system} part {self.part}: "
                             f"anchor beats not strictly increasing")
        if any(x1 < x0 for x0, x1 in zip(self.xs, self.xs[1:])):
            raise ValueError(f"system {self.system} part {self.part}: "
                             f"anchor xs not monotone")

    def resolve(self, tempo_map: TempoMap,
                swing: Sequence[SwingRegion] = ()) -> "RevealCurve":
        return RevealCurve(
            system=self.system, part=self.part,
            times=tuple(resolve_seconds(self.beats, tempo_map, swing)),
            xs=self.xs, x_left=self.x_left)


@dataclass(frozen=True)
class RevealCurve:
    """A track resolved to seconds (tempo + swing applied)."""
    system: int
    part: PartId | None
    times: tuple[float, ...]
    xs: tuple[float, ...]
    x_left: float


def reveal_x(curve: RevealCurve, t_seconds: float, mode: RevealMode) -> float:
    """The reveal edge of one (system, part) at time t.

    STEPPED: x of the latest anchor ≤ t (left hull edge before the
    first). CONTINUOUS: piecewise-linear between anchors. Past the end
    sentinel both modes hold the right hull edge (fully revealed)."""
    i = bisect_right(curve.times, t_seconds) - 1
    if i < 0:
        return curve.x_left
    if mode is RevealMode.STEPPED or i == len(curve.times) - 1:
        return curve.xs[i]
    t0, t1 = curve.times[i], curve.times[i + 1]
    if t1 <= t0:                 # degenerate segment; hold the later value
        return curve.xs[i + 1]
    f = (t_seconds - t0) / (t1 - t0)
    return curve.xs[i] + f * (curve.xs[i + 1] - curve.xs[i])


def build_reveal_tracks(layout: Layout, schedule: TriggerSchedule,
                        score_end: Beats) -> tuple[SystemRevealTrack, ...]:
    """One track per (system, part), system-major order.

    Anchors come from ``schedule.beats_by_element`` (tie-gated), so a
    tied chain is one event at its chain start. ``score_end`` (total
    quarters; from the score model's measures) closes each part's last
    system — Layout carries no durations."""
    triggers: Mapping = schedule.beats_by_element

    # Chain-start lookup for tie ink: notehead groups keyed
    # (part, staff, voice, quantized notated onset) → min member trigger
    # (an all-tied group's members all carry the chain start; min is the
    # conservative pick for mixed groups — the tie belongs to the tied
    # note).
    group_start: dict[tuple, Beats] = {}
    for el in layout.elements:
        ident = el.identity
        if ident.kind is not ElementKind.NOTEHEAD or ident.onset is None:
            continue
        trigger = triggers.get(ident.element_id)
        if trigger is None:
            continue
        key = (ident.part, ident.staff, ident.voice,
               quantize_beats(ident.onset))
        prev = group_start.get(key)
        group_start[key] = trigger if prev is None else min(prev, trigger)

    # (system, part) → {quantized trigger → (beats, max x2)}, plus the
    # shared per-system hull
    anchors: dict[tuple[int, PartId | None],
                  dict[int, tuple[Beats, float]]] = defaultdict(dict)
    hull: dict[int, tuple[float, float]] = {}
    for el in layout.elements:
        if el.system is None:
            continue
        lo, hi = hull.get(el.system, (el.bbox.x, el.bbox.x2))
        hull[el.system] = (min(lo, el.bbox.x), max(hi, el.bbox.x2))
        ident = el.identity
        if ident.part is None or ident.onset is None:
            continue
        if ident.kind in ANCHOR_KINDS:
            beat = triggers.get(ident.element_id, ident.onset)
        elif ident.kind is ElementKind.TIE:
            # fold the chain's tie ink (incl. broken :seg segments,
            # which inherit the source identity) into its chain-start
            # bucket in the system THEY sit in
            key = (ident.part, ident.staff, ident.voice,
                   quantize_beats(ident.onset))
            beat = group_start.get(key, ident.onset)
        else:
            continue
        bucket = anchors[(el.system, ident.part)]
        qb = quantize_beats(beat)
        prev = bucket.get(qb)
        x2 = el.bbox.x2
        if prev is None:
            bucket[qb] = (beat, x2)
        elif x2 > prev[1]:
            bucket[qb] = (prev[0], x2)

    # assemble tracks: per part, systems in order, interlocking sentinels
    parts = sorted({p for (_, p) in anchors},
                   key=lambda p: str(p))
    systems = sorted(hull)
    tracks: list[SystemRevealTrack] = []
    for part in parts:
        prev_last = 0.0
        part_systems = [s for s in systems if (s, part) in anchors]
        for n, sys_n in enumerate(systems):
            if (sys_n, part) not in anchors:
                continue
            x_left, x_right = hull[sys_n]
            onsets = sorted(anchors[(sys_n, part)].values())
            end_beat = score_end
            for later in part_systems:
                if later > sys_n:
                    end_beat = min(anchors[(later, part)].values())[0]
                    break

            beats: list[Beats] = []
            xs: list[float] = []
            lead = prev_last
            first = onsets[0][0]
            if lead >= first:    # degenerate input; keep strict order
                lead = first - 1.0
            beats.append(lead)
            xs.append(x_left)
            x_cummax = x_left
            for onset, x in onsets:
                x_cummax = max(x_cummax, x)
                beats.append(onset)
                xs.append(x_cummax)
            if end_beat <= beats[-1]:        # defensive: keep the sentinel
                end_beat = beats[-1] + 1.0
            beats.append(end_beat)
            xs.append(max(x_right, x_cummax))
            tracks.append(SystemRevealTrack(
                system=sys_n, part=part, beats=tuple(beats),
                xs=tuple(xs), x_left=x_left))
            prev_last = onsets[-1][0]
    tracks.sort(key=lambda t: (t.system, str(t.part)))
    return tuple(tracks)
