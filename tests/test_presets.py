"""The pop preset (PHASES 5.4): proving effects-as-data — this preset
plus this test are the ENTIRE diff for adding an effect. Zero changes in
the evaluator (core/animation/effect.py, state.py), the applier, or the
UI (the effect menu enumerates the registry)."""
from __future__ import annotations

import pytest

from scoreanim.core.animation import (DEFAULT_EFFECT, OFFSET_X, OFFSET_Y,
                                      OPACITY, PRESETS, SCALE, build_presets,
                                      derive_windows, effect_for, effects_for,
                                      element_state, split_effect_name,
                                      FLOOR_OPACITY)
from scoreanim.core.animation.presets import slide_start
from scoreanim.core.timing import TempoEvent, TempoMap

# 60 bpm, so a duration in beats is the same number in seconds and the
# swell's stretch reads straight off (the test_windows.py convention).
_SWELL_TEMPO = TempoMap([TempoEvent(0.0, 60.0)])


def test_pop_is_registered() -> None:
    assert "pop" in PRESETS
    assert PRESETS["pop"].duration == pytest.approx(0.25)


def test_registry_is_a_function_of_the_floor() -> None:
    """Phase 7.2: presets stay data, parameterized by the document
    floor. Floor 0 is a value — fully invisible before the trigger —
    and the default registry equals build_presets(default)."""
    assert PRESETS == build_presets(FLOOR_OPACITY)
    zero = build_presets(0.0)
    assert set(zero) == set(PRESETS)
    for name in ("appear", "pop"):
        before = element_state(10.0, zero[name], 9.9)
        assert before[OPACITY] == 0.0
        assert element_state(10.0, zero[name], 10.0)[OPACITY] == 1.0
    # scale is not the floor's business: pop still bumps to 1.25
    assert element_state(10.0, zero["pop"], 10.0)[SCALE] == 1.25


def test_effect_for_resolves_against_a_given_registry() -> None:
    half = build_presets(0.5)
    assert effect_for("pop", half) is half["pop"]
    assert effect_for("no-such-effect", half) is half["appear"]
    assert effect_for(None, half) is half["appear"]
    assert effect_for("pop") is PRESETS["pop"]      # default registry


def test_pop_exact_values_through_the_unchanged_evaluator() -> None:
    pop = PRESETS["pop"]
    before = element_state(10.0, pop, 9.9)
    assert before == {OPACITY: FLOOR_OPACITY, SCALE: 1.0}
    at_onset = element_state(10.0, pop, 10.0)
    assert at_onset == {OPACITY: 1.0, SCALE: 1.25}
    mid = element_state(10.0, pop, 10.125)
    assert mid[OPACITY] == 1.0
    assert mid[SCALE] == pytest.approx(1.125)
    settled = element_state(10.0, pop, 10.25)
    assert settled == {OPACITY: 1.0, SCALE: 1.0}
    long_after = element_state(10.0, pop, 99.0)
    assert long_after == {OPACITY: 1.0, SCALE: 1.0}


# --- M4.3: parameterized pop + the timescale/shift kernel -------------------

def test_amplitude_and_settle_land_in_the_envelope() -> None:
    pop = build_presets(0.3, {"pop": {"scale": 2.0, "settle": 0.5}})["pop"]
    assert element_state(0.0, pop, 0.0)[SCALE] == 2.0
    assert pop.duration == pytest.approx(0.5)
    assert element_state(0.0, pop, 0.25)[SCALE] == pytest.approx(1.5)


def test_peak_offset_lands_in_trigger_shift() -> None:
    pop = build_presets(0.3, {"pop": {"peak_offset": -0.1}})["pop"]
    assert pop.trigger_shift == -0.1
    # shift never changes the effect's own duration
    assert pop.duration == pytest.approx(0.25)
    # the WHOLE effect moves early (F3): at −100 ms the note is visible
    # AND peaked 100 ms before its trigger
    early = element_state(10.0, pop, 9.9)
    assert early[OPACITY] == 1.0
    assert early[SCALE] == pytest.approx(1.25)
    assert element_state(10.0, pop, 9.85)[OPACITY] == 0.3


def test_note_value_lands_in_settle_to_note_value() -> None:
    assert PRESETS["pop"].settle_to_note_value is False
    pop = build_presets(0.3, {"pop": {"note_value": True}})["pop"]
    assert pop.settle_to_note_value is True


