"""Evaluator: exact values around the trigger; effects stay data-only."""
from __future__ import annotations

import pytest

from scoreanim.core.animation import (OPACITY, Easing, Effect, Envelope,
                                      Keyframe, PropertyId, appear,
                                      element_state)


def test_appear_step_exact_values() -> None:
    env = appear(0.3).tracks[OPACITY]
    assert env.value_at(-1.0) == 0.3
    assert env.value_at(-1e-9) == 0.3
    assert env.value_at(0.0) == 1.0          # at-onset inclusive
    assert env.value_at(1e-9) == 1.0
    assert env.value_at(3600.0) == 1.0       # after-last holds


def test_initial_honored_with_empty_keyframes() -> None:
    assert Envelope(initial=0.5, keyframes=()).value_at(123.0) == 0.5


def test_linear_midpoint_exact() -> None:
    env = Envelope(initial=0.0, keyframes=(
        Keyframe(0.0, 0.0, Easing.STEP),
        Keyframe(2.0, 1.0, Easing.LINEAR)))
    assert env.value_at(0.0) == 0.0
    assert env.value_at(1.0) == 0.5
    assert env.value_at(2.0) == 1.0
    assert env.value_at(5.0) == 1.0


def test_envelope_validation() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        Envelope(initial=0.0, keyframes=(
            Keyframe(1.0, 0.0), Keyframe(1.0, 1.0)))
    with pytest.raises(ValueError, match="first keyframe"):
        Envelope(initial=0.0, keyframes=(Keyframe(0.0, 1.0, Easing.LINEAR),))


def test_element_state_around_trigger() -> None:
    fx = appear(0.3)
    assert element_state(10.0, fx, 9.99)[OPACITY] == 0.3
    assert element_state(10.0, fx, 10.0)[OPACITY] == 1.0
    assert element_state(10.0, fx, 11.0)[OPACITY] == 1.0


def test_two_track_effect_needs_no_evaluator_changes() -> None:
    """Rule 6: a new property is data, not a new evaluator branch."""
    glow = PropertyId("glow")
    fx = Effect("appear+glow", {
        OPACITY: Envelope(0.3, (Keyframe(0.0, 1.0),)),
        glow: Envelope(0.0, (Keyframe(0.0, 1.0), Keyframe(0.5, 0.0, Easing.LINEAR))),
    })
    state = fx.state_at(0.25)
    assert state[OPACITY] == 1.0
    assert state[glow] == 0.5
