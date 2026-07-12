"""The pop preset (PHASES 5.4): proving effects-as-data — this preset
plus this test are the ENTIRE diff for adding an effect. Zero changes in
the evaluator (core/animation/effect.py, state.py), the applier, or the
UI (the effect menu enumerates the registry)."""
from __future__ import annotations

import pytest

from scoreanim.core.animation import (OPACITY, PRESETS, SCALE, element_state,
                                      FLOOR_OPACITY)


def test_pop_is_registered() -> None:
    assert "pop" in PRESETS
    assert PRESETS["pop"].duration == pytest.approx(0.25)


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
