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
# 0.25 s. Pure data; the effects-as-data proof (rule 6). Since M4 the
# two constants are the DEFAULTS for the document's effect_params.
_POP_SCALE = 1.25
_POP_SETTLE_S = 0.25

# fade: opacity ramps from the document floor up to full over a
# duration, easing out — quick away from the floor, slow to arrive. The
# duration is the DEFAULT for the document's effect_params["fade"].
_FADE_S = 0.4

# Consumption clamps (M4, brief F7 ranges). The command layer validates
# only type/finiteness, so a future preset reuses it unchanged; ranges
# are enforced here, where the params are consumed.
_SCALE_RANGE = (0.1, 10.0)
_SETTLE_MIN = 0.01              # shared floor for any authored duration
_SHIFT_RANGE = (-0.5, 0.5)


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def build_presets(floor: float,
                  params: Mapping[str, Mapping[str, object]] | None = None
                  ) -> dict[str, Effect]:
    """The registry as a function of the document's floor opacity and
    (M4) its sparse effect_params — still pure data (rule 6): the same
    named bundles of (property, Envelope) tracks, with `floor` as each
    opacity envelope's pre-trigger `initial`, pop's amplitude / settle /
    peak-offset / note-value read from ``params["pop"]`` and fade's
    duration / note-value from ``params["fade"]`` (both merged over
    defaults, clamped). Unknown presets and unknown keys are ignored
    here — they round-trip through the document untouched (the
    effect-name precedent)."""
    pop = dict(params.get("pop", {})) if params else {}
    scale = _clamp(float(pop.get("scale", _POP_SCALE)), *_SCALE_RANGE)
    settle = max(_SETTLE_MIN, float(pop.get("settle", _POP_SETTLE_S)))
    shift = _clamp(float(pop.get("peak_offset", 0.0)), *_SHIFT_RANGE)
    note_value = bool(pop.get("note_value", False))
    fade = dict(params.get("fade", {})) if params else {}
    fade_s = max(_SETTLE_MIN, float(fade.get("duration", _FADE_S)))
    fade_note_value = bool(fade.get("note_value", False))
    return {
        "appear": appear(floor),
        "pop": Effect("pop", {
            OPACITY: Envelope(initial=floor,
                              keyframes=(Keyframe(0.0, 1.0, Easing.STEP),)),
            SCALE: Envelope(initial=1.0,
                            keyframes=(Keyframe(0.0, scale,
                                                Easing.STEP),
                                       Keyframe(settle, 1.0,
                                                Easing.LINEAR))),
        }, trigger_shift=shift, settle_to_note_value=note_value),
        # Two keyframes: the ramp needs something to lerp from, and a
        # first keyframe is always STEP. It sits AT the floor, so the
        # note holds its ghost value through the onset and then rises.
        "fade": Effect("fade", {
            OPACITY: Envelope(initial=floor,
                              keyframes=(Keyframe(0.0, floor, Easing.STEP),
                                         Keyframe(fade_s, 1.0,
                                                  Easing.EASE_OUT))),
        }, settle_to_note_value=fade_note_value),
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
