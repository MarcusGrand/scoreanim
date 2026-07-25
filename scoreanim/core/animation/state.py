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

from scoreanim.core.animation.effect import Effect, PropertyId


def element_state(trigger_seconds: float, effect: Effect,
                  t_seconds: float,
                  timescale: float = 1.0) -> dict[PropertyId, float]:
    t_rel = (t_seconds - trigger_seconds - effect.trigger_shift) / timescale
    return effect.state_at(t_rel)