def test_unknown_params_and_presets_are_ignored() -> None:
    reg = build_presets(0.3, {"pop": {"sparkle": 99}, "shimmer": {"x": 1}})
    assert reg == build_presets(0.3)
    assert set(reg) == {"appear", "drop", "fade", "pop", "slide", "swell"}


def test_consumption_clamps() -> None:
    pop = build_presets(0.3, {"pop": {"scale": 99.0, "settle": 0.0,
                                      "peak_offset": 5.0}})["pop"]
    assert pop.trigger_shift == 0.5                     # ±0.5 s range
    assert pop.duration == pytest.approx(0.01)          # settle floor
    assert element_state(0.0, pop, 0.5)[SCALE] == 10.0  # scale ceiling


# --- fade: the same proof again, with no evaluator change ------------------

def test_fade_is_registered() -> None:
    assert "fade" in PRESETS
    assert PRESETS["fade"].duration == pytest.approx(0.4)


def test_fade_exact_values_through_the_unchanged_evaluator() -> None:
    fade = PRESETS["fade"]
    # the floor holds up to and AT the onset, then the ramp starts
    assert element_state(10.0, fade, 9.9)[OPACITY] == FLOOR_OPACITY
    assert element_state(10.0, fade, 10.0)[OPACITY] == FLOOR_OPACITY
    assert element_state(10.0, fade, 10.4)[OPACITY] == 1.0
    assert element_state(10.0, fade, 99.0)[OPACITY] == 1.0
    # ease-out: halfway through the time is most of the way to full,
    # well past the straight line's 0.65
    half = element_state(10.0, fade, 10.2)[OPACITY]
    assert half == pytest.approx(FLOOR_OPACITY + 0.875 * (1.0 - FLOOR_OPACITY))
    assert half > 0.65
    # fade owns opacity only — no scale track to apply
    assert set(fade.tracks) == {OPACITY}


def test_fade_tracks_the_document_floor() -> None:
    dark = build_presets(0.0)["fade"]
    assert element_state(10.0, dark, 10.0)[OPACITY] == 0.0
    assert element_state(10.0, dark, 10.2)[OPACITY] == pytest.approx(0.875)
    assert element_state(10.0, dark, 10.4)[OPACITY] == 1.0


def test_fade_duration_lands_in_the_envelope() -> None:
    fade = build_presets(0.3, {"fade": {"duration": 1.0}})["fade"]
    assert fade.duration == pytest.approx(1.0)
    assert element_state(0.0, fade, 0.5)[OPACITY] == \
        pytest.approx(0.3 + 0.875 * 0.7)
    assert element_state(0.0, fade, 1.0)[OPACITY] == 1.0


def test_fade_duration_is_clamped() -> None:
    assert build_presets(0.3, {"fade": {"duration": 0.0}})["fade"].duration \
        == pytest.approx(0.01)


def test_fade_note_value_lands_in_settle_to_note_value() -> None:
    assert PRESETS["fade"].settle_to_note_value is False
    fade = build_presets(0.3, {"fade": {"note_value": True}})["fade"]
    assert fade.settle_to_note_value is True
    # the stretch is the applier's generic timescale, not a fade branch:
    # at timescale 2 the ramp takes twice as long
    assert element_state(0.0, fade, 0.4, timescale=2.0)[OPACITY] == \
        pytest.approx(element_state(0.0, fade, 0.2)[OPACITY])
    assert element_state(0.0, fade, 0.8, timescale=2.0)[OPACITY] == 1.0


def test_fade_params_do_not_disturb_pop() -> None:
    reg = build_presets(0.3, {"fade": {"duration": 2.0}})
    assert reg["pop"] == PRESETS["pop"]


# --- drop: a third effect, again with no evaluator change ------------------

def test_drop_is_registered() -> None:
    assert "drop" in PRESETS
    assert PRESETS["drop"].duration == pytest.approx(0.35)
    # opacity and scale, both existing properties
    assert set(PRESETS["drop"].tracks) == {OPACITY, SCALE}


