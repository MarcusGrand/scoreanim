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


def _ramp(easing: Easing) -> Envelope:
    """0 → 1 over two seconds, on the given curve."""
    return Envelope(initial=0.0, keyframes=(
        Keyframe(0.0, 0.0, Easing.STEP), Keyframe(2.0, 1.0, easing)))


def test_eased_endpoints_are_exact() -> None:
    """A curve only changes the way there, never where it starts or
    ends — the same guarantee LINEAR gives."""
    for easing in (Easing.EASE_OUT, Easing.EASE_IN):
        env = _ramp(easing)
        assert env.value_at(-1.0) == 0.0     # before the first keyframe
        assert env.value_at(0.0) == 0.0
        assert env.value_at(2.0) == 1.0
        assert env.value_at(5.0) == 1.0      # after-last holds


def test_eased_midpoints_are_not_linear() -> None:
    """Half the time is not half the way: ease-out is most of the way
    there already, ease-in has barely left."""
    assert _ramp(Easing.EASE_OUT).value_at(1.0) == pytest.approx(0.875)
    assert _ramp(Easing.EASE_IN).value_at(1.0) == pytest.approx(0.125)


def test_eased_curves_are_monotone() -> None:
    for easing in (Easing.EASE_OUT, Easing.EASE_IN):
        env = _ramp(easing)
        values = [env.value_at(i / 10.0) for i in range(21)]
        assert all(b >= a for a, b in zip(values, values[1:]))


def test_eased_curve_runs_from_the_previous_keyframe() -> None:
    """Like LINEAR, the ease spans the gap it ends — a keyframe before
    it moves where the curve starts, not just when."""
    env = Envelope(initial=0.0, keyframes=(
        Keyframe(0.0, 0.5, Easing.STEP),
        Keyframe(1.0, 1.5, Easing.EASE_OUT)))
    assert env.value_at(0.0) == 0.5
    assert env.value_at(0.5) == pytest.approx(0.5 + 0.875)
    assert env.value_at(1.0) == 1.5


def test_envelope_validation() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        Envelope(initial=0.0, keyframes=(
            Keyframe(1.0, 0.0), Keyframe(1.0, 1.0)))
    with pytest.raises(ValueError, match="first keyframe"):
        Envelope(initial=0.0, keyframes=(Keyframe(0.0, 1.0, Easing.LINEAR),))
    # the rule covers the new curves too: nothing to ease from
    with pytest.raises(ValueError, match="first keyframe"):
        Envelope(initial=0.0, keyframes=(Keyframe(0.0, 1.0, Easing.EASE_OUT),))


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
