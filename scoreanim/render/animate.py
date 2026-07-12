"""Schedule-driven animation applied to ScoreScenes items.

The cursor is a cache, never state: ``apply_at(t)`` leaves the scene in
the same state whether t was reached by ticking forward, scrubbing
backward, or a fresh ``refresh(t)`` — element state is a pure function
of t (CLAUDE.md rule 2). Step effects change only when t crosses their
trigger, so diff-applying crossed triggers is exact; timed effects
(duration > 0, e.g. pop's scale decay) are additionally re-evaluated
while t sits inside their transition window [trigger, trigger +
duration] — the window is re-derived from t each call (a bisect over
trigger times), never accumulated, so scrubbing stays stateless.

Per-element effects come from StyleRules (element override > part rule >
default) resolved against the preset registry; ``set_style`` re-resolves
without rebuilding the applier. Properties apply through a fixed map:
opacity on the ElementItem parent (composites over children), scale
around the element's stored anchor — restricted to kinds with a
meaningful one (a beam scaling around its own center reads as jitter,
not pop). Unknown properties are skipped, so a preset from a newer
build degrades instead of crashing.

Spanners (REVEALED_KINDS) are not trigger-driven at all: their clip
edges follow the per-system reveal curves (core/animation/reveal.py).

Opacity floor overlap caveat (Phase 3, accepted): separate elements
whose ink overlaps double-darken at floor opacity.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from typing import Callable, Mapping, Sequence

from scoreanim.core.animation import (OPACITY, PRESETS, REVEALED_KINDS,
                                      SCALE, Effect, RevealCurve, StyleRules,
                                      SystemRevealTrack, TriggerSchedule,
                                      build_presets, effect_for,
                                      element_state, reveal_x)
from scoreanim.core.score.identity import ElementId, ElementKind
from scoreanim.core.timing import SwingRegion, TempoMap, resolve_seconds
from scoreanim.render.items import ElementItem

_BEFORE_EVERYTHING = float("-inf")

# Kinds a SCALE track may transform (render-side rule; the evaluator is
# untouched by it). Anchored ink only: heads, slashes, accidentals,
# articulations, dots (OTHER-with-onset). Stems/beams/flags/ledgers
# scaling independently of their heads reads as jitter.
_SCALABLE_KINDS = frozenset({
    ElementKind.NOTEHEAD, ElementKind.SLASH, ElementKind.ACCIDENTAL,
    ElementKind.ARTICULATION, ElementKind.OTHER,
})


def _apply_opacity(item: ElementItem, value: float) -> None:
    item.setOpacity(value)


def _apply_scale(item: ElementItem, value: float) -> None:
    if item.identity is None or item.identity.kind not in _SCALABLE_KINDS:
        return
    if item.anchor is None:
        return
    item.setScale(value)


_PROPERTY_APPLIERS: Mapping[str, Callable[[ElementItem, float], None]] = {
    OPACITY: _apply_opacity,
    SCALE: _apply_scale,
}


class AnimationApplier:
    def __init__(self, items: Mapping[ElementId, ElementItem],
                 schedule: TriggerSchedule, tempo_map: TempoMap,
                 style: StyleRules,
                 reveal_tracks: Sequence[SystemRevealTrack] = ()) -> None:
        self._schedule = schedule
        self._items_per_trigger: tuple[tuple[ElementItem, ...], ...] = tuple(
            tuple(items[eid] for eid in trig.element_ids if eid in items)
            for trig in schedule.triggers)
        self._pages = tuple(trig.page for trig in schedule.triggers)
        self._systems = tuple(trig.system for trig in schedule.triggers)
        self._trigger_seconds: list[float] = []
        self._cursor = 0
        self._t = _BEFORE_EVERYTHING

        # Spanners reveal by clip-grow at their (system, part) reveal
        # edge — no triggers involved (REVEALED_KINDS left the
        # schedule). Per-part edges: one part's tied group holds only
        # that part's spanners (ruling A, 2026-07-12).
        self._reveal_tracks = tuple(reveal_tracks)
        by_key: dict[tuple, list[ElementItem]] = defaultdict(list)
        for item in items.values():
            if (item.identity is not None and item.system is not None
                    and item.identity.kind in REVEALED_KINDS):
                by_key[(item.system, item.identity.part)].append(item)
        self._revealed_by_key: dict[tuple, tuple[ElementItem, ...]] = {
            k: tuple(v) for k, v in by_key.items()}
        self._curves: tuple[RevealCurve, ...] = ()
        self._last_edges: dict[tuple, float] = {}  # (system, part) → edge

        self._style = style
        self._resolve_effects()
        self.set_timing(tempo_map)       # also refreshes: floor everywhere

    # -- configuration -------------------------------------------------------

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

    def set_style(self, style: StyleRules) -> None:
        """Re-resolve per-element effects and the reveal mode from the
        document's StyleRules (called on every document change; cheap
        no-op when nothing styling-relevant moved)."""
        if style == self._style:
            return
        self._style = style
        self._resolve_effects()
        # an element whose effect lost its SCALE track would otherwise
        # keep a stale mid-pop transform
        for items in self._items_per_trigger:
            for item in items:
                if item.scale() != 1.0:
                    item.setScale(1.0)
        self.refresh(self._t)

    def _resolve_effects(self) -> None:
        rules = self._style
        # Built-in presets are rebuilt at the document's floor (Phase
        # 7.2): a floor change is a StyleRules change, so it arrives
        # through set_style's re-resolve + refresh like any styling
        # edit. Overlaying onto PRESETS keeps entries registered beyond
        # the built-ins resolvable (their own envelopes untouched).
        presets = {**PRESETS, **build_presets(rules.floor_opacity)}
        self._effects_per_trigger: tuple[tuple[Effect, ...], ...] = tuple(
            tuple(effect_for(rules.resolve(item.identity).effect, presets)
                  for item in items)
            for items in self._items_per_trigger)
        self._durations = tuple(
            max((e.duration for e in effects), default=0.0)
            for effects in self._effects_per_trigger)
        self._d_max = max(self._durations, default=0.0)

    # -- application ---------------------------------------------------------

    def apply_at(self, t_score_seconds: float) -> int:
        """Diff-apply from the last applied time; returns items touched.
        Crossed triggers step; triggers whose transition window contains
        t re-evaluate; reveal edges fan out only when a system's edge
        actually moved (STEPPED edges hold between onsets, so idle cost
        stays flat)."""
        t_prev = self._t
        idx = bisect_right(self._trigger_seconds, t_score_seconds)
        changed = 0
        for i in range(min(self._cursor, idx), max(self._cursor, idx)):
            changed += self._apply_trigger(i, t_score_seconds)
        self._cursor = idx
        self._t = t_score_seconds
        changed += self._apply_window(t_score_seconds, t_prev)
        changed += self._apply_reveal(t_score_seconds)
        return changed

    def refresh(self, t_score_seconds: float) -> None:
        """Full apply — after seeks, tempo reloads, and style changes."""
        for i in range(len(self._trigger_seconds)):
            self._apply_trigger(i, t_score_seconds)
        self._cursor = bisect_right(self._trigger_seconds, t_score_seconds)
        self._t = t_score_seconds
        self._last_edges.clear()
        self._apply_reveal(t_score_seconds)

    def current_page(self) -> int:
        """Page of the last crossed trigger (1 before anything fires)."""
        return self._pages[self._cursor - 1] if self._cursor else 1

    def current_system(self) -> int:
        """System of the last crossed trigger (1 before anything fires)
        — the current_page() idiom on the same bisect cursor, consumed
        identically by live follow and export (Phase 7)."""
        return self._systems[self._cursor - 1] if self._cursor else 1

    # -- internals -----------------------------------------------------------

    def _apply_trigger(self, i: int, t: float) -> int:
        trigger_s = self._trigger_seconds[i]
        changed = 0
        for item, effect in zip(self._items_per_trigger[i],
                                self._effects_per_trigger[i]):
            state = element_state(trigger_s, effect, t)
            for prop, value in state.items():
                applier = _PROPERTY_APPLIERS.get(prop)
                if applier is not None:
                    applier(item, value)
            changed += 1
        return changed

    def _apply_window(self, t: float, t_prev: float) -> int:
        """Re-evaluate triggers whose timed effects were mid-transition
        at ANY point since the previously applied time — including the
        one final evaluation that settles a transition expiring between
        two calls (evaluating past the last keyframe yields its final
        value, so the settle equals a fresh refresh). Empty range when
        no timed effect is assigned (d_max == 0)."""
        if self._d_max <= 0.0:
            return 0
        lo = bisect_left(self._trigger_seconds,
                         min(t_prev, t) - self._d_max)
        changed = 0
        for i in range(lo, self._cursor):
            if self._durations[i] > 0.0:
                changed += self._apply_trigger(i, t)
        return changed

    def _apply_reveal(self, t_score_seconds: float) -> int:
        changed = 0
        mode = self._style.reveal_mode
        for curve in self._curves:
            key = (curve.system, curve.part)
            edge = reveal_x(curve, t_score_seconds, mode)
            if self._last_edges.get(key) == edge:
                continue
            self._last_edges[key] = edge
            for item in self._revealed_by_key.get(key, ()):
                if item.set_reveal_edge(edge):
                    changed += 1
        return changed
