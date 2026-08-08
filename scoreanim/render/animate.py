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
policy (core/animation/scale_groups.py); ink with no pivot never scales.
The two offsets (the slide effect) go to the item as well, not to
setPos: the document's own nudge moves the item too, and the item adds
the two. Unknown properties are skipped, so a preset from a newer build
degrades instead of crashing.

The glow is the fussiest of the five, and it has its own object
(render/glow_driver.py). Only note ink glows at all; an accidental, a
lyric and a tie share the halo of the note beside them; and a tied chain
glows as the one note it is, which needs a second evaluation stretched
to the whole chain. What the halo LOOKS like is document intent and goes
to the items once per document change (render/glow_sprite.py) — only how
brightly it burns moves per frame.

How strongly an element animates can follow the recording: ``set_audio``
hands over the peak cache, and a gain scales the finished state away
from rest. Which gain each element takes, and the bookkeeping behind it,
is its own object (render/gain_index.py). Opacity is never modulated.
With no audio, or the response off, there are no gains at all and every
state is exactly what it was before the feature existed.

Spanners (REVEALED_KINDS) are not trigger-driven at all: their clip
edges follow the per-system reveal curves, and that whole concern lives
in render/reveal_driver.py.

The whole page can breathe as well: one size per system at time t, each
turning around the centre of its own ink. Two things move it — the
recording's raw loudness (not the volume response's gain) and a bump on
every beat, sized by how many noteheads land there. Both are per FRAME
rather than per element, so they sit behind their own object
(render/pulse_driver.py); the bump half needs no audio at all, and with
both amounts at 0 no system is touched.

