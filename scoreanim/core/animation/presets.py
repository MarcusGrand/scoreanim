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

from typing import Mapping

# Ghost-score floor DEFAULT: dimmed ink before the trigger (Phase 3
# value, moved here from the UI in Phase 5.3). Since Phase 7.2 the
# working value is document intent (StyleRules.floor_opacity, same
# default); registries for other floors come from build_presets.
FLOOR_OPACITY = 0.3

DEFAULT_EFFECT = "appear"

# pop (PHASES 5.4): appear's opacity step plus a scale bump around the
# element's stored anchor — 1.25× at onset, easing back to 1.0 over
# 0.25 s. Pure data; the effects-as-data proof (rule 6).
_POP_SCALE = 1.25
_POP_SETTLE_S = 0.25


def build_presets(floor: float) -> dict[str, Effect]:
    """The registry as a function of the document's floor opacity —
    still pure data (rule 6): the same named bundles of
    (property, Envelope) tracks, with `floor` as each opacity
    envelope's pre-trigger `initial`."""
    return {
        "appear": appear(floor),
        "pop": Effect("pop", {
            OPACITY: Envelope(initial=floor,
                              keyframes=(Keyframe(0.0, 1.0, Easing.STEP),)),
            SCALE: Envelope(initial=1.0,
                            keyframes=(Keyframe(0.0, _POP_SCALE,
                                                Easing.STEP),
                                       Keyframe(_POP_SETTLE_S, 1.0,
                                                Easing.LINEAR))),
        }),
    }


# Default registry: drives the UI effect menu and any resolution that
# has no document floor at hand.
PRESETS: dict[str, Effect] = build_presets(FLOOR_OPACITY)


def effect_for(name: str | None,
               presets: Mapping[str, Effect] = PRESETS) -> Effect:
    """Resolve a stored effect name; unknown/None → the default preset
    (the stored intent survives round-trips untouched)."""
    if name is not None and name in presets:
        return presets[name]
    return presets[DEFAULT_EFFECT]
