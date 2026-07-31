"""The effect preset registry (rule 6: effects are data, not code).

Adding an effect means adding an entry HERE — nothing in the evaluator
(core/animation/effect.py, state.py) or the render applier changes.
The registry drives the UI (the effect menu enumerates it) and the
StyleRules resolution (names in the doc resolve here, unknown names
fail soft to the default so an old build opening a newer project
degrades instead of crashing).
"""
from __future__ import annotations

import math

from scoreanim.core.animation.effect import (OFFSET_X, OFFSET_Y, OPACITY,
                                             SCALE, Easing, Effect, Envelope,
                                             Keyframe, appear)

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

# drop: the note falls onto the page from the viewer's side. It arrives
# oversized and washed out, then shrinks and solidifies onto its place,
# like a stamp landing. Both tracks run over the same time. These three
# are the DEFAULTS for the document's effect_params["drop"].
_DROP_SIZE = 3.0        # how big the note starts, in engraved sizes
_DROP_S = 0.35
_DROP_BOUNCE = True     # a small settle as it lands
# How solid the note is the moment it enters, before it closes the last
# of the distance. Never dimmer than the ghost it grew out of, so a
# document with a high floor does not make its notes dip at the onset.
_DROP_ARRIVAL = 0.3

# slide: the note travels in to its place across the page, from a
# direction the user picks. These four are the DEFAULTS for the
# document's effect_params["slide"].
_SLIDE_DIRECTION = 0.0  # degrees; where the note comes FROM, 0 = above
_SLIDE_S = 0.35
_SLIDE_BOUNCE = False   # a small settle as it arrives
# How far out it starts, in scene units. Measured on testdata/testscore:
# a staff is 72 units tall (18 to a staff space), staff sits 200 below
# staff, so the clear gap between two staves is about 128, on a page
# 2096 × 2967. 120 starts the note just outside its own staff and inside
# that gap: the travel plainly reads as coming in from off the staff,
# and on a many-staff score the incoming ink still does not land on the
# part above. Rendered and looked at, 2026-07-31 — at 200 the note
# arrives sitting in the middle of the staff above.
_SLIDE_DISTANCE = 120.0

# Consumption clamps (M4, brief F7 ranges). The command layer validates
# only type/finiteness, so a future preset reuses it unchanged; ranges
# are enforced here, where the params are consumed.
_SCALE_RANGE = (0.1, 10.0)
_SETTLE_MIN = 0.01              # shared floor for any authored duration
_SHIFT_RANGE = (-0.5, 0.5)
# Scene units. The far end is about a page wide: past that the note
# starts from somewhere nobody is looking.
_DISTANCE_RANGE = (0.0, 2000.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def slide_start(direction_degrees: float, distance: float
                ) -> tuple[float, float]:
    """Where a sliding note starts, as an (x, y) offset from its
    engraved place. The direction says where it comes FROM: 0 = from
    above, 90 = from the right, 180 = from below, 270 = from the left,
    turning clockwise. Scene y grows downward, so "from above" is a
    negative y."""
    radians = math.radians(direction_degrees)
    return (distance * math.sin(radians), -distance * math.cos(radians))


def build_presets(floor: float,
                  params: Mapping[str, Mapping[str, object]] | None = None
                  ) -> dict[str, Effect]:
    """The registry as a function of the document's floor opacity and
    (M4) its sparse effect_params — still pure data (rule 6): the same
    named bundles of (property, Envelope) tracks, with `floor` as each
    opacity envelope's pre-trigger `initial`, pop's amplitude / settle /
    peak-offset / note-value read from ``params["pop"]``, fade's
    duration / note-value from ``params["fade"]``, drop's start size /
    duration / bounce from ``params["drop"]`` and slide's direction /
    distance / duration / bounce from ``params["slide"]`` (all merged
    over defaults, clamped). Unknown presets and unknown keys are ignored
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
    drop = dict(params.get("drop", {})) if params else {}
    drop_size = _clamp(float(drop.get("start_size", _DROP_SIZE)),
                       *_SCALE_RANGE)
    drop_s = max(_SETTLE_MIN, float(drop.get("duration", _DROP_S)))
    # The bounce is a choice of CURVE, made here in the data — the
    # evaluator still knows nothing about any effect's name.
    drop_curve = (Easing.EASE_OUT_BOUNCE
                  if bool(drop.get("bounce", _DROP_BOUNCE))
                  else Easing.EASE_OUT)
    slide = dict(params.get("slide", {})) if params else {}
    slide_s = max(_SETTLE_MIN, float(slide.get("duration", _SLIDE_S)))
    slide_curve = (Easing.EASE_OUT_BOUNCE
                   if bool(slide.get("bounce", _SLIDE_BOUNCE))
                   else Easing.EASE_OUT)
    # The angle becomes two track values HERE, once per document change.
    # That is still data — the evaluator only ever sees two ordinary
    # envelopes and never hears the word "direction".
    start_x, start_y = slide_start(
        float(slide.get("direction", _SLIDE_DIRECTION)),
        _clamp(float(slide.get("distance", _SLIDE_DISTANCE)),
               *_DISTANCE_RANGE))
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
        # Both tracks step at the trigger and then run to their resting
        # value over the same time: the note enters big and washed out
        # and closes the distance to the page. Scale starts from 1.0 —
        # the ghost sits at its engraved size, and only the note that
        # has arrived is ever oversized.
        "drop": Effect("drop", {
            OPACITY: Envelope(initial=floor,
                              keyframes=(Keyframe(0.0,
                                                  max(floor, _DROP_ARRIVAL),
                                                  Easing.STEP),
                                         Keyframe(drop_s, 1.0,
                                                  Easing.EASE_OUT))),
            SCALE: Envelope(initial=1.0,
                            keyframes=(Keyframe(0.0, drop_size, Easing.STEP),
                                       Keyframe(drop_s, 1.0, drop_curve))),
        }),
        # The note appears at the trigger the way appear's does, and
        # travels in to its place from `distance` away in the direction
        # asked for. Both offsets start at 0 — the ghost waits in the
        # place the note will end up, and only the note that has arrived
        # is ever away from it.
        "slide": Effect("slide", {
            OPACITY: Envelope(initial=floor,
                              keyframes=(Keyframe(0.0, 1.0, Easing.STEP),)),
            OFFSET_X: Envelope(initial=0.0,
                               keyframes=(Keyframe(0.0, start_x, Easing.STEP),
                                          Keyframe(slide_s, 0.0,
                                                   slide_curve))),
            OFFSET_Y: Envelope(initial=0.0,
                               keyframes=(Keyframe(0.0, start_y, Easing.STEP),
                                          Keyframe(slide_s, 0.0,
                                                   slide_curve))),
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
