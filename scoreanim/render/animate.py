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
without rebuilding the applier. A name may hold several effects that run
together ("drop+fade"), so each element carries a TUPLE of effects and a
timescale for each of them; the states combine property by property in
core (core/animation/compose.py). Properties apply through a fixed map
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

How strongly an element animates can follow the recording: ``set_audio``
hands over the peak cache, and a gain scales the finished state away
from rest. Which gain each element takes, and the bookkeeping behind it,
is its own object (render/gain_index.py). Opacity is never modulated.
With no audio, or the response off, there are no gains at all and every
state is exactly what it was before the feature existed.

Spanners (REVEALED_KINDS) are not trigger-driven at all: their clip
edges follow the per-system reveal curves, and that whole concern lives
in render/reveal_driver.py.

The whole page can breathe with the recording too: one size for every
system at time t, each turning around the centre of its own ink. That is
per FRAME rather than per element, so it also sits behind its own object
(render/pulse_driver.py). It reads the RAW loudness, not the volume
response's gain, and at amount 0 no system is touched at all.

Opacity floor overlap caveat (Phase 3, accepted): separate elements
whose ink overlaps double-darken at floor opacity.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from itertools import accumulate
from typing import Iterable, Mapping, Sequence

from scoreanim.core.animation import (PRESETS, Effect, StyleRules,
                                      SystemRevealTrack, TriggerSchedule,
                                      build_presets, combined_state,
                                      derive_windows, effects_for,
                                      modulate_state, read_pulse)
from scoreanim.core.audio import PeakCache
from scoreanim.core.score.identity import ElementId
from scoreanim.core.timing import SwingRegion, TempoMap, resolve_seconds
from scoreanim.render.gain_index import GainIndex
from scoreanim.render.items import ElementItem
from scoreanim.render.properties import PROPERTY_APPLIERS
from scoreanim.render.pulse_driver import PulseDriver
from scoreanim.render.reveal_driver import RevealDriver
from scoreanim.render.system_group import SystemGroupItem

_BEFORE_EVERYTHING = float("-inf")


