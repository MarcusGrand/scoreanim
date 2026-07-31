"""Effects that run together (drop+fade): the compose table and the
combined evaluation helper.

The envelopes are never merged — each effect is evaluated on its own
through the ONE kernel and the RESULTS combine, property by property.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation import (COMPOSE_OPS, FLOOR_OPACITY, OFFSET_X,
                                      OFFSET_Y, OPACITY, PRESETS, SCALE,
                                      Easing, Effect, Envelope, Keyframe,
                                      combined_state, compose_states,
                                      element_state)
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
    assert declared == {OPACITY, SCALE, OFFSET_X, OFFSET_Y}
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


def test_two_movers_add_their_travel() -> None:
    out = combined_state(0.0, ((_mover("a", 10.0, -20.0), 1.0),
                               (_mover("b", 5.0, 4.0), 1.0)), 0.0)
    assert out[OFFSET_X] == pytest.approx(15.0)
    assert out[OFFSET_Y] == pytest.approx(-16.0)