Opacity floor overlap caveat (Phase 3, accepted): separate elements
whose ink overlaps double-darken at floor opacity.
"""
from __future__ import annotations

from bisect import bisect_right
from typing import Iterable, Mapping, Sequence

from scoreanim.core.animation import (GLOW, PRESETS, Effect, GlowScope,
                                      StyleRules, SystemRevealTrack,
                                      TriggerSchedule, build_bumps,
                                      build_presets, combined_state,
                                      derive_windows, effects_for,
                                      modulate_state, read_pulse)
from scoreanim.core.animation.windows import reapply_indices
from scoreanim.core.audio import PeakCache
from scoreanim.core.score.identity import ElementId
from scoreanim.core.timing import SwingRegion, TempoMap, resolve_seconds
from scoreanim.render.gain_index import GainIndex
from scoreanim.render.glow_driver import GlowDriver
from scoreanim.render.glow_sprite import push_glow_style
from scoreanim.render.items import ElementItem
from scoreanim.render.properties import PROPERTY_APPLIERS
from scoreanim.render.pulse_driver import PulseDriver
from scoreanim.render.reveal_driver import RevealDriver
from scoreanim.render.system_group import SystemGroupItem
from scoreanim.render.trigger_index import TriggerIndex

_BEFORE_EVERYTHING = float("-inf")


class AnimationApplier:
    def __init__(self, items: Mapping[ElementId, ElementItem],
                 schedule: TriggerSchedule, tempo_map: TempoMap,
                 style: StyleRules,
                 reveal_tracks: Sequence[SystemRevealTrack] = (),
                 system_groups: Iterable[SystemGroupItem] = (),
                 glow: GlowScope | None = None) -> None:
        self._items = items
        self._glow_scope = glow
        self._trigger_seconds: list[float] = []
        self._cursor = 0
        self._t = _BEFORE_EVERYTHING
        # timing inputs, kept for window recomputation (M4.6): note-value
        # timescales convert engraved durations through the ONE
        # swing-aware seam, so a bpm/swing change re-times every stretch
        self._tempo_map: TempoMap | None = None
        self._swing: tuple[SwingRegion, ...] = ()
        self._adopt_schedule(schedule)

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

    def _adopt_schedule(self, schedule: TriggerSchedule) -> None:
        """The schedule-shaped state, (re)built as one unit — the row
        index, the gain index and the glow driver are all keyed by the
        schedule's rows, so they live and die together."""
        self._schedule = schedule
        # The schedule's rows against this scene — items, ids, and the
        # followed page/system (render/trigger_index.py).
        self._index = TriggerIndex(self._items, schedule)
        # How strongly each element animates, if it follows the
        # recording: one gain per ELEMENT and the audio state behind it,
        # all in its own object (render/gain_index.py).
        self._audio = GainIndex([trig.beats for trig in schedule.triggers],
                                self._index.ids,
                                schedule.duration_by_element)
        # Which ink may glow at all, which of it shares another note's
        # halo, and how long a tied chain burns (render/glow_driver.py).
        self._glow = GlowDriver(self._items, self._index, self._glow_scope)

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
        self._recompute_bumps()      # and every onset bump moved with them
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
        self._recompute_bumps()      # and so may the pulse settings
        # an element whose effects no longer carry a SCALE track would
        # otherwise keep a stale mid-pop transform, one that lost its
        # offset tracks would be left standing wherever its slide had
        # reached, and one that lost its glow would keep a lit halo.
        # Unconditional, so it covers a combination losing a component
        # as well: the refresh below writes back only the properties the
        # new effects actually animate.
        for items in self._index.items:
            for item in items:
                if item.scale() != 1.0:
                    item.setScale(1.0)
                if item.animated_offset != (0.0, 0.0):
                    item.set_animated_offset(0.0, 0.0)
        # Ties glow but never receive a trigger, so putting the halos
        # out is the driver's job, not this loop's.
        self._glow.extinguish()
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
        # The glow's colour and radius never reach an envelope — they
        # are what the halo LOOKS like, not what it does over time — so
        # they go to the items here, once, rather than every frame.
        push_glow_style(self._glow.items, rules.effect_params)
        # One element may animate with SEVERAL effects at once
        # ("drop+fade"), so each item holds a tuple. A plain name gives
        # a tuple of one and behaves exactly as it always did.
        self._effects_per_trigger: tuple[tuple[tuple[Effect, ...], ...],
                                         ...] = tuple(
            tuple(effects_for(rules.resolve(item.identity).effect, presets)
                  for item in items)
            for items in self._index.items)
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

    def _recompute_bumps(self) -> None:
        """Where every system's onset bump sits on the seconds axis, and
        how hard it hits. No audio in it at all — the schedule is the
        whole input — so it is rebuilt from the two seams that can move
        it: set_timing (a tempo edit moves every bump) and set_style (the
        settings the strengths are measured against).

        Each item's OWN system goes to core, never the trigger's single
        system hint: around a system break one beat's ink straddles two
        systems, and both should bump."""
        self._pulse.set_bumps(build_bumps(
            self._trigger_seconds,
            [[(None if item.identity is None else item.identity.kind,
               item.system) for item in row]
             for row in self._index.items],
            read_pulse(self._style.pulse)))

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
            self._index.ids,
            self._effects_per_trigger,
            self._schedule.duration_by_element,
            self._tempo_map,
            self._swing)
        self._timescales_per_trigger = plan.timescales_per_trigger
        self._follows = plan.follows_per_trigger
        self._lead = plan.lead
        # A tied chain's halo outlasts its first notehead, so its
        # trigger has to keep being re-evaluated after that notehead's
        # own window has closed — or every follower would freeze
        # mid-glow.
        self._glow.resolve([trig.beats for trig in self._schedule.triggers],
                           self._trigger_seconds, self._effects_per_trigger,
                           self._tempo_map, self._swing)
        self._durations = tuple(max(d, self._glow.window(i))
                                for i, d in enumerate(plan.durations))
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
        return self._index.page_at(self._cursor)

    def current_system(self) -> int:
        """System of the last crossed trigger, off the same bisect
        cursor, consumed identically by live follow and export."""
        return self._index.system_at(self._cursor)

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
                self._index.items[i],
                self._effects_per_trigger[i],
                self._timescales_per_trigger[i])):
            state = combined_state(trigger_s, tuple(zip(effects, timescales)),
                                   t)
            # A tied chain glows as the one note it is: the same light
            # over the whole chain, from a second evaluation stretched
            # to the chain's own length. Everything else stays on this
            # notehead's own window.
            chain = self._glow.chain_glow(i, j, trigger_s, effects, t)
            if chain is not None:
                state = {**state, GLOW: chain}
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
            # Whatever this note's halo ended up at goes to the ink that
            # shares it — its accidental, its lyric, its ties, and the
            # rest of its tied chain.
            changed += 1 + self._glow.spread(i, j, state.get(GLOW))
        return changed

    def _apply_window(self, t: float, t_prev: float) -> int:
        """Re-evaluate triggers whose timed effects were mid-transition
        since the previously applied time. The index arithmetic — the
        F2 expiry guard and the F3 forward lead — is pure and lives in
        core (windows.reapply_indices)."""
        changed = 0
        for i in reapply_indices(self._trigger_seconds, self._durations,
                                 self._d_max, self._lead, self._cursor,
                                 t, t_prev):
            changed += self._apply_trigger(i, t)
        return changed
