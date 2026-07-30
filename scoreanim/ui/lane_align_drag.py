"""The drag half of ticks mode: what happens between press and release.

Split out of `ui/lane_ticks.py`, which keeps the grid, the painting and
the hit-testing. This module owns one gesture: the pre-drag snapshot, the
window the cursor is clamped into, the command previewed on every move,
and the readout.

The anchors are the user's locks, and `AlignBeat` reads them off the
document itself — so this only has to ask `lock_anchors` the same
question for the clamp, and the two can never disagree.
"""
from __future__ import annotations

from dataclasses import dataclass

from scoreanim.core.project import AlignBeat, Command, SetOffset
from scoreanim.core.score.identity import Beats
from scoreanim.core.timing import (GridUnit, TempoMap, lock_anchors,
                                   span_bounds, swing_warp)
from scoreanim.ui.readouts import format_time

_OFFSET_MIN, _OFFSET_MAX = -60.0, 3600.0     # the Offset field's own range
_EDGE = 1e-4                                 # keep off the exact bound


@dataclass
class AlignDrag:
    """One drag in flight."""
    beat: Beats                              # musical beat being dragged
    left: Beats | None                       # anchor before; None = first line
    right: Beats | None                      # anchor after, if any
    tempo_map: TempoMap                      # pre-drag: stable geometry
    unit: GridUnit                           # frozen: the grid must not
                                             # change resolution mid-drag
    flat: tuple[float, float] | None         # reachable audio seconds, per
    shaped: tuple[float, float] | None       # drag rule
    label: str
    last_cmd: Command | None = None


def begin(state, lane, beat: Beats, label: str,
          unit: GridUnit) -> AlignDrag | None:
    """Snapshot a drag, or None with a status message when the line has
    nowhere to go."""
    left, right = lock_anchors(state.doc.timing.locked_beats, beat)
    snapshot = dict(beat=beat, tempo_map=lane.tempo_map, unit=unit,
                    label=label)
    if beat - left < 1e-9:
        # nothing to span: true only at the score start, where the drag
        # means "slide the whole score under the recording" instead
        return AlignDrag(left=None, right=None, flat=None, shaped=None,
                         **snapshot)
    flat = _bounds(state, beat, left, right, flatten=True)
    shaped = _bounds(state, beat, left, right, flatten=False)
    if flat is None and shaped is None:
        state.status.emit(f"{label} has no room to move between its anchors")
        return None
    return AlignDrag(left=left, right=right, flat=flat, shaped=shaped,
                     **snapshot)


def move(state, drag: AlignDrag, seconds: float, alt: bool) -> None:
    """Preview the gesture at the cursor's second. `alt` flips whichever
    drag rule the strip has set, for this drag only."""
    if drag.left is None:
        _preview_offset(state, drag, seconds)
        return
    flatten = state.grid.flatten ^ alt
    bounds = drag.flat if flatten else drag.shaped
    if bounds is None:                       # that rule has no room here
        flatten = not flatten
        bounds = drag.flat if flatten else drag.shaped
    seconds = min(max(seconds, bounds[0] + _EDGE), bounds[1] - _EDGE)
    drag.last_cmd = AlignBeat(drag.beat, seconds, flatten)
    state.preview(drag.last_cmd)
    state.status.emit(
        f"{drag.label} → {format_time(seconds)} · "
        f"{_span_bpm(state, drag, seconds):.1f} bpm"
        f"{'' if flatten else ' · keeping the tempo shape'}")


def _preview_offset(state, drag: AlignDrag, seconds: float) -> None:
    """The first line: slide the whole score under the recording."""
    warped = swing_warp(drag.beat, state.doc.timing.swing_regions)
    offset = min(max(seconds - drag.tempo_map.seconds_at(warped),
                     _OFFSET_MIN), _OFFSET_MAX)
    drag.last_cmd = SetOffset(offset)
    state.preview(drag.last_cmd)
    state.status.emit(f"{drag.label} → offset {offset:+.2f} s")


def _span_bpm(state, drag: AlignDrag, seconds: float) -> float:
    """The tempo the span before the line is being stretched to. Exact by
    construction when flattening — it IS the one bpm being written."""
    regions = state.doc.timing.swing_regions
    start = state.doc.timing.offset_seconds \
        + drag.tempo_map.seconds_at(swing_warp(drag.left, regions))
    span = seconds - start
    return 60.0 * (drag.beat - drag.left) / span if span > 0.0 else 0.0


def _bounds(state, beat: Beats, left: Beats, right: Beats | None,
            *, flatten: bool) -> tuple[float, float] | None:
    doc = state.doc
    regions = doc.timing.swing_regions
    try:
        lo, hi = span_bounds(
            doc.timing.tempo_events,
            beat=swing_warp(beat, regions), left=swing_warp(left, regions),
            right=None if right is None else swing_warp(right, regions),
            flatten=flatten)
    except ValueError:
        return None
    offset = doc.timing.offset_seconds
    return (lo + offset, hi + offset) if hi - lo > 2e-3 else None
