"""element_state: animation state as a pure function of time.

No hidden state, no timers, no accumulation (CLAUDE.md rule 2). The same
function serves AudioClock playback, scrubbing, and FrameClock export.

M4 kernel: ``(t − trigger − effect.trigger_shift) / timescale``. The
shift is absolute seconds — applied BEFORE the timescale division, so a
±100 ms peak offset means ±100 ms regardless of note length — and the
timescale is a per-element scalar the caller resolves (note-value
settle, F7); both are DATA inputs to this one evaluation, never a
branch on an effect's name (rule 6).
"""
from __future__ import annotations

from typing import Sequence

from scoreanim.core.animation.compose import compose_states
from scoreanim.core.animation.effect import Effect, PropertyId


def element_state(trigger_seconds: float, effect: Effect,
                  t_seconds: float,
                  timescale: float = 1.0) -> dict[PropertyId, float]:
    t_rel = (t_seconds - trigger_seconds - effect.trigger_shift) / timescale
    return effect.state_at(t_rel)


def combined_state(trigger_seconds: float,
                   components: Sequence[tuple[Effect, float]],
                   t_seconds: float) -> dict[PropertyId, float]:
    """The state of an element animating with several effects at once
    ("drop+fade"). Each component is an (effect, timescale) pair and
    goes through the ONE kernel above, keeping its own trigger shift and
    its own timescale; the results combine property by property
    (compose.py). One component returns exactly what element_state
    returns."""
    return compose_states([element_state(trigger_seconds, effect, t_seconds,
                                         timescale)
                           for effect, timescale in components])
