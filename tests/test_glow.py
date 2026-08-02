"""The glow effect's own data: the two envelope shapes, and the
fail-soft reading of the halo's colour and size.

The applier's half — a halo lit only inside its window, and the styling
reaching the items once rather than every frame — is in
tests/test_glow_render.py.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation import (FLOOR_OPACITY, GLOW, GLOW_COLOR,
                                      GLOW_POP, GLOW_RADIUS, GLOW_SWELL,
                                      OPACITY, PRESETS, SCALE, build_presets,
                                      derive_windows, element_state,
                                      glow_track, read_glow)
from scoreanim.core.timing import TempoEvent, TempoMap

# 60 bpm: one beat is one second, so every duration below reads straight
# off in seconds.
TEMPO = TempoMap([TempoEvent(0.0, 60.0)])


# -- the two shapes -------------------------------------------------------

def test_the_pop_shape_is_full_at_the_trigger_and_dark_at_the_end() -> None:
    env = glow_track(GLOW_POP, strength=1.0, peak=0.5, seconds=0.4)
    assert env.value_at(-0.001) == 0.0        # nothing before the note
    assert env.value_at(0.0) == pytest.approx(1.0)
    assert env.value_at(0.4) == pytest.approx(0.0)
    assert env.value_at(4.0) == pytest.approx(0.0)   # and it stays out
    # it only ever fades: monotonically down across the whole window
    values = [env.value_at(0.4 * i / 20) for i in range(21)]
    assert values == sorted(values, reverse=True)


def test_the_swell_shape_peaks_where_peak_says_and_ends_dark() -> None:
    env = glow_track(GLOW_SWELL, strength=1.0, peak=0.25, seconds=0.8)
    assert env.value_at(-0.001) == 0.0
    assert env.value_at(0.0) == pytest.approx(0.0)   # starts dark
    assert env.value_at(0.2) == pytest.approx(1.0)   # 25 % of 0.8
    assert env.value_at(0.8) == pytest.approx(0.0)   # and ends dark
    # the top really is the top, not a plateau or a slope through it
    assert env.value_at(0.1) < env.value_at(0.2) > env.value_at(0.4)


def test_the_strength_is_the_top_of_either_shape() -> None:
    assert glow_track(GLOW_POP, 0.4, 0.5, 0.4).value_at(0.0) \
        == pytest.approx(0.4)
    assert glow_track(GLOW_SWELL, 0.4, 0.5, 0.4).value_at(0.2) \
        == pytest.approx(0.4)


def test_an_unknown_shape_is_a_pop() -> None:
    """The fail-soft every stored name here gets."""
    odd = glow_track("shimmer", 1.0, 0.5, 0.4)
    pop = glow_track(GLOW_POP, 1.0, 0.5, 0.4)
    assert odd.keyframes == pop.keyframes


# -- the styling half -----------------------------------------------------

def test_a_silent_document_reads_the_defaults() -> None:
    for raw in (None, {}, {"duration": 0.4}):
        style = read_glow(raw)
        assert style.color == GLOW_COLOR
        assert style.radius == pytest.approx(GLOW_RADIUS)


def test_a_stored_colour_and_radius_come_back() -> None:
    style = read_glow({"color": "#FF0080", "radius": 12.5})
    assert style.color == "#ff0080"           # lowercased for QColor
    assert style.radius == pytest.approx(12.5)


@pytest.mark.parametrize("bad", ["", "red", "#fff", "#12345g", "ffcc66",
                                 42, None, ["#ffcc66"]])
def test_an_unreadable_colour_falls_back_to_the_default(bad) -> None:
    """A hand-edited file must not be able to produce a halo nobody can
    see — read_colors' argument, on a second setting."""
    assert read_glow({"color": bad}).color == GLOW_COLOR


@pytest.mark.parametrize("bad", ["wide", None, [], float("nan"),
                                 float("inf")])
def test_an_unreadable_radius_falls_back_to_the_default(bad) -> None:
    assert read_glow({"radius": bad}).radius == pytest.approx(GLOW_RADIUS)