def test_drop_exact_values_through_the_unchanged_evaluator() -> None:
    drop = PRESETS["drop"]
    # before the trigger: the ghost, at its engraved size
    before = element_state(10.0, drop, 9.9)
    assert before == {OPACITY: FLOOR_OPACITY, SCALE: 1.0}
    # at the trigger the note enters: oversized and part-way solid
    at_onset = element_state(10.0, drop, 10.0)
    assert at_onset == {OPACITY: 0.3, SCALE: 3.0}
    # halfway through, opacity is most of the way up (ease-out)
    assert element_state(10.0, drop, 10.175)[OPACITY] == \
        pytest.approx(0.3 + 0.875 * 0.7)
    # it lands on its size and stays there — exactly, once the window is
    # over, which is what keeps a played note from sitting oversized
    landed = element_state(10.0, drop, 10.35)
    assert landed[OPACITY] == pytest.approx(1.0)
    assert landed[SCALE] == pytest.approx(1.0)
    assert element_state(10.0, drop, 10.36) == {OPACITY: 1.0, SCALE: 1.0}
    assert element_state(10.0, drop, 99.0) == {OPACITY: 1.0, SCALE: 1.0}


def test_drop_bounces_on_the_way_down() -> None:
    """The bounce touches the engraved size early, springs back up and
    settles — the little squash of a stamp landing."""
    drop = PRESETS["drop"]
    first_landing = element_state(10.0, drop, 10.0 + 0.35 / 2.75)[SCALE]
    assert first_landing == pytest.approx(1.0)
    bounce = element_state(10.0, drop, 10.0 + 0.35 * 1.5 / 2.75)[SCALE]
    assert bounce == pytest.approx(1.5)          # back up, three quarters
    assert bounce > first_landing


def test_drop_without_bounce_eases_straight_down() -> None:
    plain = build_presets(0.3, {"drop": {"bounce": False}})["drop"]
    at = 10.0 + 0.35 / 2.75
    assert element_state(10.0, plain, at)[SCALE] == \
        pytest.approx(3.0 - 2.0 * (1.0 - (1.0 - 1.0 / 2.75) ** 3))
    assert element_state(10.0, plain, at)[SCALE] != \
        pytest.approx(element_state(10.0, PRESETS["drop"], at)[SCALE])
    # either way it lands on its size, exactly
    assert element_state(10.0, plain, 10.35)[SCALE] == 1.0


def test_drop_params_land_in_the_envelopes() -> None:
    drop = build_presets(0.3, {"drop": {"start_size": 5.0,
                                        "duration": 1.0}})["drop"]
    assert drop.duration == pytest.approx(1.0)
    assert element_state(0.0, drop, 0.0)[SCALE] == 5.0
    assert element_state(0.0, drop, 1.0) == {OPACITY: 1.0, SCALE: 1.0}


def test_drop_params_are_clamped() -> None:
    drop = build_presets(0.3, {"drop": {"start_size": 99.0,
                                        "duration": 0.0}})["drop"]
    assert element_state(0.0, drop, 0.0)[SCALE] == 10.0   # scale ceiling
    assert drop.duration == pytest.approx(0.01)           # duration floor


def test_drop_never_dips_below_the_document_floor() -> None:
    """The note enters at 0.3 solid — but never dimmer than the ghost it
    grew out of, so a bright floor does not make it dip at the onset."""
    dark = build_presets(0.0)["drop"]
    assert element_state(10.0, dark, 9.9)[OPACITY] == 0.0
    assert element_state(10.0, dark, 10.0)[OPACITY] == 0.3
    bright = build_presets(0.6)["drop"]
    assert element_state(10.0, bright, 10.0)[OPACITY] == 0.6
    assert element_state(10.0, bright, 10.35)[OPACITY] == 1.0


def test_drop_params_do_not_disturb_pop_or_fade() -> None:
    reg = build_presets(0.3, {"drop": {"start_size": 8.0}})
    assert reg["pop"] == PRESETS["pop"]
    assert reg["fade"] == PRESETS["fade"]


def test_drop_has_no_note_value_or_shift() -> None:
    """Its two knobs are the size and the time; nothing else moves."""
    assert PRESETS["drop"].settle_to_note_value is False
    assert PRESETS["drop"].trigger_shift == 0.0


# --- slide: two NEW properties, and still no evaluator change --------------

_EASE_OUT = (lambda f: 1.0 - (1.0 - f) ** 3)


def test_slide_is_registered() -> None:
    assert "slide" in PRESETS
    assert PRESETS["slide"].duration == pytest.approx(0.35)
    assert set(PRESETS["slide"].tracks) == {OPACITY, OFFSET_X, OFFSET_Y}


