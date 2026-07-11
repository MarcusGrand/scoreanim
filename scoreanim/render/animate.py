"""Schedule-driven animation applied to ScoreScenes items.

The cursor is a cache, never state: ``apply_at(t)`` leaves the scene in
the same state whether t was reached by ticking forward, scrubbing
backward, or a fresh ``refresh(t)`` — element state is a pure function
of t (CLAUDE.md rule 2). With the Phase 3 step effect an element's
opacity changes only when t crosses its trigger, so applying just the
triggers between the previous and the new cursor position is exactly
equivalent to a full re-evaluation. (Timed envelopes in later phases
widen this to a transition window around the playhead; the diff-apply
structure stays.)

Opacity is set on the ElementItem parent, which composites over its
children — correct per element. Separate elements whose ink overlaps
(an accidental grazing a notehead) double-darken at floor opacity;
accepted for v1 (flagged in the Phase 3 plan; the alternative is
color-lightening).
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from typing import Mapping, Sequence

from scoreanim.core.animation import (OPACITY, REVEALED_KINDS, Effect,
                                      RevealCurve, RevealMode,
                                      SystemRevealTrack, TriggerSchedule,
                                      element_state, reveal_x)
from scoreanim.core.score.identity import ElementId
from scoreanim.core.timing import SwingRegion, TempoMap, resolve_seconds
from scoreanim.render.items import ElementItem

_BEFORE_EVERYTHING = float("-inf")


class AnimationApplier:
    def __init__(self, items: Mapping[ElementId, ElementItem],
                 schedule: TriggerSchedule, tempo_map: TempoMap,
                 effect: Effect,
                 reveal_tracks: Sequence[SystemRevealTrack] = (),
                 reveal_mode: RevealMode = RevealMode.STEPPED) -> None:
        self._effect = effect
        self._schedule = schedule
        self._items_per_trigger: tuple[tuple[ElementItem, ...], ...] = tuple(
            tuple(items[eid] for eid in trig.element_ids if eid in items)
            for trig in schedule.triggers)
        self._pages = tuple(trig.page for trig in schedule.triggers)
        self._trigger_seconds: list[float] = []
        self._cursor = 0
        self._t = _BEFORE_EVERYTHING

        # Spanners reveal by clip-grow at their system's reveal edge —
        # no triggers involved (REVEALED_KINDS left the schedule).
        self._reveal_tracks = tuple(reveal_tracks)
        self._reveal_mode = reveal_mode
        by_system: dict[int, list[ElementItem]] = defaultdict(list)
        for item in items.values():
            if (item.identity is not None and item.system is not None
                    and item.identity.kind in REVEALED_KINDS):
                by_system[item.system].append(item)
        self._revealed_by_system: dict[int, tuple[ElementItem, ...]] = {
            s: tuple(v) for s, v in by_system.items()}
        self._curves: tuple[RevealCurve, ...] = ()
        self._last_edges: dict[int, float] = {}   # system → applied edge

        self.set_timing(tempo_map)       # also refreshes: floor everywhere

    def set_timing(self, tempo_map: TempoMap,
                   swing: Sequence[SwingRegion] = ()) -> None:
        """Beats → seconds for every trigger and reveal anchor: swing warp
        upstream of the tempo map (core/timing/swing.py). Both stages are
        strictly monotone, so the sorted-trigger bisect logic is
        untouched."""
        self._trigger_seconds = resolve_seconds(
            [trig.beats for trig in self._schedule.triggers],
            tempo_map, swing)
        self._curves = tuple(track.resolve(tempo_map, swing)
                             for track in self._reveal_tracks)
        self.refresh(self._t)

    def set_reveal_mode(self, mode: RevealMode) -> None:
        if mode is self._reveal_mode:
            return
        self._reveal_mode = mode
        self._last_edges.clear()
        self._apply_reveal(self._t)

    def apply_at(self, t_score_seconds: float) -> int:
        """Diff-apply from the last applied time; returns items touched.
        Triggers are stepped only when crossed; reveal edges are
        re-evaluated every call but fan out to items only when a
        system's edge actually moved (STEPPED edges hold between
        onsets, so idle cost stays flat)."""
        idx = bisect_right(self._trigger_seconds, t_score_seconds)
        changed = 0
        for i in range(min(self._cursor, idx), max(self._cursor, idx)):
            value = element_state(self._trigger_seconds[i], self._effect,
                                  t_score_seconds)[OPACITY]
            for item in self._items_per_trigger[i]:
                item.setOpacity(value)
                changed += 1
        self._cursor = idx
        self._t = t_score_seconds
        changed += self._apply_reveal(t_score_seconds)
        return changed

    def refresh(self, t_score_seconds: float) -> None:
        """Full apply — after seeks and tempo reloads."""
        for i, trigger_s in enumerate(self._trigger_seconds):
            value = element_state(trigger_s, self._effect,
                                  t_score_seconds)[OPACITY]
            for item in self._items_per_trigger[i]:
                item.setOpacity(value)
        self._cursor = bisect_right(self._trigger_seconds, t_score_seconds)
        self._t = t_score_seconds
        self._last_edges.clear()
        self._apply_reveal(t_score_seconds)

    def current_page(self) -> int:
        """Page of the last crossed trigger (1 before anything fires)."""
        return self._pages[self._cursor - 1] if self._cursor else 1

    def _apply_reveal(self, t_score_seconds: float) -> int:
        changed = 0
        for curve in self._curves:
            edge = reveal_x(curve, t_score_seconds, self._reveal_mode)
            if self._last_edges.get(curve.system) == edge:
                continue
            self._last_edges[curve.system] = edge
            for item in self._revealed_by_system.get(curve.system, ()):
                if item.set_reveal_edge(edge):
                    changed += 1
        return changed