def test_the_radius_is_clamped_at_consumption() -> None:
    assert read_glow({"radius": -5.0}).radius == pytest.approx(0.0)
    assert read_glow({"radius": 99999.0}).radius == pytest.approx(500.0)


# -- the preset -----------------------------------------------------------

def test_the_registry_carries_glow_and_it_reveals_the_note() -> None:
    """Opacity is appear's step, so "glow" on its own still brings the
    note in — the ghost floor before the trigger, solid at it."""
    glow = PRESETS["glow"]
    assert set(glow.tracks) == {OPACITY, GLOW}
    assert element_state(10.0, glow, 9.9)[OPACITY] == pytest.approx(
        FLOOR_OPACITY)
    assert element_state(10.0, glow, 10.0)[OPACITY] == pytest.approx(1.0)
    # and it never touches the size, which is what lets it combine
    assert SCALE not in glow.tracks


def test_the_note_value_stretch_is_on_by_default() -> None:
    """The point of the effect: the light dies when the note's value
    ends, so only SOUNDING notes glow."""
    assert PRESETS["glow"].settle_to_note_value is True


def test_the_params_reach_the_envelope() -> None:
    reg = build_presets(FLOOR_OPACITY,
                        {"glow": {"shape": "swell", "strength": 0.5,
                                  "peak": 0.25, "duration": 1.0}})
    env = reg["glow"].tracks[GLOW]
    assert env.value_at(0.0) == pytest.approx(0.0)     # the swell shape
    assert env.value_at(0.25) == pytest.approx(0.5)    # peak × duration
    assert env.value_at(1.0) == pytest.approx(0.0)


def test_the_params_are_clamped_at_consumption() -> None:
    """The command layer checks type only; the ranges are enforced
    here, where the params are consumed."""
    reg = build_presets(FLOOR_OPACITY,
                        {"glow": {"strength": 99.0, "duration": -1.0}})
    env = reg["glow"].tracks[GLOW]
    assert env.value_at(0.0) == pytest.approx(1.0)     # strength clamped
    assert reg["glow"].duration > 0.0                  # duration floored


def test_the_light_dies_when_the_note_does() -> None:
    """Through the real windows seam, with the real preset: a whole note
    glows across its whole bar and an eighth for an eighth, and both go
    out exactly as the note stops sounding. This is what "only sounding
    notes glow" means in numbers."""
    glow = PRESETS["glow"]                    # duration 0.4, note value on
    plan = derive_windows([0.0], [0.0], [["whole", "eighth"]],
                          [[(glow,), (glow,)]],
                          {"whole": 4.0, "eighth": 0.5}, TEMPO)
    whole, eighth = plan.timescales_per_trigger[0]
    assert whole[0] == pytest.approx(10.0)    # 4 s over an authored 0.4
    assert eighth[0] == pytest.approx(1.25)   # 0.5 s over the same 0.4
    # the whole note's window is its own length, not the authored one
    assert plan.durations[0] == pytest.approx(4.0)

    def light(t: float, timescale: float) -> float:
        return element_state(0.0, glow, t, timescale)[GLOW]

    # lit at the onset, still lit most of the way through, out at the end
    assert light(0.0, whole[0]) == pytest.approx(1.0)
    assert light(3.9, whole[0]) > 0.0
    assert light(4.0, whole[0]) == pytest.approx(0.0)
    # and the eighth is dark eight times sooner
    assert light(0.0, eighth[0]) == pytest.approx(1.0)
    assert light(0.49, eighth[0]) > 0.0
    assert light(0.5, eighth[0]) == pytest.approx(0.0)
    # at the moment the eighth goes out the whole note is still burning
    assert light(0.5, whole[0]) > 0.5


def test_the_glow_window_is_the_effects_duration() -> None:
    """What the applier re-evaluates the trigger inside: a glow with no
    duration would light and never go out."""
    reg = build_presets(FLOOR_OPACITY, {"glow": {"duration": 0.6}})
    assert reg["glow"].duration == pytest.approx(0.6)