def test_direction_decomposes_into_the_two_tracks() -> None:
    """Where the note comes FROM, clockwise from straight above. Scene y
    grows downward, so above is negative."""
    assert slide_start(0.0, 100.0) == pytest.approx((0.0, -100.0))
    assert slide_start(90.0, 100.0) == pytest.approx((100.0, 0.0))
    assert slide_start(180.0, 100.0) == pytest.approx((0.0, 100.0))
    assert slide_start(270.0, 100.0) == pytest.approx((-100.0, 0.0))
    diagonal = 100.0 / (2 ** 0.5)
    assert slide_start(45.0, 100.0) == pytest.approx((diagonal, -diagonal))
    assert slide_start(225.0, 100.0) == pytest.approx((-diagonal, diagonal))
    # the trip is `distance` long whichever way it points
    for degrees in (0.0, 17.0, 90.0, 123.5, 200.0, 359.0):
        x, y = slide_start(degrees, 200.0)
        assert (x * x + y * y) ** 0.5 == pytest.approx(200.0)


def test_slide_exact_values_through_the_unchanged_evaluator() -> None:
    """The default: in from 120 units above, over 0.35 s, easing out."""
    slide = PRESETS["slide"]
    # before the trigger: a ghost, waiting in the place the note ends up
    assert element_state(10.0, slide, 9.9) == {OPACITY: FLOOR_OPACITY,
                                               OFFSET_X: 0.0, OFFSET_Y: 0.0}
    # at the trigger it appears, out at its starting distance
    at_onset = element_state(10.0, slide, 10.0)
    assert at_onset == {OPACITY: 1.0, OFFSET_X: 0.0, OFFSET_Y: -120.0}
    # halfway through the time, most of the way home (ease-out)
    mid = element_state(10.0, slide, 10.175)
    assert mid[OFFSET_Y] == pytest.approx(-120.0 * (1.0 - _EASE_OUT(0.5)))
    assert mid[OFFSET_Y] == pytest.approx(-15.0)
    # and it lands exactly in place, and stays there
    landed = element_state(10.0, slide, 10.35)
    assert landed == {OPACITY: 1.0, OFFSET_X: 0.0, OFFSET_Y: 0.0}
    assert element_state(10.0, slide, 99.0) == {OPACITY: 1.0,
                                                OFFSET_X: 0.0, OFFSET_Y: 0.0}


def test_slide_direction_and_distance_land_in_the_envelopes() -> None:
    slide = build_presets(0.3, {"slide": {"direction": 270.0,
                                          "distance": 400.0}})["slide"]
    at_onset = element_state(0.0, slide, 0.0)
    assert at_onset[OFFSET_X] == pytest.approx(-400.0)   # from the left
    assert at_onset[OFFSET_Y] == pytest.approx(0.0)
    assert element_state(0.0, slide, 0.35) == pytest.approx(
        {OPACITY: 1.0, OFFSET_X: 0.0, OFFSET_Y: 0.0})


def test_slide_duration_lands_in_the_envelopes() -> None:
    slide = build_presets(0.3, {"slide": {"duration": 1.0}})["slide"]
    assert slide.duration == pytest.approx(1.0)
    # still travelling where the default would long since have landed
    assert element_state(0.0, slide, 0.5)[OFFSET_Y] == \
        pytest.approx(-120.0 * (1.0 - _EASE_OUT(0.5)))
    assert element_state(0.0, slide, 1.0)[OFFSET_Y] == 0.0


def test_slide_bounces_on_arrival_when_asked() -> None:
    """The same piecewise bounce drop uses: it reaches the note's place
    early, springs back part of the way, and settles — exactly in
    place."""
    plain = PRESETS["slide"]
    bouncy = build_presets(FLOOR_OPACITY, {"slide": {"bounce": True}})["slide"]
    first_landing = element_state(10.0, bouncy, 10.0 + 0.35 / 2.75)
    assert first_landing[OFFSET_Y] == pytest.approx(0.0)
    back_up = element_state(10.0, bouncy, 10.0 + 0.35 * 1.5 / 2.75)
    assert back_up[OFFSET_Y] == pytest.approx(-120.0 * 0.25)
    assert plain != bouncy
    # and it comes to rest in place, exactly, once the window is over
    assert element_state(10.0, bouncy, 10.36)[OFFSET_Y] == 0.0


