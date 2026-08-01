"""How long each element's animation runs (core/animation/windows.py).

Pure arithmetic, so these run without a scene: synthetic effects and a
plain tempo map, checked against numbers worked out by hand.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation import (SCALE, Effect, Envelope, Keyframe,
                                      derive_windows)
from scoreanim.core.timing import TempoEvent, TempoMap

# 60 bpm: one beat is one second, so a duration in beats is the same
# number in seconds and every expectation below reads straight off.
TEMPO = TempoMap([TempoEvent(0.0, 60.0)])


def _timed(name: str, duration: float, *, note_value: bool = False,
           shift: float = 0.0) -> Effect:
    return Effect(name,
                  {SCALE: Envelope(initial=1.25,
                                   keyframes=(Keyframe(duration, 1.0),))},
                  trigger_shift=shift, settle_to_note_value=note_value)


def _step(name: str = "step") -> Effect:
    return Effect(name, {SCALE: Envelope(initial=1.0, keyframes=())})


def test_an_authored_duration_runs_at_its_own_speed() -> None:
    """No note-value settle: timescale 1.0, and the window is exactly
    what the effect was authored with."""
    plan = derive_windows([0.0], [0.0], [["n1"]], [[(_timed("pop", 0.25),)]],
                          {"n1": 4.0}, TEMPO)
    assert plan.timescales_per_trigger == (((1.0,),),)
    assert plan.durations == (0.25,)
    assert plan.d_max == 0.25
    assert plan.lead == 0.0


def test_a_note_value_settle_stretches_to_the_engraved_duration() -> None:
    """A 0.25 s effect on a 4-beat note at 60 bpm runs over 4 s — a
    timescale of 16, and a window to match."""
    plan = derive_windows([0.0], [0.0], [["whole"]],
                          [[(_timed("pop", 0.25, note_value=True),)]],
                          {"whole": 4.0}, TEMPO)
    assert plan.timescales_per_trigger[0][0][0] == pytest.approx(16.0)
    assert plan.durations[0] == pytest.approx(4.0)


def test_two_notes_on_one_beat_stretch_by_their_own_lengths() -> None:
    """The whole point of a per-ELEMENT timescale: same trigger,
    different note values, different speeds."""
    effect = _timed("pop", 0.5, note_value=True)
    plan = derive_windows([0.0], [0.0], [["whole", "quarter"]],
                          [[(effect,), (effect,)]],
                          {"whole": 4.0, "quarter": 1.0}, TEMPO)
    whole, quarter = plan.timescales_per_trigger[0]
    assert whole[0] == pytest.approx(8.0)
    assert quarter[0] == pytest.approx(2.0)
    # the trigger's window is the LONGEST of its items
    assert plan.durations[0] == pytest.approx(4.0)


def test_one_element_may_stretch_one_effect_and_not_the_other() -> None:
    """Per COMPONENT, not per element: "pop+fade" can settle the pop to
    the note value and run the fade at its authored speed."""
    plan = derive_windows(
        [0.0], [0.0], [["n1"]],
        [[(_timed("pop", 0.5, note_value=True), _timed("fade", 0.3))]],
        {"n1": 2.0}, TEMPO)
    stretched, plain = plan.timescales_per_trigger[0][0]
    assert stretched == pytest.approx(4.0)
    assert plain == 1.0
    assert plan.durations[0] == pytest.approx(2.0)


def test_a_missing_or_zero_duration_leaves_the_effect_alone() -> None:
    """Elements the duration map omits (dynamics, texts) and any
    non-positive entry both park at 1.0 rather than blowing up."""
    effect = _timed("pop", 0.25, note_value=True)
    plan = derive_windows([0.0, 0.0], [0.0, 0.0], [["dyn"], ["odd"]],
                          [[(effect,)], [(effect,)]],
                          {"odd": 0.0}, TEMPO)
    assert plan.timescales_per_trigger == (((1.0,),), ((1.0,),))


def test_without_a_tempo_map_every_stretch_parks_at_one() -> None:
    """Construction order: the applier builds before it has timing."""
    plan = derive_windows([0.0], [0.0], [["n1"]],
                          [[(_timed("pop", 0.25, note_value=True),)]],
                          {"n1": 4.0}, None)
    assert plan.timescales_per_trigger == (((1.0,),),)
    assert plan.durations == (0.25,)


def test_a_step_effect_has_no_window_at_all() -> None:
    plan = derive_windows([0.0], [0.0], [["n1"]], [[(_step(),)]], {}, TEMPO)
    assert plan.durations == (0.0,)
    assert plan.d_max == 0.0


def test_a_negative_shift_becomes_the_forward_lead() -> None:
    """The F3 bound: how far ahead of its trigger a shifted component is
    already live. A positive shift never leads."""
    early = derive_windows([0.0], [0.0], [["n1"]],
                           [[(_timed("pop", 0.25, shift=-0.4),)]], {}, TEMPO)
    assert early.lead == pytest.approx(0.4)
    late = derive_windows([0.0], [0.0], [["n1"]],
                          [[(_timed("pop", 0.25, shift=0.4),)]], {}, TEMPO)
    assert late.lead == 0.0
    assert late.durations[0] == pytest.approx(0.65)   # shift + duration


def test_an_element_with_no_identity_is_never_stretched() -> None:
    """The applier passes None for an item that carries no identity."""
    plan = derive_windows([0.0], [0.0], [[None]],
                          [[(_timed("pop", 0.25, note_value=True),)]],
                          {"n1": 4.0}, TEMPO)
    assert plan.timescales_per_trigger == (((1.0,),),)


def test_an_empty_schedule_is_not_a_crash() -> None:
    plan = derive_windows([], [], [], [], {}, TEMPO)
    assert plan.durations == () and plan.d_max == 0.0 and plan.lead == 0.0
