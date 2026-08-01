"""How long each element's animation actually runs (M4.6).

An effect is authored with one duration, but an element may stretch it
to its own note value (`Effect.settle_to_note_value` — F7): a whole note
settles over its whole bar, a sixteenth over a sixteenth. The stretch is
a TIMESCALE, one number per component, and the applier hands it to the
kernel rather than rewriting the envelope.

This module works that out. It is pure — it takes element ids, not Qt
items — so the applier's timing arithmetic can be read and tested
without a scene.

Three things come out of one pass (`WindowPlan`):

- `timescales_per_trigger` — one number per component of every item, in
  the applier's own [trigger][item][component] shape.
- `durations` — per trigger, the longest a component of any of its items
  stays in transition. The applier re-evaluates a trigger while t sits
  inside this window.
- `lead` — the F3 forward bound: how far ahead of a trigger a negatively
  shifted component is already live.

Engraved ends resolve through the ONE swing-aware seam
(`core/timing/resolve_seconds`) in a single batched call, so a tempo or
swing edit re-times every stretch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from scoreanim.core.animation.effect import Effect
from scoreanim.core.score.identity import Beats, ElementId
from scoreanim.core.timing import SwingRegion, TempoMap, resolve_seconds


@dataclass(frozen=True)
class WindowPlan:
    """What the applier holds: timescales in its own nested shape, the
    per-trigger window, the largest window, and the forward lead."""
    timescales_per_trigger: tuple[tuple[tuple[float, ...], ...], ...]
    durations: tuple[float, ...]
    d_max: float
    lead: float


def derive_windows(trigger_beats: Sequence[Beats],
                   trigger_seconds: Sequence[float],
                   element_ids_per_trigger: Sequence[
                       Sequence[ElementId | None]],
                   effects_per_trigger: Sequence[
                       Sequence[Sequence[Effect]]],
                   duration_by_element: Mapping[ElementId, Beats],
                   tempo_map: TempoMap | None,
                   swing: Sequence[SwingRegion] = ()) -> WindowPlan:
    """Per-component timescales and per-trigger effective windows.

    A note-value component's timescale is its element's engraved duration
    in seconds over the effect's authored duration (F7 — guarded dur > 0
    on both sides, absent entry → 1.0). Every one of these is per
    COMPONENT: an element animating with two effects at once may stretch
    one of them to its note value and run the other at its authored
    speed.

    A trigger's window is max(shift + duration × timescale) over every
    component of every item. Before timing exists (construction) there is
    no tempo map, so stretches park at 1.0 — the applier recomputes as
    soon as `set_timing` runs.
    """
    stretch: dict[tuple[int, int, int], float] = {}
    if tempo_map is not None and duration_by_element:
        refs: list[tuple[int, int, int]] = []
        end_beats: list[float] = []
        for i, beats in enumerate(trigger_beats):
            for j, (eid, effects) in enumerate(
                    zip(element_ids_per_trigger[i], effects_per_trigger[i])):
                for k, effect in enumerate(effects):
                    if (not effect.settle_to_note_value
                            or effect.duration <= 0.0
                            or eid is None):
                        continue
                    dur_beats = duration_by_element.get(eid, 0.0)
                    if dur_beats > 0.0:
                        refs.append((i, j, k))
                        end_beats.append(beats + dur_beats)
        if refs:
            ends_s = resolve_seconds(end_beats, tempo_map, swing)
            for (i, j, k), end_s in zip(refs, ends_s):
                dur_s = end_s - trigger_seconds[i]
                if dur_s > 0.0:
                    stretch[(i, j, k)] = dur_s

    timescales: list[tuple[tuple[float, ...], ...]] = []
    windows: list[float] = []
    lead = 0.0
    for i in range(len(trigger_beats)):
        row: list[tuple[float, ...]] = []
        window = 0.0
        for j, effects in enumerate(effects_per_trigger[i]):
            scales: list[float] = []
            for k, effect in enumerate(effects):
                dur_s = stretch.get((i, j, k))
                ts = dur_s / effect.duration if dur_s is not None else 1.0
                scales.append(ts)
                window = max(window,
                             effect.trigger_shift + effect.duration * ts)
                lead = max(lead, -effect.trigger_shift)
            row.append(tuple(scales))
        timescales.append(tuple(row))
        windows.append(window)
    return WindowPlan(timescales_per_trigger=tuple(timescales),
                      durations=tuple(windows),
                      d_max=max(windows, default=0.0),
                      lead=max(0.0, lead))


def audio_windows(trigger_beats: Sequence[Beats],
                  trigger_seconds: Sequence[float],
                  element_ids_per_trigger: Sequence[
                      Sequence[ElementId | None]],
                  duration_by_element: Mapping[ElementId, Beats],
                  tempo_map: TempoMap | None,
                  swing: Sequence[SwingRegion] = (),
                  offset_seconds: float = 0.0
                  ) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Which stretch of the recording each element covers: its onset,
    out to the end of its notated duration, in the same nested shape as
    the ids given. Used by the volume response, which averages the
    loudness over each one (core/animation/intensity.py).

    An element the duration map omits — a dynamic, a text, a rest —
    gets a zero-length window, which the reading takes as "use the
    attack instead".

    `offset_seconds` is the audio time of score beat 0, added to both
    ends: the caller works in score seconds and the peak cache is
    indexed from the start of the sound file. Engraved ends resolve
    through the ONE swing-aware seam in a single batched call.
    """
    refs: list[tuple[int, int]] = []
    end_beats: list[float] = []
    if tempo_map is not None and duration_by_element:
        for i, beats in enumerate(trigger_beats):
            for j, eid in enumerate(element_ids_per_trigger[i]):
                dur = duration_by_element.get(eid, 0.0) \
                    if eid is not None else 0.0
                if dur > 0.0:
                    refs.append((i, j))
                    end_beats.append(beats + dur)
    ends_s = resolve_seconds(end_beats, tempo_map, swing) \
        if refs and tempo_map is not None else []
    end_by_ref = dict(zip(refs, ends_s))
    return tuple(
        tuple((start + offset_seconds,
               max(end_by_ref.get((i, j), start), start) + offset_seconds)
              for j in range(len(element_ids_per_trigger[i])))
        for i, start in enumerate(trigger_seconds))