def test_slide_params_are_clamped() -> None:
    slide = build_presets(0.3, {"slide": {"distance": 1e9,
                                          "duration": 0.0}})["slide"]
    assert slide.duration == pytest.approx(0.01)          # duration floor
    assert element_state(0.0, slide, 0.0)[OFFSET_Y] == -2000.0   # distance cap
    close = build_presets(0.3, {"slide": {"distance": -50.0}})["slide"]
    assert element_state(0.0, close, 0.0)[OFFSET_Y] == 0.0       # never < 0


def test_slide_tracks_the_document_floor() -> None:
    dark = build_presets(0.0)["slide"]
    assert element_state(10.0, dark, 9.9)[OPACITY] == 0.0
    assert element_state(10.0, dark, 10.0)[OPACITY] == 1.0


def test_slide_has_no_note_value_or_shift() -> None:
    assert PRESETS["slide"].settle_to_note_value is False
    assert PRESETS["slide"].trigger_shift == 0.0


def test_slide_params_do_not_disturb_the_other_presets() -> None:
    reg = build_presets(0.3, {"slide": {"distance": 800.0}})
    for name in ("appear", "pop", "fade", "drop", "swell"):
        assert reg[name] == PRESETS[name]


# --- swell: the first effect timed to the note's own length ---------------

def test_swell_is_registered() -> None:
    assert "swell" in PRESETS
    assert PRESETS["swell"].duration == pytest.approx(0.8)
    # opacity and scale, both existing properties
    assert set(PRESETS["swell"].tracks) == {OPACITY, SCALE}


def test_swell_exact_values_through_the_unchanged_evaluator() -> None:
    swell = PRESETS["swell"]
    # before the trigger: the ghost, at its engraved size
    assert element_state(10.0, swell, 9.9) == {OPACITY: FLOOR_OPACITY,
                                               SCALE: 1.0}
    # at the trigger the note is simply there — the growth starts FROM
    # its engraved size, so nothing jumps
    assert element_state(10.0, swell, 10.0) == {OPACITY: 1.0, SCALE: 1.0}
    # a quarter of the way up, the rise is still gentle (ease-in)
    quarter = element_state(10.0, swell, 10.1)[SCALE]
    assert quarter == pytest.approx(1.0 + 0.4 * 0.25 ** 3)
    assert quarter < 1.05
    # the top, halfway through
    assert element_state(10.0, swell, 10.4)[SCALE] == pytest.approx(1.4)
    # and back to its engraved size, exactly, and there it stays
    assert element_state(10.0, swell, 10.8) == {OPACITY: 1.0, SCALE: 1.0}
    assert element_state(10.0, swell, 99.0) == {OPACITY: 1.0, SCALE: 1.0}


def test_swell_peak_lands_where_the_params_say() -> None:
    """Both halves of the shape: the top is the size asked for, and it
    sits at the fraction of the way through asked for."""
    early = build_presets(0.3, {"swell": {"peak": 0.25, "size": 2.0,
                                          "duration": 1.0}})["swell"]
    assert element_state(0.0, early, 0.25)[SCALE] == pytest.approx(2.0)
    # sampled across the whole shape, nothing beats the top and nothing
    # else sits on it
    values = [element_state(0.0, early, i / 100.0)[SCALE]
              for i in range(101)]
    assert max(values) == pytest.approx(2.0)
    assert values.index(max(values)) == 25
    # rising into it, falling out of it
    assert values[10] < values[20] < values[25]
    assert values[25] > values[40] > values[80]


def test_swell_ends_exactly_at_the_engraved_size() -> None:
    """Whatever the size and wherever the top, a played note is left the
    size it was drawn — no note is ever stranded big."""
    for size, peak in ((1.1, 0.05), (2.5, 0.5), (8.0, 0.95)):
        swell = build_presets(0.3, {"swell": {"size": size, "peak": peak,
                                              "duration": 1.0}})["swell"]
        assert element_state(0.0, swell, 1.0)[SCALE] == 1.0
        assert element_state(0.0, swell, 1.5)[SCALE] == 1.0


def test_swell_settles_to_the_note_value_by_default() -> None:
    """The one effect that is ON by default: its whole point is the
    note's length."""
    assert PRESETS["swell"].settle_to_note_value is True
    off = build_presets(0.3, {"swell": {"note_value": False}})["swell"]
    assert off.settle_to_note_value is False


