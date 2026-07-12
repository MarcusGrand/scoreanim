"""The effect preset registry (rule 6: effects are data, not code).

Adding an effect means adding an entry HERE — nothing in the evaluator
(core/animation/effect.py, state.py) or the render applier changes.
The registry drives the UI (the effect menu enumerates it) and the
StyleRules resolution (names in the doc resolve here, unknown names
fail soft to the default so an old build opening a newer project
degrades instead of crashing).
"""
from __future__ import annotations

from scoreanim.core.animation.effect import Effect, appear

# Ghost-score floor: dimmed ink before the trigger (Phase 3 value,
# moved here from the UI in Phase 5.3).
FLOOR_OPACITY = 0.3

DEFAULT_EFFECT = "appear"

PRESETS: dict[str, Effect] = {
    "appear": appear(FLOOR_OPACITY),
}


def effect_for(name: str | None) -> Effect:
    """Resolve a stored effect name; unknown/None → the default preset
    (the stored intent survives round-trips untouched)."""
    if name is not None and name in PRESETS:
        return PRESETS[name]
    return PRESETS[DEFAULT_EFFECT]
