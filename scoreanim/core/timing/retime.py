"""Retiming a span: put a beat at a given second without moving its
neighbours.

This is what dragging a grid line onto the waveform means. To put beat
`B` at second `S` while the anchors `L` and `R` either side stay exactly
where they are: give each span a boundary event, then multiply the bpm of
every event inside `[L, B)` by `old_span / new_span`, and the same inside
`[B, R)`. Scaling by a constant divides the span's duration by that
constant and preserves any tempo shape already inside it.

`right=None` is the ripple case: only the span before `B` retimes, and
everything after `B` keeps its tempo and slides by the same amount. It is
also what dragging the last line means, since there is no anchor after
it.

Positions here are beats in the domain `TempoMap.seconds_at` consumes —
already swing-warped. The caller warps (`swing.swing_warp`); this module
never sees a swing region.

Two things that look like details and are not:

- The events are normalized with a beat-0 event first. `TempoMap` anchors
  `seconds_at(0) == 0` by extending the FIRST event's bpm backwards, so
  scaling that event would move every second before it — including the
  anchor we promised not to move. A document made in the app always has
  a beat-0 event already, so the normalization is usually a no-op; a
  `.tempo` sidecar import is where it earns its keep.
- `retime_bounds` gives the caller the reachable window, so a drag can
  clamp the cursor and `retime` never has to fail half way through a
  gesture.
"""
from __future__ import annotations

import math
from typing import Sequence

from scoreanim.core.score.identity import Beats
from scoreanim.core.timing.tempo_map import TempoEvent, TempoMap

BPM_MIN, BPM_MAX = 20.0, 400.0
MIN_SPAN_SECONDS = 1e-3          # never solve for a zero-length span

_EPS = 1e-9


def bpm_at(events: Sequence[TempoEvent], beat: Beats) -> float:
    """The bpm in force at `beat` (the first event's bpm extends back)."""
    prevailing = events[0].bpm
    for event in events:
        if event.position <= beat + _EPS:
            prevailing = event.bpm
        else:
            break
    return prevailing


def retime(events: Sequence[TempoEvent], *, beat: Beats, seconds: float,
           left: Beats, right: Beats | None) -> tuple[TempoEvent, ...]:
    """Rewrite bpms so `seconds_at(beat) == seconds`, with `seconds_at`
    unchanged at `left`, at `right`, and everywhere outside `[left,
    right)`. Raises ValueError when the target is unreachable."""
    events = _normalized(events)
    _check_anchors(beat, seconds, left, right)
    tempo_map = TempoMap(list(events))
    s_left = tempo_map.seconds_at(left)
    s_beat = tempo_map.seconds_at(beat)
    if seconds - s_left < MIN_SPAN_SECONDS:
        raise ValueError(f"target {seconds:.4f}s crowds the anchor at beat "
                         f"{left:g} ({s_left:.4f}s)")
    ratio_left = (s_beat - s_left) / (seconds - s_left)
    ratio_right = None
    if right is not None:
        s_right = tempo_map.seconds_at(right)
        if s_right - seconds < MIN_SPAN_SECONDS:
            raise ValueError(f"target {seconds:.4f}s crowds the anchor at "
                             f"beat {right:g} ({s_right:.4f}s)")
        ratio_right = (s_right - s_beat) / (s_right - seconds)

    wanted = [left, beat] + ([] if right is None else [right])
    events, inserted = _with_boundaries(events, wanted)
    events = _scaled(events, left, beat, ratio_left)
    if ratio_right is not None:
        events = _scaled(events, beat, right, ratio_right)
    return _pruned(events, inserted)


def retime_bounds(events: Sequence[TempoEvent], *, beat: Beats, left: Beats,
                  right: Beats | None) -> tuple[float, float]:
    """The window of score seconds `beat` can be moved into with every
    bpm still inside [BPM_MIN, BPM_MAX]. The view clamps the cursor with
    this, so `retime` is never asked for the impossible."""
    events = _normalized(events)
    _check_anchors(beat, None, left, right)
    tempo_map = TempoMap(list(events))
    s_left = tempo_map.seconds_at(left)
    s_beat = tempo_map.seconds_at(beat)
    slow, fast = _duration_range(events, left, beat, s_beat - s_left)
    lo, hi = s_left + fast, s_left + slow
    if right is not None:
        s_right = tempo_map.seconds_at(right)
        slow, fast = _duration_range(events, beat, right, s_right - s_beat)
        lo = max(lo, s_right - slow)
        hi = min(hi, s_right - fast)
    return lo, hi


