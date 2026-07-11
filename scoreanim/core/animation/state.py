"""element_state: animation state as a pure function of time.

No hidden state, no timers, no accumulation (CLAUDE.md rule 2). The same
function serves AudioClock playback, scrubbing, and FrameClock export.

Phase 3 arity: trigger resolution happens upstream (TriggerSchedule →
TempoMap.seconds_at) and StyleRules do not exist yet, so the seam takes
the resolved trigger time and one effect. It grows toward the full
ARCHITECTURE §3 signature (identity, style_rules, ...) when StyleRules
land in Phase 5.3.
"""
from __future__ import annotations

from scoreanim.core.animation.effect import Effect, PropertyId


def element_state(trigger_seconds: float, effect: Effect,
                  t_seconds: float) -> dict[PropertyId, float]:
    return effect.state_at(t_seconds - trigger_seconds)
