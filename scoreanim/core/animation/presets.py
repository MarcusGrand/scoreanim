"""The effect preset registry (rule 6: effects are data, not code).

Adding an effect means adding an entry HERE — nothing in the evaluator
(core/animation/effect.py, state.py) or the render applier changes.
The registry drives the UI (the effect menu enumerates it) and the
StyleRules resolution (names in the doc resolve here, unknown names
fail soft to the default so an old build opening a newer project
degrades instead of crashing).
"""
from __future__ import annotations

from scoreanim.core.animation.effect import (OPACITY, SCALE, Easing, Effect,
                                             Envelope, Keyframe, appear)

# Ghost-score floor: dimmed ink before the trigger (Phase 3 value,
# moved here from the UI in Phase 5.3).
FLOOR_OPACITY = 0.3

DEFAULT_EFFECT = "appear"

# pop (PHASES 5.4): appear's opacity step plus a scale bump around the
# element's stored anchor — 1.25× at onset, easing back to 1.0 over
# 0.25 s. Pure data; the effects-as-data proof (rule 6).
_POP_SCALE = 1.25
_POP_SETTLE_S = 0.25

PRESETS: dict[str, Effect] = {
    "appear": appear(FLOOR_OPACITY),
    "pop": Effect("pop", {
        OPACITY: Envelope(initial=FLOOR_OPACITY,
                          keyframes=(Keyframe(0.0, 1.0, Easing.STEP),)),
        SCALE: Envelope(initial=1.0,
                        keyframes=(Keyframe(0.0, _POP_SCALE, Easing.STEP),
                                   Keyframe(_POP_SETTLE_S, 1.0,
                                            Easing.LINEAR))),
    }),
}


def effect_for(name: str | None) -> Effect:
    """Resolve a stored effect name; unknown/None → the default preset
    (the stored intent survives round-trips untouched)."""
    if name is not None and name in PRESETS:
        return PRESETS[name]
    return PRESETS[DEFAULT_EFFECT]