# -- internals ---------------------------------------------------------------


def _check_anchors(beat: Beats, seconds: float | None, left: Beats,
                   right: Beats | None) -> None:
    values = [beat, left] + ([] if right is None else [right])
    if seconds is not None:
        values.append(seconds)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("retime needs finite beats and seconds")
    if beat - left < _EPS:
        raise ValueError(f"beat {beat:g} is not after its anchor {left:g}")
    if right is not None and right - beat < _EPS:
        raise ValueError(f"beat {beat:g} is not before its anchor {right:g}")


def _normalized(events: Sequence[TempoEvent]) -> tuple[TempoEvent, ...]:
    """Sorted, with a beat-0 event so no scaling can move seconds_at(0)."""
    ordered = tuple(sorted(events, key=lambda e: e.position))
    if not ordered:
        raise ValueError("retime needs at least one tempo event")
    if ordered[0].position > _EPS:
        ordered = (TempoEvent(0.0, ordered[0].bpm),) + ordered
    return ordered


def _span_bpms(events: Sequence[TempoEvent], lo: Beats,
               hi: Beats | None) -> tuple[float, ...]:
    """Every bpm in force somewhere in [lo, hi)."""
    inside = [e.bpm for e in events
              if e.position > lo + _EPS
              and (hi is None or e.position < hi - _EPS)]
    return (bpm_at(events, lo),) + tuple(inside)


def _duration_range(events: Sequence[TempoEvent], lo: Beats, hi: Beats,
                    duration: float) -> tuple[float, float]:
    """(slowest, fastest) seconds this span can be stretched to."""
    bpms = _span_bpms(events, lo, hi)
    ratio_max = min(BPM_MAX / bpm for bpm in bpms)      # fastest
    ratio_min = max(BPM_MIN / bpm for bpm in bpms)      # slowest
    return duration / ratio_min, max(duration / ratio_max, MIN_SPAN_SECONDS)


def _with_boundaries(events: tuple[TempoEvent, ...],
                     positions: Sequence[Beats]
                     ) -> tuple[tuple[TempoEvent, ...], tuple[Beats, ...]]:
    """An event at each position, neutral where one has to be added. The
    _EPS match matters: without it a boundary a hair from an existing
    event makes a zero-length span with an absurd bpm."""
    out = list(events)
    inserted: list[Beats] = []
    for position in positions:
        if any(abs(e.position - position) <= _EPS for e in out):
            continue
        out.append(TempoEvent(position, bpm_at(out, position)))
        out.sort(key=lambda e: e.position)
        inserted.append(position)
    return tuple(out), tuple(inserted)


def _scaled(events: tuple[TempoEvent, ...], lo: Beats, hi: Beats,
            ratio: float) -> tuple[TempoEvent, ...]:
    """Multiply the bpm of every event governing [lo, hi) by `ratio`."""
    out = []
    for event in events:
        if lo - _EPS <= event.position < hi - _EPS:
            bpm = event.bpm * ratio
            if not BPM_MIN - _EPS <= bpm <= BPM_MAX + _EPS:
                raise ValueError(f"retiming beat {event.position:g} would "
                                 f"need {bpm:.1f} bpm")
            event = TempoEvent(event.position, bpm)
        out.append(event)
    return tuple(out)


def _pruned(events: tuple[TempoEvent, ...],
            inserted: Sequence[Beats]) -> tuple[TempoEvent, ...]:
    """Drop the boundary events this call added that turned out to say
    nothing. Only those: an equal-bpm event the user placed on purpose is
    an anchor of theirs, not clutter."""
    out = list(events)
    for position in sorted(inserted, reverse=True):
        if len(out) == 1:
            break
        i = next((k for k, e in enumerate(out)
                  if abs(e.position - position) <= _EPS), None)
        if i is None:
            continue
        neighbour = out[i - 1] if i > 0 else out[i + 1]
        if math.isclose(out[i].bpm, neighbour.bpm, rel_tol=1e-12):
            del out[i]
    return tuple(out)
