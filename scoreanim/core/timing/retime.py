"""Retiming a span: put a beat at a given second without moving the
anchors either side.

This is what dragging a grid line onto the waveform means, and there are
two rules for it. Both hold `left` and `right` still and touch nothing
outside `[left, right)`; they differ in what happens to the tempo INSIDE.

- `flatten_span` — the default. The span comes out evenly spaced: one
  constant bpm from `left` to `beat`, and another from `beat` to `right`.
  Whatever tempo detail was inside is gone, which is the point — "these
  bars, evenly, between the two things I have pinned".
- `scale_span` — keep the shape. Multiply the bpm of every event inside
  each span by `old_span / new_span`, which divides the span's duration
  by that constant and leaves the tempo's shape intact. This is the one
  to use after tapping a rubato passage, where flattening would throw the
  taps away.

`right=None` means there is no anchor after the beat: only the span
before it retimes, and everything after keeps its tempo and slides by the
same amount.

The anchors come from the user's locks — `lock_anchors` picks the nearest
one either side, with the score start standing in when nothing is locked
before.

Positions here are beats in the domain `TempoMap.seconds_at` consumes —
already swing-warped. The caller warps (`swing.swing_warp`); this module
never sees a swing region.

Two things that look like details and are not:

- The events are normalized with a beat-0 event first. `TempoMap` anchors
  `seconds_at(0) == 0` by extending the FIRST event's bpm backwards, so
  rewriting that event would move every second before it — including the
  anchor we promised not to move. A document made in the app always has
  a beat-0 event already, so the normalization is usually a no-op; a
  `.tempo` sidecar import is where it earns its keep.
- `span_bounds` gives the caller the reachable window, so a drag can
  clamp the cursor and the retime never has to fail half way through a
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


def lock_anchors(locked: Sequence[Beats],
                 beat: Beats) -> tuple[Beats, Beats | None]:
    """The nearest locked beat either side of `beat`.

    `left` is never None: with nothing locked before it, the score start
    stands in, which is what "even out everything before this line"
    means when the user has pinned nothing yet. `right` is None when
    nothing is locked after — then the tail simply slides.
    """
    left = max((b for b in locked if b < beat - _EPS), default=0.0)
    right = min((b for b in locked if b > beat + _EPS), default=None)
    return left, right


def flatten_span(events: Sequence[TempoEvent], *, beat: Beats,
                 seconds: float, left: Beats,
                 right: Beats | None) -> tuple[TempoEvent, ...]:
    """Put `beat` at `seconds` and space each span evenly: one constant
    bpm from `left` to `beat`, another from `beat` to `right`. Events
    inside are dropped — that is the rule, not a side effect. Anchors and
    everything outside `[left, right)` hold still."""
    events = _normalized(events)
    _check_anchors(beat, seconds, left, right)
    tempo_map = TempoMap(list(events))
    s_left = tempo_map.seconds_at(left)
    _check_room(seconds - s_left, seconds, left, s_left)

    kept = [e for e in events if e.position < left - _EPS]
    kept.append(TempoEvent(left, _uniform_bpm(beat - left, seconds - s_left)))
    if right is None:
        # the tail keeps its tempo and slides: an event at `beat` carrying
        # what was in force there stops the flattened span bleeding past it
        kept.append(TempoEvent(beat, bpm_at(events, beat)))
        kept.extend(e for e in events if e.position > beat + _EPS)
    else:
        s_right = tempo_map.seconds_at(right)
        _check_room(s_right - seconds, seconds, right, s_right)
        kept.append(TempoEvent(beat, _uniform_bpm(right - beat,
                                                  s_right - seconds)))
        kept.append(TempoEvent(right, bpm_at(events, right)))
        kept.extend(e for e in events if e.position > right + _EPS)
    return tuple(sorted(kept, key=lambda e: e.position))


def scale_span(events: Sequence[TempoEvent], *, beat: Beats, seconds: float,
               left: Beats, right: Beats | None) -> tuple[TempoEvent, ...]:
    """Put `beat` at `seconds` by scaling every bpm inside each span, so
    the tempo's shape survives. `seconds_at` is unchanged at `left`, at
    `right`, and everywhere outside `[left, right)`. Raises ValueError
    when the target is unreachable."""
    events = _normalized(events)
    _check_anchors(beat, seconds, left, right)
    tempo_map = TempoMap(list(events))
    s_left = tempo_map.seconds_at(left)
    s_beat = tempo_map.seconds_at(beat)
    _check_room(seconds - s_left, seconds, left, s_left)
    ratio_left = (s_beat - s_left) / (seconds - s_left)
    ratio_right = None
    if right is not None:
        s_right = tempo_map.seconds_at(right)
        _check_room(s_right - seconds, seconds, right, s_right)
        ratio_right = (s_right - s_beat) / (s_right - seconds)

    wanted = [left, beat] + ([] if right is None else [right])
    events, inserted = _with_boundaries(events, wanted)
    events = _scaled(events, left, beat, ratio_left)
    if ratio_right is not None:
        events = _scaled(events, beat, right, ratio_right)
    return _pruned(events, inserted)


def span_bounds(events: Sequence[TempoEvent], *, beat: Beats, left: Beats,
                right: Beats | None, flatten: bool) -> tuple[float, float]:
    """The window of score seconds `beat` can be moved into with every
    bpm still inside [BPM_MIN, BPM_MAX]. The view clamps the cursor with
    this, so neither retime is ever asked for the impossible.

    Flattening replaces the span's bpms with one value, so its window
    depends only on the span's LENGTH IN BEATS; scaling keeps them, so
    its window is bounded by the most extreme bpm already inside."""
    events = _normalized(events)
    _check_anchors(beat, None, left, right)
    tempo_map = TempoMap(list(events))
    s_left = tempo_map.seconds_at(left)
    s_beat = tempo_map.seconds_at(beat)
    slow, fast = _duration_range(events, left, beat, s_beat - s_left, flatten)
    lo, hi = s_left + fast, s_left + slow
    if right is not None:
        s_right = tempo_map.seconds_at(right)
        slow, fast = _duration_range(events, beat, right, s_right - s_beat,
                                     flatten)
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


def _check_room(span: float, seconds: float, anchor: Beats,
                s_anchor: float) -> None:
    if span < MIN_SPAN_SECONDS:
        raise ValueError(f"target {seconds:.4f}s crowds the anchor at beat "
                         f"{anchor:g} ({s_anchor:.4f}s)")


def _uniform_bpm(beats: Beats, seconds: float) -> float:
    """The one bpm that spaces `beats` evenly over `seconds`."""
    bpm = 60.0 * beats / seconds
    if not BPM_MIN - _EPS <= bpm <= BPM_MAX + _EPS:
        raise ValueError(f"spacing {beats:g} beats over {seconds:.3f}s would "
                         f"need {bpm:.1f} bpm")
    return bpm


def _duration_range(events: Sequence[TempoEvent], lo: Beats, hi: Beats,
                    duration: float, flatten: bool) -> tuple[float, float]:
    """(slowest, fastest) seconds this span can be stretched to."""
    if flatten:                  # one bpm: only the span's beats matter
        return (60.0 * (hi - lo) / BPM_MIN,
                max(60.0 * (hi - lo) / BPM_MAX, MIN_SPAN_SECONDS))
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
