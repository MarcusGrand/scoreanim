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
without rebuilding the applier. Properties apply through a fixed map
(render/properties.py):
opacity on the ElementItem parent (composites over children), scale
around the item's scale pivot — a whole note (head, stem, flag, beam,
accidental, dots) turns around its noteheads' centre, so it grows and
shrinks as one object. Which ink scales and where it pivots is core
policy (core/animation/scale_groups.py); ink with no pivot never
scales. The two offsets (the slide effect) go to the item as well, not
to setPos: the document's own nudge moves the item too, and the item
adds the two. Unknown properties are skipped, so a preset from a newer
build degrades instead of crashing.

Spanners (REVEALED_KINDS) are not trigger-driven at all: their clip
edges follow the per-system reveal curves (core/animation/reveal.py).
A revealed item whose (system, part) key matches NO reveal track can
never receive an edge; since the FINDING-2 fix (2026-07-22) its clip
children default to hidden (fail-safe — only the floor ghost shows)
and construction warns loudly on stderr, one line per uncovered key
(``uncovered_reveal_keys`` carries them for tests and callers).

Opacity floor overlap caveat (Phase 3, accepted): separate elements
whose ink overlaps double-darken at floor opacity.
"""
from __future__ import annotations

import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict
from itertools import accumulate
from typing import Mapping, Sequence

from scoreanim.core.animation import (PRESETS, REVEALED_KINDS, Effect,
                                      RevealCurve, StyleRules,
                                      SystemRevealTrack, TriggerSchedule,
                                      build_presets, effect_for,
                                      element_state, reveal_x)
from scoreanim.core.score.identity import ElementId
from scoreanim.core.timing import SwingRegion, TempoMap, resolve_seconds
from scoreanim.render.items import ElementItem
from scoreanim.render.properties import PROPERTY_APPLIERS

_BEFORE_EVERYTHING = float("-inf")


class AnimationApplier:
    def __init__(self, items: Mapping[ElementId, ElementItem],
                 schedule: TriggerSchedule, tempo_map: TempoMap,
                 style: StyleRules,
                 reveal_tracks: Sequence[SystemRevealTrack] = ()) -> None:
        self._schedule = schedule
        self._items_per_trigger: tuple[tuple[ElementItem, ...], ...] = tuple(
            tuple(items[eid] for eid in trig.element_ids if eid in items)
            for trig in schedule.triggers)
        # Followed page/system is monotonic non-decreasing over the
        # time-ordered triggers (prefix-max): the view must never turn
        # backward while the clock advances. A per-trigger page/system is
        # only a hint — schedule.py aggregates each beat bucket with min(),
        # and tie/rest/group retiming plus sub-beat bucket-merging across a
        # system break can make a single trigger's value dip N, N-1, N.
        # bisect_right(trigger_seconds, t) is monotone in t, so forward play
        # only grows the cursor → the followed unit only advances; a genuine
        # backward seek moves the cursor earlier and returns the prefix-max
        # up to that time (exactly what a forward playthrough showed there).
        # v1 playback is a linear sweep of a through-composed timeline, so a
        # legitimate backward turn (repeats/D.S.) does not arise.
        self._pages = tuple(accumulate(
            (trig.page for trig in schedule.triggers), max))
        self._systems = tuple(accumulate(
            (trig.system for trig in schedule.triggers), max))
        self._trigger_seconds: list[float] = []
        self._cursor = 0
        self._t = _BEFORE_EVERYTHING
        # timing inputs, kept for window recomputation (M4.6): note-value
        # timescales convert engraved durations through the ONE
        # swing-aware seam, so a bpm/swing change re-times every stretch
        self._tempo_map: TempoMap | None = None
        self._swing: tuple[SwingRegion, ...] = ()

        # Spanners reveal by clip-grow at their (system, part) reveal
        # edge — no triggers involved (REVEALED_KINDS left the
        # schedule). Per-part edges: one part's tied group holds only
        # that part's spanners (ruling A, 2026-07-12).
        self._reveal_tracks = tuple(reveal_tracks)
        track_keys = {(tr.system, tr.part) for tr in self._reveal_tracks}
        by_key: dict[tuple, list[ElementItem]] = defaultdict(list)
        uncovered: dict[tuple, list[ElementId]] = defaultdict(list)
        for eid, item in items.items():
            if (item.identity is None
                    or item.identity.kind not in REVEALED_KINDS):
                continue
            key = (item.system, item.identity.part)
            if item.system is not None and key in track_keys:
                by_key[key].append(item)
            else:
                # no track can ever reach this item: its clip children
                # stay at the hidden construction default (FINDING-2
                # fix — fail safe, never silently visible from t=0)
                uncovered[key].append(eid)
        self._revealed_by_key: dict[tuple, tuple[ElementItem, ...]] = {
            k: tuple(v) for k, v in by_key.items()}
        self.uncovered_reveal_keys: dict[tuple, tuple[ElementId, ...]] = {
            k: tuple(v) for k, v in uncovered.items()}
        for (system, part), eids in sorted(
                self.uncovered_reveal_keys.items(), key=repr):
            print(f"reveal warning [curve-less-key]: system {system} "
                  f"part {part} matches no reveal curve — "
                  f"{len(eids)} spanner(s) stay hidden: "
                  f"{', '.join(str(e) for e in eids)}", file=sys.stderr)
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
        untouched. Note-value stretches re-time here too (M4.6): the
        windows recompute from the new seconds axis."""
        self._tempo_map = tempo_map
        self._swing = tuple(swing)
        self._trigger_seconds = resolve_seconds(
            [trig.beats for trig in self._schedule.triggers],
            tempo_map, swing)
        self._curves = tuple(track.resolve(tempo_map, swing)
                             for track in self._reveal_tracks)
        self._recompute_windows()
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
        # keep a stale mid-pop transform, and one that lost its offset
        # tracks would be left standing wherever its slide had reached
        for items in self._items_per_trigger:
            for item in items:
                if item.scale() != 1.0:
                    item.setScale(1.0)
                if item.animated_offset != (0.0, 0.0):
                    item.set_animated_offset(0.0, 0.0)
        self.refresh(self._t)

    def _resolve_effects(self) -> None:
        rules = self._style
        # Built-in presets are rebuilt at the document's floor (Phase
        # 7.2) and effect_params (M4): both are StyleRules changes, so
        # they arrive through set_style's re-resolve + refresh like any
        # styling edit. Overlaying onto PRESETS keeps entries registered
        # beyond the built-ins resolvable (their own envelopes
        # untouched).
        presets = {**PRESETS, **build_presets(rules.floor_opacity,
                                              rules.effect_params)}
        self._effects_per_trigger: tuple[tuple[Effect, ...], ...] = tuple(
            tuple(effect_for(rules.resolve(item.identity).effect, presets)
                  for item in items)
            for items in self._items_per_trigger)
        self._recompute_windows()

    def _recompute_windows(self) -> None:
        """Per-item timescales and per-trigger effective windows (M4.6),
        recomputed from BOTH configuration seams: set_timing (tempo/
        swing moved the seconds axis) and _resolve_effects (params or
        effect assignments moved). A note-value effect's timescale is
        its element's engraved duration in seconds over the effect's
        authored duration (F7 — guarded dur > 0 both sides, absent
        entry → 1.0); the engraved end resolves through the ONE
        swing-aware seam in a single batched resolve_seconds call. A
        trigger's window is max(shift + duration × timescale) over its
        items; `lead` is the F3 forward bound (max positive lead of any
        negatively shifted effect). Before timing exists (construction)
        stretches park at 1.0 — set_timing recomputes immediately."""
        triggers = self._schedule.triggers
        durs = self._schedule.duration_by_element
        stretch: dict[tuple[int, int], float] = {}
        if self._tempo_map is not None and durs:
            refs: list[tuple[int, int]] = []
            end_beats: list[float] = []
            for i, trig in enumerate(triggers):
                for j, (item, effect) in enumerate(
                        zip(self._items_per_trigger[i],
                            self._effects_per_trigger[i])):
                    if (not effect.settle_to_note_value
                            or effect.duration <= 0.0
                            or item.identity is None):
                        continue
                    dur_beats = durs.get(item.identity.element_id, 0.0)
                    if dur_beats > 0.0:
                        refs.append((i, j))
                        end_beats.append(trig.beats + dur_beats)
            if refs:
                ends_s = resolve_seconds(end_beats, self._tempo_map,
                                         self._swing)
                for (i, j), end_s in zip(refs, ends_s):
                    dur_s = end_s - self._trigger_seconds[i]
                    if dur_s > 0.0:
                        stretch[(i, j)] = dur_s
        timescales: list[tuple[float, ...]] = []
        windows: list[float] = []
        lead = 0.0
        for i in range(len(triggers)):
            row: list[float] = []
            window = 0.0
            for j, effect in enumerate(self._effects_per_trigger[i]):
                dur_s = stretch.get((i, j))
                ts = dur_s / effect.duration if dur_s is not None else 1.0
                row.append(ts)
                window = max(window,
                             effect.trigger_shift + effect.duration * ts)
                lead = max(lead, -effect.trigger_shift)
            timescales.append(tuple(row))
            windows.append(window)
        self._timescales_per_trigger = tuple(timescales)
        self._durations = tuple(windows)
        self._d_max = max(windows, default=0.0)
        self._lead = max(0.0, lead)

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
        for item, effect, timescale in zip(self._items_per_trigger[i],
                                           self._effects_per_trigger[i],
                                           self._timescales_per_trigger[i]):
            state = element_state(trigger_s, effect, t, timescale)
            for prop, value in state.items():
                applier = PROPERTY_APPLIERS.get(prop)
                if applier is not None:
                    applier(item, value)
            changed += 1
        return changed

    def _apply_window(self, t: float, t_prev: float) -> int:
        """Re-evaluate triggers whose timed effects were mid-transition
        at ANY point since the previously applied time — including the
        one final evaluation that settles a transition expiring between
        two calls (evaluating past the last keyframe yields its final
        value, so the settle equals a fresh refresh). Two M4.6 bounds:
        the F2 expiry guard skips triggers whose effective window ended
        before min(t, t_prev) — cost tracks elements genuinely
        mid-transition, not d_max — and the F3 forward `lead` bound
        evaluates not-yet-crossed triggers whose negatively shifted
        effects are already live (early evaluation before the shifted
        step is a natural no-op: the envelope yields its initial)."""
        changed = 0
        floor_t = min(t, t_prev)
        if self._d_max > 0.0:
            lo = bisect_left(self._trigger_seconds, floor_t - self._d_max)
            for i in range(lo, self._cursor):
                d = self._durations[i]
                if d > 0.0 and self._trigger_seconds[i] + d >= floor_t:
                    changed += self._apply_trigger(i, t)
        if self._lead > 0.0:
            # max(t, t_prev): a backward scrub must also RE-evaluate the
            # not-yet-crossed triggers the lead had lit before the jump,
            # or they would hold their early-lit state
            hi = bisect_right(self._trigger_seconds,
                              max(t, t_prev) + self._lead)
            for i in range(self._cursor, hi):
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
