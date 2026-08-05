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

from scoreanim.core.animation.effect import (GLOW, OFFSET_X, OFFSET_Y, OPACITY,
                                             SCALE, Easing, Effect, Envelope,
                                             Keyframe, appear)
from scoreanim.core.animation.glow import (GLOW_NOTE_VALUE, GLOW_S,
                                           glow_track, read_glow_shape)

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

# swell: the note is already on the page at its engraved size, grows to
# a peak and eases back down to where it started — a crescendo you can
# see. It is the first effect whose whole point is the note's LENGTH, so
# it is also the only one that stretches to the note value by default: a
# whole note swells across its bar, an eighth gives a quick breath.
# These four are the DEFAULTS for the document's effect_params["swell"].
_SWELL_SIZE = 1.4           # size at the top, in engraved sizes
_SWELL_PEAK = 0.5           # how far through the swell the top lands
_SWELL_S = 0.8              # authored length, used when note_value is off
_SWELL_NOTE_VALUE = True
_SWELL_FOLLOW = False

# With follow on the swell is a PLATEAU, not a hump: a quick ease up, a
# hold across the note, and a quick ease back to exactly 1.0 at the end.
# The held part is the size the recording's own loudness then plays on,
# and the tail is the snap-back that lands the note at its engraved size
# just as the next one arrives. Fractions of the window, not absolute
# seconds — the timescale stretches the whole shape at once, so a whole
# note's ease is proportionally the same as an eighth's. 10 / 75 / 15,
# Marcus 2026-08-01: 15 % is long enough that the return reads as a
# release rather than a flick on a fast note.
_FOLLOW_RISE = 0.10
_FOLLOW_FALL = 0.15

# glow: the note carries a soft coloured halo while it sounds. The
# shape of the light over time, and the colour and size of the halo,
# are both in core/animation/glow.py — the colour and radius because
# they are styling rather than animation, and render has to read them
# without the preset registry. The defaults are that module's
# GLOW_* constants.

