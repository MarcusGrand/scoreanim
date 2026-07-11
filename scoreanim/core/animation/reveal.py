"""Reveal / playhead-x unification (ARCHITECTURE §3, Phase 5.1).

Per system, the reveal edge is a function of time built from the sorted
(onset, x) pairs of the system's noteheads and slashes — onsets from the
timing model mapped to x, never derived from engraved x. The whole-system
sweep, per-spanner clip-grow, and any cursor all read this one function.

Anchor onsets are NOTATED onsets (``identity.onset``) — deliberately not
the trigger schedule's tie-gated beats. The playhead-x is a musical-time
mapping: a tie-stop head is passed at its notated beat (its ink was lit
at the chain start, which is the schedule's business, not reveal's).
Using chain-start beats would pin a later x to an earlier beat, breaking
monotonicity and prematurely growing every spanner in between. Nothing
is re-derived: ``identity.onset`` is the same column the schedule
consumed, simultaneity uses the shared ``quantize_beats``, and anchor
times resolve through the same swing-aware ``resolve_seconds`` seam as
trigger times.

Sentinels (each track spans its system's whole time slot):
- lead anchor ``(previous system's last onset, left hull edge)`` — so in
  CONTINUOUS mode the new system sweeps left-edge → first-note while the
  previous system sweeps last-note → right-edge over the same interval,
  and a break-spanning spanner grows continuously through the break.
  The first system leads from beat 0 (or one quarter before an
  immediate first onset).
- end anchor ``(next system's first onset — score end for the last —,
  right hull edge)`` — the trailing ink past the last onset (a tie
  reaching the margin) completes exactly when the next system begins.
Hull edges come from every element bbox in the system, so no drawn ink
lies outside [x_left, x_right]. Systems with no anchors (all-rest) keep
their two sentinels, so spanners crossing them still grow.
"""
from __future__ import annotations

import enum
from bisect import bisect_right
from dataclasses import dataclass
from typing import Sequence

from scoreanim.core.animation.schedule import quantize_beats
from scoreanim.core.engraving.types import Layout
from scoreanim.core.score.identity import Beats, ElementKind
from scoreanim.core.timing.swing import SwingRegion, resolve_seconds
from scoreanim.core.timing.tempo_map import TempoMap

# Kinds whose (onset, x) pairs define the reveal edge.
ANCHOR_KINDS = frozenset({ElementKind.NOTEHEAD, ElementKind.SLASH})

# Spanner kinds revealed by clip-grow at the reveal edge (Phase 5.2
# ruling: grow REPLACES the Phase 3 step-appear for SLUR/TIE and newly
# covers HAIRPIN per the 5.2 task text; the dynamic letters stay static).
# Their opacity stays 1.0 — the clip does all revealing.
REVEALED_KINDS = frozenset({ElementKind.SLUR, ElementKind.TIE,
                            ElementKind.HAIRPIN})


def is_revealed(kind: ElementKind) -> bool:
    return kind in REVEALED_KINDS


class RevealMode(enum.Enum):
    CONTINUOUS = enum.auto()     # lerp x between onset positions (sweep)
    STEPPED = enum.auto()        # step function; jumps at musical onsets


@dataclass(frozen=True)
class SystemRevealTrack:
    """Beat-domain reveal anchors for one system: strictly increasing
    beats (lead + onsets + end sentinel), monotone non-decreasing x."""
    system: int
    beats: tuple[Beats, ...]
    xs: tuple[float, ...]
    x_left: float                # reveal-0 edge (left of all ink)

    def __post_init__(self) -> None:
        if len(self.beats) != len(self.xs) or len(self.beats) < 2:
            raise ValueError("track needs matching beats/xs, at least "
                             "lead + end sentinel")
        if any(b1 <= b0 for b0, b1 in zip(self.beats, self.beats[1:])):
            raise ValueError(f"system {self.system}: anchor beats not "
                             f"strictly increasing")
        if any(x1 < x0 for x0, x1 in zip(self.xs, self.xs[1:])):
            raise ValueError(f"system {self.system}: anchor xs not "
                             f"monotone")

    def resolve(self, tempo_map: TempoMap,
                swing: Sequence[SwingRegion] = ()) -> "RevealCurve":
        return RevealCurve(
            system=self.system,
            times=tuple(resolve_seconds(self.beats, tempo_map, swing)),
            xs=self.xs, x_left=self.x_left)


@dataclass(frozen=True)
class RevealCurve:
    """A track resolved to seconds (tempo + swing applied)."""
    system: int
    times: tuple[float, ...]
    xs: tuple[float, ...]
    x_left: float


def reveal_x(curve: RevealCurve, t_seconds: float, mode: RevealMode) -> float:
    """The reveal edge of one system at time t.

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


def build_reveal_tracks(layout: Layout, score_end: Beats
                        ) -> tuple[SystemRevealTrack, ...]:
    """One track per system in the layout, in system order.

    ``score_end`` (total quarters; derivable from the score model's
    measures) closes the last system — Layout carries no durations."""
    # (onset, x) buckets and bbox hulls, per system
    anchors: dict[int, dict[int, tuple[Beats, float]]] = {}
    hull: dict[int, tuple[float, float]] = {}
    for el in layout.elements:
        if el.system is None:
            continue
        lo, hi = hull.get(el.system, (el.bbox.x, el.bbox.x2))
        hull[el.system] = (min(lo, el.bbox.x), max(hi, el.bbox.x2))
        ident = el.identity
        if ident.kind not in ANCHOR_KINDS or ident.onset is None:
            continue
        bucket = anchors.setdefault(el.system, {})
        key = quantize_beats(ident.onset)
        prev = bucket.get(key)
        x2 = el.bbox.x2
        if prev is None or x2 > prev[1]:
            bucket[key] = (ident.onset, x2)

    systems = sorted(hull)
    tracks: list[SystemRevealTrack] = []
    prev_last_onset = 0.0
    for n, sys_n in enumerate(systems):
        x_left, x_right = hull[sys_n]
        onsets = sorted(anchors.get(sys_n, {}).values())
        end_beat = score_end
        for later in systems[n + 1:]:    # first onset of the next system
            nxt = anchors.get(later, {})  # with any anchors at all
            if nxt:
                end_beat = min(nxt.values())[0]
                break

        beats: list[Beats] = []
        xs: list[float] = []
        lead = prev_last_onset
        first = onsets[0][0] if onsets else end_beat
        if lead >= first:        # degenerate input; keep strict order
            lead = first - 1.0
        beats.append(lead)
        xs.append(x_left)
        x_cummax = x_left
        for onset, x in onsets:
            x_cummax = max(x_cummax, x)
            beats.append(onset)
            xs.append(x_cummax)
        if end_beat <= beats[-1]:            # defensive: keep the sentinel
            end_beat = beats[-1] + 1.0
        beats.append(end_beat)
        xs.append(max(x_right, x_cummax))
        tracks.append(SystemRevealTrack(
            system=sys_n, beats=tuple(beats), xs=tuple(xs), x_left=x_left))
        if onsets:
            prev_last_onset = onsets[-1][0]
    return tuple(tracks)