def test_swell_note_value_off_falls_back_to_the_authored_duration() -> None:
    """With the flag off the stretch seam parks at 1.0, so every note
    swells over the authored 0.8 s. With it on, a 4-beat note at 60 bpm
    takes the whole 4 s — and because the stretch is uniform, the top
    stays halfway through."""
    off = build_presets(0.3, {"swell": {"note_value": False}})["swell"]
    plain = derive_windows([0.0], [0.0], [["whole"]], [[(off,)]],
                           {"whole": 4.0}, _SWELL_TEMPO)
    assert plain.timescales_per_trigger[0][0][0] == 1.0
    assert plain.durations[0] == pytest.approx(0.8)
    assert element_state(0.0, off, 0.4)[SCALE] == pytest.approx(1.4)

    on = PRESETS["swell"]
    stretched = derive_windows([0.0], [0.0], [["whole"]], [[(on,)]],
                               {"whole": 4.0}, _SWELL_TEMPO)
    timescale = stretched.timescales_per_trigger[0][0][0]
    assert timescale == pytest.approx(5.0)          # 4 s over 0.8 s
    assert stretched.durations[0] == pytest.approx(4.0)
    assert element_state(0.0, on, 2.0, timescale=timescale)[SCALE] == \
        pytest.approx(1.4)
    assert element_state(0.0, on, 4.0, timescale=timescale)[SCALE] == 1.0


def test_swell_params_are_clamped() -> None:
    big = build_presets(0.3, {"swell": {"size": 99.0, "duration": 0.0}})
    assert element_state(0.0, big["swell"], 0.005)[SCALE] == 10.0
    assert big["swell"].duration == pytest.approx(0.01)   # duration floor
    # a top at either end is no shape at all, so both ends are held off
    late = build_presets(0.3, {"swell": {"peak": 5.0, "duration": 1.0}})
    assert element_state(0.0, late["swell"], 0.95)[SCALE] == \
        pytest.approx(1.4)
    early = build_presets(0.3, {"swell": {"peak": -1.0, "duration": 1.0}})
    assert element_state(0.0, early["swell"], 0.05)[SCALE] == \
        pytest.approx(1.4)


def test_swell_tracks_the_document_floor() -> None:
    dark = build_presets(0.0)["swell"]
    assert element_state(10.0, dark, 9.9)[OPACITY] == 0.0
    assert element_state(10.0, dark, 10.0)[OPACITY] == 1.0
    bright = build_presets(0.6)["swell"]
    assert element_state(10.0, bright, 9.9)[OPACITY] == 0.6


def test_swell_has_no_shift() -> None:
    assert PRESETS["swell"].trigger_shift == 0.0


# --- swell following the recording ----------------------------------------

def test_follow_is_off_by_default() -> None:
    """Nothing anyone has saved changes shape."""
    assert PRESETS["swell"].follow_volume is False
    assert build_presets(0.3, {"swell": {"size": 2.0}})["swell"] \
        .follow_volume is False


def test_follow_turns_the_hump_into_a_plateau() -> None:
    """A quick ease up, a hold the live volume plays on, and a quick
    ease back — not a point at the top."""
    swell = build_presets(0.3, {"swell": {"follow": True, "size": 2.0,
                                          "duration": 1.0}})["swell"]
    at = lambda t: element_state(0.0, swell, t)[SCALE]     # noqa: E731
    assert at(0.0) == 1.0                       # starts where it was drawn
    # up over the first 10 %, held from there to 85 %
    assert at(0.10) == pytest.approx(2.0)
    for t in (0.10, 0.25, 0.5, 0.7, 0.85):
        assert at(t) == pytest.approx(2.0), t
    # nothing ever goes past the size asked for
    values = [at(i / 200.0) for i in range(201)]
    assert max(values) == pytest.approx(2.0)
    # and the top is a stretch, not a spike: most of the note sits on it
    assert sum(v == pytest.approx(2.0) for v in values) > 140
    # the tail eases back, and the fall is monotone
    tail = [at(0.85 + i / 300.0) for i in range(46)]
    assert all(b <= a + 1e-9 for a, b in zip(tail, tail[1:]))
    assert 1.0 < at(0.95) < 2.0


def test_follow_ends_exactly_at_the_engraved_size() -> None:
    """The whole point of the tail: the note lands where it was drawn,
    in time for the next one, whatever size it was held at."""
    for size in (1.05, 1.4, 3.0, 10.0):
        swell = build_presets(0.3, {"swell": {"follow": True, "size": size,
                                              "duration": 2.0}})["swell"]
        assert element_state(0.0, swell, 2.0)[SCALE] == 1.0
        assert element_state(0.0, swell, 5.0)[SCALE] == 1.0