class AnimationApplier:
    def __init__(self, items: Mapping[ElementId, ElementItem],
                 schedule: TriggerSchedule, tempo_map: TempoMap,
                 style: StyleRules,
                 reveal_tracks: Sequence[SystemRevealTrack] = (),
                 system_groups: Iterable[SystemGroupItem] = ()) -> None:
        self._schedule = schedule
        self._items_per_trigger: tuple[tuple[ElementItem, ...], ...] = tuple(
            tuple(items[eid] for eid in trig.element_ids if eid in items)
            for trig in schedule.triggers)
        # The same rows as ids, for the pure timing arithmetic in core
        # (core/animation/windows.py): it must never see a Qt item. An
        # item with no identity contributes None, which every duration
        # lookup treats as "no engraved duration".
        self._element_ids_per_trigger: tuple[
            tuple[ElementId | None, ...], ...] = tuple(
            tuple(None if item.identity is None else item.identity.element_id
                  for item in row)
            for row in self._items_per_trigger)
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
        # How strongly each element animates, if it follows the
        # recording: one gain per ELEMENT and the audio state behind it,
        # all in its own object (render/gain_index.py).
        self._audio = GainIndex([trig.beats for trig in schedule.triggers],
                                self._element_ids_per_trigger,
                                schedule.duration_by_element)

        # Spanners reveal by clip-grow at their (system, part) reveal
        # edge — no triggers involved (REVEALED_KINDS left the
        # schedule), so the whole concern sits behind its own object.
        self._reveal = RevealDriver(items, reveal_tracks)
        # The page breathing with the recording: one size per frame for
        # every system, so it has its own object too. With no groups it
        # can never do anything (render/pulse_driver.py).
        self._pulse = PulseDriver(system_groups)

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
        self._reveal.resolve(tempo_map, swing)
        self._recompute_windows()
        self._recompute_audio()      # the triggers moved along the audio
        self.refresh(self._t)

    def set_audio(self, peaks: PeakCache | None,
                  offset_seconds: float) -> None:
        """The recording the animation follows, and the audio time of
        score beat 0. Both live playback and export come through here,
        so an exported video pops exactly like the preview.

        `None` is no audio: every element animates as authored. The
        offset is what turns a trigger's score seconds into the audio
        seconds the peak cache is indexed by."""
        if not self._audio.set_audio(peaks, offset_seconds):
            return
        self._recompute_audio()
        self.refresh(self._t)

    def set_style(self, style: StyleRules) -> None:
        """Re-resolve per-element effects and the reveal mode from the
        document's StyleRules (called on every document change; cheap
        no-op when nothing styling-relevant moved)."""
        if style == self._style:
            return
        self._style = style
        self._resolve_effects()
        self._recompute_audio()      # the volume settings may have moved
        # an element whose effects no longer carry a SCALE track would
        # otherwise keep a stale mid-pop transform, and one that lost
        # its offset tracks would be left standing wherever its slide
        # had reached. Unconditional, so it covers a combination losing
        # a component as well: the refresh below writes back only the
        # properties the new effects actually animate.
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
        # One element may animate with SEVERAL effects at once
        # ("drop+fade"), so each item holds a tuple. A plain name gives
        # a tuple of one and behaves exactly as it always did.
        self._effects_per_trigger: tuple[tuple[tuple[Effect, ...], ...],
                                         ...] = tuple(
            tuple(effects_for(rules.resolve(item.identity).effect, presets)
                  for item in items)
            for items in self._items_per_trigger)
        self._recompute_windows()

    def _recompute_audio(self) -> None:
        """Everything the recording drives, re-read from ALL THREE seams
        that can move it: the audio (set_audio), the settings
        (set_style), and the seconds axis itself (set_timing) — a tempo
        edit slides every element to a different stretch of the
        recording.

        Two consumers, one call: the per-element gains
        (render/gain_index.py) and the page's own breathing, which reads
        the same recording through settings of its own. That is why live
        preview and export needed no wiring of their own — both already
        come through these seams."""
        self._audio.recompute(self._trigger_seconds, self._tempo_map,
                              self._swing, self._style.volume)
        self._pulse.configure(self._audio.peaks, self._audio.offset,
                              self._audio.reference,
                              read_pulse(self._style.pulse))

    def _recompute_windows(self) -> None:
        """Per-component timescales and per-trigger effective windows
        (M4.6), recomputed from BOTH configuration seams: set_timing
        (tempo/swing moved the seconds axis) and _resolve_effects (params
        or effect assignments moved). The arithmetic itself is pure and
        lives in core (core/animation/windows.py); all this does is hand
        it element ids instead of items and unpack the answer."""
        plan = derive_windows(
            [trig.beats for trig in self._schedule.triggers],
            self._trigger_seconds,
            self._element_ids_per_trigger,
            self._effects_per_trigger,
            self._schedule.duration_by_element,
            self._tempo_map,
            self._swing)
        self._timescales_per_trigger = plan.timescales_per_trigger
        self._follows = plan.follows_per_trigger
        self._durations = plan.durations
        self._d_max = plan.d_max
        self._lead = plan.lead

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
        changed += self._reveal.apply(t_score_seconds,
                                      self._style.reveal_mode)
        changed += self._pulse.apply(t_score_seconds)
        return changed

    def refresh(self, t_score_seconds: float) -> None:
        """Full apply — after seeks, tempo reloads, and style changes."""
        for i in range(len(self._trigger_seconds)):
            self._apply_trigger(i, t_score_seconds)
        self._cursor = bisect_right(self._trigger_seconds, t_score_seconds)
        self._t = t_score_seconds
        self._reveal.invalidate()
        self._reveal.apply(t_score_seconds, self._style.reveal_mode)
        self._pulse.invalidate()
        self._pulse.apply(t_score_seconds)

    @property
    def uncovered_reveal_keys(self) -> dict[tuple, tuple[ElementId, ...]]:
        """Revealed items no curve can ever reach — they stay hidden.
        Carried for tests and callers (reveal_driver.py)."""
        return self._reveal.uncovered_keys

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
        gains = self._audio.row(i)
        # How loud the recording is at THIS moment, for the elements
        # here that follow it. One lookup per trigger, not per element:
        # every following element in the row reads the same instant.
        live = None
        if gains is not None and any(self._follows[i]):
            live = self._audio.live_gain(t)
        changed = 0
        for j, (item, effects, timescales) in enumerate(zip(
                self._items_per_trigger[i],
                self._effects_per_trigger[i],
                self._timescales_per_trigger[i])):
            state = combined_state(trigger_s, tuple(zip(effects, timescales)),
                                   t)
            # The volume response scales the FINISHED state, once, so an
            # element running two effects at a time is modulated as one
            # thing (core/animation/compose.py). A following element
            # takes the live reading; every other one keeps the average
            # over its own note.
            if gains is not None:
                state = modulate_state(
                    state,
                    live if live is not None and self._follows[i][j]
                    else gains[j])
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
