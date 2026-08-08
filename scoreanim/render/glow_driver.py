"""The glow half of the applier: whose halo it is, and how long it burns.

Every other property reaches every animated element. The glow does not
(Marcus, 2026-08-06): a halo says "this note is sounding", so only notes
carry one. That is two rules, and this object is both of them applied to
a real scene.

**The gate.** An item may light only if its kind is in `GLOWING_KINDS`
(core/animation/glow_scope.py). It is written onto the item once, here,
and `render/properties.py` reads it — the scale_pivot precedent: policy
decided in core, carried on the item, applied without deciding anything.

**The shared halo.** An accidental, a lyric and a tie glow with the
notehead beside them, and a tied chain's noteheads all glow as the one
note they are. So a piece of ink is either a LEADER, whose halo the
effect evaluates as usual, or a FOLLOWER, which is put on the leader's
own value the moment the leader is evaluated. A follower's gate is
cleared: its halo is not its own, and letting it light itself would race
the leader's write, since the two sit at different triggers.

**The longer burn.** A chain leader's halo has to last the whole chain,
not the first notehead's engraved value. That is one number per leader —
a timescale, the same one the note-value settle already runs on
(core/animation/windows.py) — so the leader is evaluated a SECOND time,
with the chain's own stretch, and only its glow is taken from that. The
first evaluation still owns everything else: a pop on a tied note pops
over its own notehead, exactly as it did.

The second evaluation also widens the trigger's window, or the applier
would stop re-evaluating the leader when its own note ended and every
follower would freeze mid-glow.

Nothing here knows the word "glow" means an effect called glow (rule 6):
it reads the GLOW property off a composed state and writes it to items.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from scoreanim.core.animation import (GLOW, GLOWING_KINDS, Effect, GlowScope,
                                      combined_state)
from scoreanim.core.score.identity import Beats, ElementId
from scoreanim.core.timing import SwingRegion, TempoMap, resolve_seconds
from scoreanim.render.items import ElementItem
from scoreanim.render.trigger_index import TriggerIndex


class GlowDriver:
    """Which items may glow, which of them share a halo, and how far a
    shared one is stretched."""

    def __init__(self, items: Mapping[ElementId, ElementItem],
                 index: TriggerIndex,
                 scope: GlowScope | None = None) -> None:
        scope = scope if scope is not None else GlowScope()

        # -- the gate: only note ink may ever light ----------------------
        glowing: dict[ElementId, ElementItem] = {}
        for eid, item in items.items():
            lights = (item.identity is not None
                      and item.identity.kind in GLOWING_KINDS)
            item.set_can_glow(lights)
            if lights:
                glowing[eid] = item

        # -- the shared halo: leader → the items that copy it ------------
        followers: dict[ElementId, tuple[ElementItem, ...]] = {}
        for leader, eids in scope.followers().items():
            if leader not in glowing:
                continue                 # the leader is off this page set
            row = tuple(glowing[eid] for eid in eids if eid in glowing)
            if not row:
                continue
            followers[leader] = row
            for item in row:
                item.set_can_glow(False)     # its halo is its leader's
        self.items: tuple[ElementItem, ...] = tuple(glowing.values())

        # The applier addresses its elements by (trigger, item) rather
        # than by id, so both maps are re-keyed that way once.
        self._spread: dict[tuple[int, int], tuple[ElementItem, ...]] = {}
        self._span: dict[tuple[int, int], Beats] = {}
        for i, row in enumerate(index.ids):
            for j, eid in enumerate(row):
                if eid is None:
                    continue
                if eid in followers:
                    self._spread[(i, j)] = followers[eid]
                if eid in scope.span:
                    self._span[(i, j)] = scope.span[eid]

        self._timescales: dict[tuple[int, int], tuple[float, ...]] = {}
        self._windows: dict[int, float] = {}

    # -- configuration ---------------------------------------------------

    def resolve(self, trigger_beats: Sequence[Beats],
                trigger_seconds: Sequence[float],
                effects_per_trigger: Sequence[Sequence[Sequence[Effect]]],
                tempo_map: TempoMap | None,
                swing: Sequence[SwingRegion] = ()) -> None:
        """Work out each chain leader's stretched timescales, and how far
        past its trigger that pushes the window.

        Recomputed from the same two seams the ordinary windows are
        (`core/animation/windows.py`): a tempo or swing edit moves the
        seconds axis under every chain, and a style edit may hand an
        element a different effect. Chain ends resolve through the ONE
        swing-aware seam, batched."""
        self._timescales = {}
        self._windows = {}
        if tempo_map is None or not self._span:
            return
        refs = [(i, j) for (i, j) in self._span
                if i < len(trigger_beats) and j < len(effects_per_trigger[i])]
        if not refs:
            return
        ends_s = resolve_seconds(
            [trigger_beats[i] + self._span[(i, j)] for i, j in refs],
            tempo_map, swing)
        for (i, j), end_s in zip(refs, ends_s):
            dur_s = end_s - trigger_seconds[i]
            if dur_s <= 0.0:
                continue
            scales: list[float] = []
            stretched = False
            window = 0.0
            for effect in effects_per_trigger[i][j]:
                ts = 1.0
                if effect.settle_to_note_value and effect.duration > 0.0:
                    ts = dur_s / effect.duration
                    stretched = True
                scales.append(ts)
                window = max(window,
                             effect.trigger_shift + effect.duration * ts)
            if not stretched:
                # Nothing here stretches to the note's value, so the
                # chain's own length changes nothing: the leader's first
                # evaluation is already the right answer.
                continue
            self._timescales[(i, j)] = tuple(scales)
            self._windows[i] = max(self._windows.get(i, 0.0), window)

    def window(self, i: int) -> float:
        """How long trigger i must keep being re-evaluated for its chain
        leaders' sake. 0 when it leads no stretched chain."""
        return self._windows.get(i, 0.0)

    def extinguish(self) -> None:
        """Put every halo out. The applier calls this when the styling
        changes, so ink that lost its glow — including a tie, which no
        trigger ever reaches — cannot keep a lit halo standing."""
        for item in self.items:
            if item.glow_strength != 0.0:
                item.set_glow(0.0)

    # -- application -----------------------------------------------------

    def chain_glow(self, i: int, j: int, trigger_s: float,
                   effects: Iterable[Effect], t: float) -> float | None:
        """This element's glow over its whole tied chain, or None when it
        does not lead one — in which case its ordinary state already
        says the right thing."""
        scales = self._timescales.get((i, j))
        if scales is None:
            return None
        return combined_state(trigger_s, tuple(zip(effects, scales)),
                              t).get(GLOW)

    def spread(self, i: int, j: int, value: float | None) -> int:
        """Put this element's finished glow on every piece of ink that
        shares its halo. Returns how many items were touched."""
        row = self._spread.get((i, j))
        if row is None or value is None:
            return 0
        for item in row:
            item.set_glow(value)
        return len(row)
