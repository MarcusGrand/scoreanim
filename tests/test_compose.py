"""Effects that run together (drop+fade): the compose table and the
combined evaluation helper.

The envelopes are never merged — each effect is evaluated on its own
through the ONE kernel and the RESULTS combine, property by property.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation import (COMPOSE_OPS, FLOOR_OPACITY, GLOW,
                                      MODULATED_PROPERTIES, OFFSET_X,
                                      OFFSET_Y, OPACITY, PRESETS, SCALE,
                                      Easing, Effect, Envelope, Keyframe,
                                      PropertyId, build_presets,
                                      combined_state, compose_states,
                                      element_state, modulate_state)
from scoreanim.core.animation import effect as effect_module


def _scaler(name: str, factor: float) -> Effect:
    return Effect(name, {SCALE: Envelope(
        initial=1.0, keyframes=(Keyframe(0.0, factor, Easing.STEP),))})


def _mover(name: str, dx: float, dy: float) -> Effect:
    return Effect(name, {
        OFFSET_X: Envelope(initial=0.0,
                           keyframes=(Keyframe(0.0, dx, Easing.STEP),)),
        OFFSET_Y: Envelope(initial=0.0,
                           keyframes=(Keyframe(0.0, dy, Easing.STEP),)),
    })


# -- the table ------------------------------------------------------------

def test_the_table_covers_every_property_there_is() -> None:
    """A property with no rule falls back to last-one-wins, which is
    fine for a preset from a newer build but must never happen to one of
    ours: adding a property means adding its rule here."""
    # every property constant the effect module declares, found by
    # scanning, so a new one added without a rule fails here
    declared = {value for name, value in vars(effect_module).items()
                if name.isupper() and isinstance(value, str)}
    assert declared == {OPACITY, SCALE, OFFSET_X, OFFSET_Y, GLOW}
    assert set(COMPOSE_OPS) == declared


def test_scales_multiply_and_offsets_add() -> None:
    both = compose_states([{SCALE: 2.0, OFFSET_X: 10.0, OFFSET_Y: -4.0},
                           {SCALE: 3.0, OFFSET_X: 0.5, OFFSET_Y: 4.0}])
    assert both[SCALE] == pytest.approx(6.0)
    assert both[OFFSET_X] == pytest.approx(10.5)
    assert both[OFFSET_Y] == pytest.approx(0.0)


def test_the_dimmer_opacity_wins() -> None:
    """min, not multiply: two effects half way in are half way in, not
    a quarter."""
    assert compose_states([{OPACITY: 0.5}, {OPACITY: 0.8}])[OPACITY] == 0.5


def test_a_silent_effect_leaves_a_property_alone() -> None:
    """An effect that carries no track for a property contributes that
    property's neutral, which by definition changes nothing."""
    out = compose_states([{OPACITY: 0.4, SCALE: 2.0}, {OPACITY: 0.9}])
    assert out == {OPACITY: 0.4, SCALE: 2.0}


def test_order_never_matters() -> None:
    a = {OPACITY: 0.3, SCALE: 2.0, OFFSET_X: 5.0}
    b = {OPACITY: 0.7, SCALE: 0.5, OFFSET_Y: -2.0}
    assert compose_states([a, b]) == compose_states([b, a])


def test_one_effect_composes_to_itself() -> None:
    one = {OPACITY: 0.3, SCALE: 1.4}
    assert compose_states([one]) == one


# -- the combined kernel --------------------------------------------------

def test_one_component_matches_the_plain_kernel() -> None:
    pop = PRESETS["pop"]
    for t in (9.9, 10.0, 10.1, 10.25, 11.0):
        assert combined_state(10.0, ((pop, 1.0),), t) \
            == element_state(10.0, pop, t)


def test_drop_and_fade_keep_the_ghost_at_the_floor() -> None:
    """The combined ghost sits exactly AT the document floor — the
    reason opacity combines with min and not with multiply."""
    combo = ((PRESETS["drop"], 1.0), (PRESETS["fade"], 1.0))
    before = combined_state(10.0, combo, 9.9)
    assert before[OPACITY] == pytest.approx(FLOOR_OPACITY)
    assert before[SCALE] == pytest.approx(1.0)


def test_drop_and_fade_arrive_solid_and_at_engraved_size() -> None:
    combo = ((PRESETS["drop"], 1.0), (PRESETS["fade"], 1.0))
    # past both durations (drop 0.35, fade 0.4)
    landed = combined_state(10.0, combo, 10.5)
    assert landed[OPACITY] == pytest.approx(1.0)
    assert landed[SCALE] == pytest.approx(1.0)
    # on the way in the note is big, and no brighter than the fade alone
    entering = combined_state(10.0, combo, 10.0)
    assert entering[SCALE] == pytest.approx(3.0)
    assert entering[OPACITY] == pytest.approx(
        element_state(10.0, PRESETS["fade"], 10.0)[OPACITY])