def test_follow_forces_the_note_value_stretch_on() -> None:
    """A fixed 0.8 s window cannot track a whole note, so follow turns
    the stretch on however the other box is set."""
    forced = build_presets(0.3, {"swell": {"follow": True,
                                           "note_value": False}})["swell"]
    assert forced.follow_volume is True
    assert forced.settle_to_note_value is True
    # and the plateau keeps its proportions inside a long note
    stretched = derive_windows([0.0], [0.0], [["whole"]], [[(forced,)]],
                               {"whole": 4.0}, _SWELL_TEMPO)
    timescale = stretched.timescales_per_trigger[0][0][0]
    assert timescale == pytest.approx(5.0)          # 4 s over 0.8 s
    assert stretched.durations[0] == pytest.approx(4.0)
    held = element_state(0.0, forced, 2.0, timescale=timescale)[SCALE]
    assert held == pytest.approx(1.4)               # still on the plateau
    assert element_state(0.0, forced, 4.0, timescale=timescale)[SCALE] == 1.0


def test_the_peak_knob_is_ignored_while_following() -> None:
    """The top is no longer a point, so where it sits means nothing."""
    shapes = [build_presets(0.3, {"swell": {"follow": True, "peak": peak,
                                            "duration": 1.0}})["swell"]
              for peak in (0.05, 0.5, 0.95)]
    assert shapes[0] == shapes[1] == shapes[2]


def test_follow_does_not_disturb_the_other_presets() -> None:
    reg = build_presets(0.3, {"swell": {"follow": True}})
    for name in ("appear", "pop", "fade", "drop", "slide"):
        assert reg[name] == PRESETS[name]


def test_swell_params_do_not_disturb_the_other_presets() -> None:
    reg = build_presets(0.3, {"swell": {"size": 3.0}})
    for name in ("appear", "pop", "fade", "drop", "slide"):
        assert reg[name] == PRESETS[name]


def test_timescale_divides_the_evaluated_t_rel() -> None:
    pop = PRESETS["pop"]
    # timescale=2 halves the evaluated t_rel: at +0.25 s the stretch is
    # only halfway through its settle, and it lands at +0.5 s
    assert element_state(0.0, pop, 0.25, timescale=2.0)[SCALE] == \
        pytest.approx(element_state(0.0, pop, 0.125)[SCALE])
    assert element_state(0.0, pop, 0.5, timescale=2.0)[SCALE] == 1.0
    # shift is applied BEFORE the division: absolute seconds either way
    shifted = build_presets(0.3, {"pop": {"peak_offset": 0.1}})["pop"]
    assert element_state(0.0, shifted, 0.1, timescale=2.0)[SCALE] == \
        element_state(0.0, shifted, 0.1, timescale=1.0)[SCALE] == 1.25


# -- combined names ("drop+fade") -----------------------------------------

def test_a_name_splits_into_its_parts() -> None:
    assert split_effect_name("drop+fade") == ("drop", "fade")
    assert split_effect_name("pop") == ("pop",)
    assert split_effect_name(None) == ()
    assert split_effect_name("") == ()
    # a hand-edited project: stray spaces and empty pieces drop out,
    # and a part named twice still runs once
    assert split_effect_name("drop + fade") == ("drop", "fade")
    assert split_effect_name("drop++fade+drop") == ("drop", "fade")


def test_effects_for_resolves_every_part() -> None:
    assert effects_for("drop+fade") == (PRESETS["drop"], PRESETS["fade"])
    half = build_presets(0.5)
    assert effects_for("drop+fade", half) == (half["drop"], half["fade"])


def test_an_unknown_part_is_skipped_and_the_rest_kept() -> None:
    """An old build opening "drop+shimmer" still drops."""
    assert effects_for("drop+shimmer") == (PRESETS["drop"],)
    assert effects_for("shimmer+drop") == (PRESETS["drop"],)


def test_a_wholly_unknown_name_falls_back_to_the_default() -> None:
    default = PRESETS[DEFAULT_EFFECT]
    assert effects_for("shimmer+glow") == (default,)
    assert effects_for("no-such-effect") == (default,)
    assert effects_for(None) == (default,)
    assert effects_for("") == (default,)


def test_a_plain_name_resolves_exactly_as_it_always_did() -> None:
    for name in (None, "pop", "fade", "drop", "slide", "no-such-effect"):
        assert effects_for(name) == (effect_for(name),)
