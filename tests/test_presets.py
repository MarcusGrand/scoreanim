"""The pop preset (PHASES 5.4): proving effects-as-data — this preset
plus this test are the ENTIRE diff for adding an effect. Zero changes in
the evaluator (core/animation/effect.py, state.py), the applier, or the
UI (the effect menu enumerates the registry)."""
from __future__ import annotations

import pytest

from scoreanim.core.animation import (OPACITY, PRESETS, SCALE, build_presets,
                                      effect_for, element_state,
                                      FLOOR_OPACITY)


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
    assert set(reg) == {"appear", "pop"}


def test_consumption_clamps() -> None:
    pop = build_presets(0.3, {"pop": {"scale": 99.0, "settle": 0.0,
                                      "peak_offset": 5.0}})["pop"]
    assert pop.trigger_shift == 0.5                     # ±0.5 s range
    assert pop.duration == pytest.approx(0.01)          # settle floor
    assert element_state(0.0, pop, 0.5)[SCALE] == 10.0  # scale ceiling


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