def test_each_component_keeps_its_own_timescale() -> None:
    """The pair is (effect, timescale): one component may stretch to a
    note's length while the other runs at its authored speed."""
    slow, fast = _scaler("slow", 2.0), _scaler("fast", 3.0)
    out = combined_state(0.0, ((slow, 4.0), (fast, 1.0)), 1.0)
    assert out[SCALE] == pytest.approx(6.0)


def test_each_component_keeps_its_own_trigger_shift() -> None:
    early = Effect("early", {SCALE: Envelope(
        initial=1.0, keyframes=(Keyframe(0.0, 2.0, Easing.STEP),))},
        trigger_shift=-0.1)
    on_time = _scaler("on_time", 3.0)
    # 50 ms before the trigger only the shifted one has fired
    assert combined_state(10.0, ((early, 1.0), (on_time, 1.0)),
                          9.95)[SCALE] == pytest.approx(2.0)
    assert combined_state(10.0, ((early, 1.0), (on_time, 1.0)),
                          10.0)[SCALE] == pytest.approx(6.0)


def test_pop_and_swell_multiply_into_a_dip_then_a_swell() -> None:
    """The look the compose table buys for free: a pop that DIPS to 0.75
    under a swell that rises to 1.5. Nothing in either preset knows
    about the other — the scales simply multiply."""
    reg = build_presets(FLOOR_OPACITY,
                        {"pop": {"scale": 0.75, "settle": 0.2},
                         "swell": {"size": 1.5, "duration": 0.8,
                                   "note_value": False}})
    combo = ((reg["pop"], 1.0), (reg["swell"], 1.0))
    # at the onset the note shrinks: the pop is at its dip, the swell
    # has not left rest
    dip = combined_state(10.0, combo, 10.0)[SCALE]
    assert dip == pytest.approx(0.75)
    # at the swell's top the pop is long home, so the swell is all there is
    top = combined_state(10.0, combo, 10.4)[SCALE]
    assert top == pytest.approx(1.5)
    # the dip and the top must differ, or this test would pass on a
    # flat state
    assert dip < 1.0 < top
    # anywhere inside both windows it is exactly the product
    inside = combined_state(10.0, combo, 10.1)[SCALE]
    assert inside == pytest.approx(
        element_state(10.0, reg["pop"], 10.1)[SCALE]
        * element_state(10.0, reg["swell"], 10.1)[SCALE])
    assert inside != pytest.approx(dip)
    # and both leave the note at its engraved size
    assert combined_state(10.0, combo, 10.8)[SCALE] == pytest.approx(1.0)


def test_a_gain_scales_the_swell_like_any_other_departure() -> None:
    """The volume response modulates the swell's amplitude with no
    special case: SCALE's rest is 1.0, so a quiet note swells less and a
    loud one more, and the note is still fully visible either way."""
    peak = element_state(10.0, PRESETS["swell"], 10.4)
    assert peak[SCALE] == pytest.approx(1.4)
    assert modulate_state(peak, 0.5)[SCALE] == pytest.approx(1.2)
    assert modulate_state(peak, 2.0)[SCALE] == pytest.approx(1.8)
    # at rest — before the trigger, and once it has settled — the gain
    # has nothing to scale
    for t in (9.9, 10.8):
        rest = element_state(10.0, PRESETS["swell"], t)
        assert modulate_state(rest, 3.0)[SCALE] == pytest.approx(1.0)
    # opacity is untouched, at the top and at the floor
    assert modulate_state(peak, 0.25)[OPACITY] == 1.0
    ghost = element_state(10.0, PRESETS["swell"], 9.9)
    assert modulate_state(ghost, 0.25)[OPACITY] == pytest.approx(
        FLOOR_OPACITY)


def test_two_glows_take_the_brighter_one() -> None:
    """max, not add: light that added would blow past full glow."""
    assert compose_states([{GLOW: 0.4}, {GLOW: 0.9}])[GLOW] == 0.9
    assert compose_states([{GLOW: 0.9}, {GLOW: 0.4}])[GLOW] == 0.9
    # an effect that does not glow contributes 0, which changes nothing
    assert compose_states([{GLOW: 0.6}, {SCALE: 2.0}])[GLOW] == 0.6


def test_pop_and_glow_leave_scale_and_glow_each_correct() -> None:
    """The two effects share nothing: pop owns the size, glow owns the
    light, and neither knows the other is running."""
    reg = build_presets(FLOOR_OPACITY,
                        {"pop": {"scale": 1.25, "settle": 0.25},
                         "glow": {"strength": 1.0, "duration": 0.4,
                                  "note_value": False}})
    combo = ((reg["pop"], 1.0), (reg["glow"], 1.0))
    at_onset = combined_state(10.0, combo, 10.0)
    assert at_onset[SCALE] == pytest.approx(1.25)
    assert at_onset[GLOW] == pytest.approx(1.0)
    assert at_onset[OPACITY] == pytest.approx(1.0)
    # each property is exactly what its own effect alone would give
    inside = combined_state(10.0, combo, 10.1)
    assert inside[SCALE] == pytest.approx(
        element_state(10.0, reg["pop"], 10.1)[SCALE])
    assert inside[GLOW] == pytest.approx(
        element_state(10.0, reg["glow"], 10.1)[GLOW])
    # and the pop is past its dip while the glow is still lit, so this
    # is not passing on a flat state
    assert inside[SCALE] < 1.25
    assert 0.0 < inside[GLOW] < 1.0
    # both home: engraved size, no light left
    landed = combined_state(10.0, combo, 10.5)
    assert landed[SCALE] == pytest.approx(1.0)
    assert landed[GLOW] == pytest.approx(0.0)