# Consumption clamps (M4, brief F7 ranges). The command layer validates
# only type/finiteness, so a future preset reuses it unchanged; ranges
# are enforced here, where the params are consumed.
_SCALE_RANGE = (0.1, 10.0)
_SETTLE_MIN = 0.01              # shared floor for any authored duration
_SHIFT_RANGE = (-0.5, 0.5)
# Where a peak may sit inside its effect, as a fraction of the way
# through. Never at either end: the shape needs a rise AND a fall, and
# a keyframe exactly on top of another one is not an envelope.
_PEAK_RANGE = (0.05, 0.95)
# Scene units. The far end is about a page wide: past that the note
# starts from somewhere nobody is looking.
_DISTANCE_RANGE = (0.0, 2000.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def swell_scale(size: float, peak: float, seconds: float,
                follow: bool) -> Envelope:
    """The swell's size over time, in either of its two shapes.

    Both start and end at exactly 1.0 — the note is already on the page
    at its engraved size, and a played note is never left bigger than it
    was drawn.

    Authored: a hump. Up on EASE_IN, gentle away from rest and gathering
    pace the way a crescendo grows; down on EASE_OUT, quick away from
    the top and slow to arrive, so it settles back softly. `peak` says
    how far through the top lands.

    Following the recording: a plateau. A quick ease up, a hold, and a
    quick ease back. `peak` has no meaning in this shape — the top is
    not a point any more, it is the stretch the live volume plays on.
    Both eases are EASE_OUT, quick away and gentle arrival, so neither
    end of the hold has a corner in it."""
    if not follow:
        return Envelope(initial=1.0,
                        keyframes=(Keyframe(0.0, 1.0, Easing.STEP),
                                   Keyframe(peak * seconds, size,
                                            Easing.EASE_IN),
                                   Keyframe(seconds, 1.0, Easing.EASE_OUT)))
    return Envelope(initial=1.0,
                    keyframes=(Keyframe(0.0, 1.0, Easing.STEP),
                               Keyframe(_FOLLOW_RISE * seconds, size,
                                        Easing.EASE_OUT),
                               Keyframe((1.0 - _FOLLOW_FALL) * seconds, size,
                                        Easing.LINEAR),
                               Keyframe(seconds, 1.0, Easing.EASE_OUT)))


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
    duration / bounce from ``params["drop"]``, slide's direction /
    distance / duration / bounce from ``params["slide"]``, swell's
    size / peak / duration / note-value / follow from ``params["swell"]``
    and glow's duration / note-value plus its envelope shape from
    ``params["glow"]`` (all merged over defaults, clamped). The glow's
    colour, radius and density are NOT read here: they never reach an
    envelope, so render reads them straight from `glow.read_glow`.
    Follow is the one param that
    reaches past its own knob: it forces swell's note-value stretch on,
    because a fixed window cannot track a whole note. Unknown presets
    and unknown keys are ignored here — they round-trip through the
    document untouched (the effect-name precedent)."""
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
    swell = dict(params.get("swell", {})) if params else {}
    swell_size = _clamp(float(swell.get("size", _SWELL_SIZE)), *_SCALE_RANGE)
    swell_s = max(_SETTLE_MIN, float(swell.get("duration", _SWELL_S)))
    swell_peak = _clamp(float(swell.get("peak", _SWELL_PEAK)), *_PEAK_RANGE)
    swell_follow = bool(swell.get("follow", _SWELL_FOLLOW))
    # Following the recording only works over the note's own length: a
    # fixed 0.8 s window cannot track a whole note. So follow turns the
    # note-value stretch on whatever the other box says, and the panel
    # shows that box checked and grayed to match.
    swell_note_value = swell_follow or bool(
        swell.get("note_value", _SWELL_NOTE_VALUE))
    glow = dict(params.get("glow", {})) if params else {}
    # The shape's own six params read and clamp next door, where the
    # ordering the Envelope demands is enforced with them.
    glow_shape = read_glow_shape(glow)
    glow_s = max(_SETTLE_MIN, float(glow.get("duration", GLOW_S)))
    glow_note_value = bool(glow.get("note_value", GLOW_NOTE_VALUE))
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
        # The note appears at its engraved size and stays there — it is
        # already on the page, so the step at the trigger is opacity's
        # alone and scale steps to 1.0, which is also what the rise has
        # to lerp from. The size track has two shapes, the authored hump
        # and the plateau the recording plays on (swell_scale above).
        # With the note value on, the timescale stretches whichever
        # shape it is all at once, so it keeps its proportions inside
        # the note however long the note is.
        "swell": Effect("swell", {
            OPACITY: Envelope(initial=floor,
                              keyframes=(Keyframe(0.0, 1.0, Easing.STEP),)),
            SCALE: swell_scale(swell_size, swell_peak, swell_s, swell_follow),
        }, settle_to_note_value=swell_note_value,
            follow_volume=swell_follow),
        # The note appears at the trigger the way appear's does — so
        # "glow" on its own still reveals it — and lights a halo that
        # dies again on the same clock. The note value is ON by default:
        # a glow that goes out exactly when the note's value ends is
        # what makes only the SOUNDING notes glow, which is the point of
        # the effect. Scale is untouched, so glow combines with pop and
        # with swell without either of them noticing.
        "glow": Effect("glow", {
            OPACITY: Envelope(initial=floor,
                              keyframes=(Keyframe(0.0, 1.0, Easing.STEP),)),
            # Amount 1.0: the envelope's own levels ARE the brightness
            # now, and the halo's opacity is its value and nothing else.
            GLOW: glow_track(glow_shape, 1.0, glow_s),
        }, settle_to_note_value=glow_note_value),
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


# A combined effect is a NAME: its parts joined by this. The document
# stores one string either way, so a combination round-trips like any
# other name and needs no schema change.
COMBINE_SEP = "+"


def split_effect_name(name: str | None) -> tuple[str, ...]:
    """The parts of a stored effect name, in order and without repeats.
    A plain name is a one-part name."""
    if not name:
        return ()
    seen: list[str] = []
    for part in name.split(COMBINE_SEP):
        part = part.strip()
        if part and part not in seen:
            seen.append(part)
    return tuple(seen)


def effects_for(name: str | None,
                presets: Mapping[str, Effect] = PRESETS
                ) -> tuple[Effect, ...]:
    """Resolve a stored effect name into the effects that run together.
    A part this build does not know is SKIPPED and the rest kept, so an
    old build opening "drop+shimmer" still drops; if nothing at all
    resolves, the default preset stands in, as it does for any unknown
    name."""
    found = tuple(presets[part] for part in split_effect_name(name)
                  if part in presets)
    return found if found else (presets[DEFAULT_EFFECT],)