def test_swell_and_glow_leave_scale_and_glow_each_correct() -> None:
    reg = build_presets(FLOOR_OPACITY,
                        {"swell": {"size": 1.4, "duration": 0.8,
                                   "note_value": False},
                         "glow": {"strength": 1.0, "duration": 0.4,
                                  "note_value": False}})
    combo = ((reg["swell"], 1.0), (reg["glow"], 1.0))
    # 0.1 s in: the swell is on its way up, the glow on its way down
    mid = combined_state(10.0, combo, 10.1)
    assert mid[SCALE] == pytest.approx(
        element_state(10.0, reg["swell"], 10.1)[SCALE])
    assert mid[GLOW] == pytest.approx(
        element_state(10.0, reg["glow"], 10.1)[GLOW])
    assert mid[SCALE] > 1.0 and 0.0 < mid[GLOW] < 1.0


def test_two_movers_add_their_travel() -> None:
    out = combined_state(0.0, ((_mover("a", 10.0, -20.0), 1.0),
                               (_mover("b", 5.0, 4.0), 1.0)), 0.0)
    assert out[OFFSET_X] == pytest.approx(15.0)
    assert out[OFFSET_Y] == pytest.approx(-16.0)


# -- the volume response's modulation -------------------------------------

def test_a_gain_scales_how_far_scale_departs_from_rest() -> None:
    """Rest for SCALE is 1.0, so gain 2 doubles the departure: a pop to
    1.25 becomes a pop to 1.5, not to 2.5."""
    assert modulate_state({SCALE: 1.25}, 2.0)[SCALE] == pytest.approx(1.5)
    assert modulate_state({SCALE: 1.25}, 0.5)[SCALE] == pytest.approx(1.125)
    # a note already at rest stays at rest whatever the gain
    assert modulate_state({SCALE: 1.0}, 4.0)[SCALE] == pytest.approx(1.0)


def test_a_gain_scales_the_offsets_about_zero() -> None:
    out = modulate_state({OFFSET_X: 100.0, OFFSET_Y: -40.0}, 0.5)
    assert out[OFFSET_X] == pytest.approx(50.0)
    assert out[OFFSET_Y] == pytest.approx(-20.0)


def test_a_gain_scales_the_glow_about_darkness() -> None:
    """Rest for GLOW is 0, so the gain simply scales the light: a loud
    note burns brighter and a quiet one barely lights — and a note with
    no glow at all stays dark whatever the gain."""
    assert modulate_state({GLOW: 0.8}, 0.5)[GLOW] == pytest.approx(0.4)
    assert modulate_state({GLOW: 0.5}, 2.0)[GLOW] == pytest.approx(1.0)
    assert modulate_state({GLOW: 0.0}, 4.0)[GLOW] == pytest.approx(0.0)
    # opacity rides along untouched, as ever
    out = modulate_state({GLOW: 0.8, OPACITY: 0.3}, 0.25)
    assert out[OPACITY] == 0.3
    assert out[GLOW] == pytest.approx(0.2)


def test_opacity_is_never_modulated() -> None:
    """A quiet note still becomes fully visible — the score has to stay
    readable wherever the playing is soft."""
    for gain in (0.0, 0.25, 1.0, 3.0):
        out = modulate_state({OPACITY: 0.3, SCALE: 2.0}, gain)
        assert out[OPACITY] == 0.3


def test_gain_one_hands_the_state_straight_back() -> None:
    """Bit-for-bit, not approximately: with the response off every value
    has to be exactly what it was before the feature existed."""
    state = {OPACITY: 0.3, SCALE: 1.2345678901234567,
             OFFSET_X: -119.99999999999999, OFFSET_Y: 0.1 + 0.2}
    out = modulate_state(state, 1.0)
    assert out == state
    for prop, value in state.items():
        assert out[prop] is value or out[prop] == value


def test_a_property_with_no_rule_passes_through() -> None:
    """A preset from a newer build degrades instead of being mangled."""
    future = PropertyId("rotation")
    assert modulate_state({future: 45.0}, 2.0)[future] == 45.0


def test_the_modulated_set_is_a_subset_of_the_table() -> None:
    """Every modulated property needs a neutral to scale about, so it
    must have a rule in the compose table."""
    assert MODULATED_PROPERTIES <= set(COMPOSE_OPS)
    assert OPACITY not in MODULATED_PROPERTIES
