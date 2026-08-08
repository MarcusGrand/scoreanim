"""The glow effect's own data: the envelope its shape params build, the
superseded shape words they replaced, and the fail-soft reading of the
halo's colour and size.

The applier's half — a halo lit only inside its window, and the styling
reaching the items once rather than every frame — is in
tests/test_glow_render.py.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation import (FLOOR_OPACITY, GLOW, GLOW_COLOR,
                                      GLOW_DENSITY, GLOW_POP, GLOW_RADIUS,
                                      GLOW_SWELL,
                                      OPACITY, PRESETS, SCALE, build_presets,
                                      derive_windows, element_state,
                                      fold_strength, glow_track, read_glow,
                                      read_glow_shape)
from scoreanim.core.timing import TempoEvent, TempoMap

# 60 bpm: one beat is one second, so every duration below reads straight
# off in seconds.
TEMPO = TempoMap([TempoEvent(0.0, 60.0)])


def envelope(params=None, seconds: float = 1.0):
    """The envelope one document entry builds. A span of exactly 1 s
    makes every fraction below read straight off as a second. The
    amount is always 1.0 — the envelope's own levels are the
    brightness, which is what retiring Strength means."""
    return glow_track(read_glow_shape(params or {}), 1.0, seconds)


def shape_of(env) -> list[tuple[float, float, str]]:
    return [(round(k.t_rel, 6), round(k.value, 6), k.easing.name)
            for k in env.keyframes]


# -- the envelope ---------------------------------------------------------

def test_the_default_shape_rises_holds_and_lands_on_nothing() -> None:
    """Attack 10 %, a hold at full, release 20 % — and the number that
    matters most is the last one: the light is at exactly 0 when the
    span ends, which is what keeps a glow to the sounding notes."""
    env = envelope()
    assert env.value_at(-0.001) == 0.0        # nothing before the note
    assert env.value_at(0.0) == pytest.approx(0.0)
    assert 0.0 < env.value_at(0.05) < 1.0     # on its way up
    assert env.value_at(0.10) == pytest.approx(1.0)   # up at the attack's end
    assert env.value_at(0.40) == pytest.approx(1.0)   # and holding
    assert env.value_at(0.80) == pytest.approx(1.0)   # right to the release
    assert 0.0 < env.value_at(0.9) < 1.0      # on its way down
    assert env.value_at(1.0) == 0.0           # exactly, not approximately
    assert env.value_at(5.0) == 0.0           # and it stays out
    # the rise only rises and the fall only falls
    rise = [env.value_at(0.10 * i / 10) for i in range(11)]
    fall = [env.value_at(0.8 + 0.2 * i / 10) for i in range(11)]
    assert rise == sorted(rise) and fall == sorted(fall, reverse=True)


def test_the_sustain_is_the_level_it_holds_at() -> None:
    env = envelope({"sustain": 0.4})
    assert env.value_at(0.10) == pytest.approx(0.4)
    assert env.value_at(0.50) == pytest.approx(0.4)
    assert env.value_at(0.80) == pytest.approx(0.4)
    assert env.value_at(1.0) == 0.0


def test_the_swell_level_is_the_top_and_the_sustain_is_the_hold() -> None:
    """The two levels are the whole of the brightness now: there is no
    second knob multiplying them."""
    env = envelope({"sustain": 0.2, "swell_on": True, "swell_level": 0.4})
    assert env.value_at(0.5) == pytest.approx(0.4)   # the swell's top
    assert env.value_at(0.8) == pytest.approx(0.2)   # the hold


def test_the_swell_humps_where_it_says_and_comes_back_to_the_hold() -> None:
    env = envelope({"sustain": 0.5, "swell_on": True, "swell_pos": 0.3,
                    "swell_level": 0.9})
    assert env.value_at(0.10) == pytest.approx(0.5)   # up to the hold
    assert env.value_at(0.30) == pytest.approx(0.9)   # the hump's top
    assert env.value_at(0.80) == pytest.approx(0.5)   # back on the hold
    assert env.value_at(1.0) == 0.0
    # the top is a top, not a slope through it
    assert env.value_at(0.2) < env.value_at(0.3) > env.value_at(0.5)


def test_a_swell_below_the_sustain_is_a_dip() -> None:
    """Nothing insists the hump goes up — the same two knobs read as a
    dip in the held light, and the shape is still legal."""
    env = envelope({"sustain": 0.8, "swell_on": True, "swell_level": 0.2})
    assert env.value_at(0.5) == pytest.approx(0.2)
    assert env.value_at(0.3) > env.value_at(0.5) < env.value_at(0.7)


def test_an_attack_and_release_that_overflow_scale_down_together() -> None:
    """A hand-edited file can ask for more rise and fall than there is
    span. Both come down proportionally, keeping the balance asked for,
    instead of the Envelope refusing the keyframes."""
    env = envelope({"attack": 0.8, "release": 0.8})
    assert shape_of(env) == [(0.0, 0.0, "STEP"), (0.49, 1.0, "EASE_OUT"),
                             (0.51, 1.0, "LINEAR"), (1.0, 0.0, "EASE_OUT")]
    # and the balance survives: twice the attack of the release stays so
    lopsided = read_glow_shape({"attack": 1.0, "release": 0.5})
    assert lopsided.attack == pytest.approx(2.0 * lopsided.release)
    assert lopsided.attack + lopsided.release < 1.0


def test_the_swell_is_forced_inside_the_hold() -> None:
    """It has to sit strictly between the attack's end and the release's
    start, or the keyframes stop increasing."""
    late = read_glow_shape({"swell_on": True, "swell_pos": 0.99})
    assert 0.10 < late.swell_pos < 0.80
    early = read_glow_shape({"swell_on": True, "swell_pos": 0.0})
    assert 0.10 < early.swell_pos < 0.80
    # and with no room left for one, the hump simply drops out
    crowded = read_glow_shape({"swell_on": True, "attack": 0.5,
                               "release": 0.5})
    assert crowded.swell_on is False


@pytest.mark.parametrize("params", [
    {"attack": -1.0}, {"release": -3.0}, {"attack": 5.0, "release": 5.0},
    {"sustain": "loud"}, {"swell_pos": float("nan")},
    {"swell_level": float("inf")}, {"attack": 0.0, "release": 0.0},
    {"attack": 1.0, "release": 1.0}, {"attack": 1.0, "release": 0.0},
    {"attack": 0.0, "release": 1.0, "swell_on": True},
    {"swell_on": True, "attack": 0.49, "release": 0.49},
    {"shape": "shimmer"}, {"sustain": 0.0, "swell_on": True},
])
def test_a_degenerate_shape_degrades_instead_of_raising(params) -> None:
    """Whatever is in the file, an envelope comes back and it ends on
    nothing. `Envelope` refuses keyframes that do not strictly increase,
    so this is the guarantee the clamping exists for."""
    env = envelope(params)
    assert env.value_at(1.0) == 0.0
    assert env.value_at(2.0) == 0.0
    times = [k.t_rel for k in env.keyframes]
    assert times == sorted(set(times))
    assert times[-1] == pytest.approx(1.0)   # the span is always the span


# -- the superseded shape words -------------------------------------------

def test_an_old_pop_document_comes_back_exactly_as_it_was() -> None:
    """Full light at the trigger, one eased fall over the whole span:
    this envelope with no attack, everything held, and the release
    taking the lot."""
    env = envelope({"shape": GLOW_POP, "sustain": 0.6}, seconds=0.4)
    assert shape_of(env) == [(0.0, 0.6, "STEP"), (0.4, 0.0, "EASE_OUT")]


def test_an_old_swell_document_comes_back_exactly_as_it_was() -> None:
    """The old hump: dark at the onset, up on EASE_IN to the peak, down
    on EASE_OUT. It is this envelope with nothing held and the swell
    doing all the work."""
    env = envelope({"shape": GLOW_SWELL, "peak": 0.25}, seconds=0.8)
    assert shape_of(env) == [(0.0, 0.0, "STEP"), (0.2, 1.0, "EASE_IN"),
                             (0.8, 0.0, "EASE_OUT")]
    # the peak keeps its own default too
    assert envelope({"shape": GLOW_SWELL}).value_at(0.5) == pytest.approx(1.0)


def test_an_unknown_old_shape_word_is_still_a_pop() -> None:
    """The fail-soft the old switch had, kept."""
    assert shape_of(envelope({"shape": "shimmer"})) \
        == shape_of(envelope({"shape": GLOW_POP}))


def test_a_new_key_wins_over_the_old_shape_word() -> None:
    """The `part_colors` fold's rule: the old word supplies defaults,
    and anything the document says outright beats it — so one knob moved
    on an old project leaves the rest of its shape standing."""
    shape = read_glow_shape({"shape": GLOW_SWELL, "peak": 0.25,
                             "sustain": 0.5})
    assert shape.sustain == pytest.approx(0.5)      # the new key
    assert shape.swell_on is True                   # still the old hump
    assert shape.swell_pos == pytest.approx(0.25)


def test_a_document_that_never_stored_a_shape_gets_the_new_defaults() -> None:
    shape = read_glow_shape(None)
    assert (shape.attack, shape.sustain, shape.release) == \
        pytest.approx((0.10, 1.0, 0.20))
    assert shape.swell_on is False


# -- the superseded Strength ----------------------------------------------

def test_a_folded_strength_glows_exactly_as_it_did() -> None:
    """The claim the whole fold rests on, in numbers: the old two-knob
    path and the folded one-knob entry build the same curve, sample for
    sample. `amount` is what Strength used to be."""
    stored = {"sustain": 0.5, "swell_on": True, "swell_level": 1.0,
              "attack": 0.1, "release": 0.2}
    before = glow_track(read_glow_shape(stored), 0.4, 1.0)
    after = envelope(fold_strength({**stored, "strength": 0.4}))
    assert [round(before.value_at(t / 100), 9) for t in range(101)] == \
        [round(after.value_at(t / 100), 9) for t in range(101)]


def test_the_strength_multiplies_the_two_levels_and_leaves() -> None:
    """A project tuned to 0.6 with the default shape: the light it held
    at was 0.6, and now the document says so outright."""
    assert fold_strength({"strength": 0.6}) == {"sustain": pytest.approx(0.6),
                                                "swell_level":
                                                    pytest.approx(0.6)}


def test_a_document_with_no_strength_is_left_alone() -> None:
    for raw in (None, {}, {"radius": 30.0, "sustain": 0.5}):
        assert fold_strength(raw) == dict(raw or {})


def test_a_full_strength_is_just_the_dead_key_going() -> None:
    """1.0 multiplied nothing, so nothing is written — only the key
    goes, which is what stops it folding a second time later."""
    assert fold_strength({"strength": 1.0, "radius": 30.0}) == {"radius": 30.0}
    assert fold_strength({"strength": 99.0}) == {}      # clamped, so full


def test_the_strength_folds_off_the_shape_the_document_glows_in() -> None:
    """An old project can carry BOTH superseded keys. The levels the
    strength multiplied were the ones the shape word mapped to, not the
    module defaults, so the fold reads through `glow_defaults`."""
    folded = fold_strength({"shape": GLOW_SWELL, "strength": 0.5})
    assert folded["sustain"] == pytest.approx(0.0)      # the hump held none
    assert folded["swell_level"] == pytest.approx(0.5)  # half of the top
    assert "strength" not in folded
    # and the shape word still supplies the rest of the old look
    assert read_glow_shape(folded).swell_on is True


def test_an_explicit_level_is_folded_too_not_just_a_default() -> None:
    """The reason this cannot happen at consumption: it has to reach a
    level the document states outright, and doing it twice would darken
    the note every time the user touched Sustain."""
    assert fold_strength({"sustain": 0.5, "strength": 0.5})["sustain"] == \
        pytest.approx(0.25)


def test_an_unreadable_strength_falls_back_to_full() -> None:
    for bad in ("bright", None, float("nan")):
        assert fold_strength({"strength": bad, "radius": 30.0}) == \
            {"radius": 30.0}


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


def test_a_silent_document_asks_for_one_pass_of_light() -> None:
    """Density is the one styling number a document already saved does
    not carry, so its default has to be the plain blur — one pass, which
    render returns untouched."""
    assert read_glow(None).density == pytest.approx(GLOW_DENSITY)
    assert read_glow(None).passes == pytest.approx(1.0)


def test_density_climbs_to_a_solid_halo() -> None:
    """Between the two ends the pass count only rises, and the first
    half of the knob buys more than the second — which is the curve's
    whole reason for being there."""
    counts = [read_glow({"density": d}).passes
              for d in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert counts == sorted(counts)
    assert counts[-1] > 16.0                  # solid, measured at 32
    assert counts[2] - counts[0] < counts[4] - counts[2]


@pytest.mark.parametrize("bad", ["solid", None, [], float("nan"),
                                 float("inf")])
def test_an_unreadable_density_falls_back_to_the_default(bad) -> None:
    assert read_glow({"density": bad}).density == pytest.approx(GLOW_DENSITY)


def test_the_density_is_clamped_at_consumption() -> None:
    assert read_glow({"density": -2.0}).density == pytest.approx(0.0)
    assert read_glow({"density": 5.0}).density == pytest.approx(1.0)


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
    """The shape is authored in fractions of the span, so the duration
    is what turns them into seconds."""
    reg = build_presets(FLOOR_OPACITY,
                        {"glow": {"sustain": 0.5, "attack": 0.25,
                                  "release": 0.25, "duration": 2.0}})
    env = reg["glow"].tracks[GLOW]
    assert env.value_at(0.0) == pytest.approx(0.0)
    assert env.value_at(0.5) == pytest.approx(0.5)     # 25 % of 2 s, at
    assert env.value_at(1.5) == pytest.approx(0.5)     # the held level
    assert env.value_at(2.0) == 0.0


def test_the_params_are_clamped_at_consumption() -> None:
    """The command layer checks type only; the ranges are enforced
    here, where the params are consumed."""
    reg = build_presets(FLOOR_OPACITY,
                        {"glow": {"sustain": 99.0, "duration": -1.0,
                                  "attack": 0.0}})
    env = reg["glow"].tracks[GLOW]
    assert env.value_at(0.0) == pytest.approx(1.0)     # sustain clamped
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

    # The shape is fractions of the span, so on a 4 s note the default
    # 10 % attack lands at 0.4 s and the 20 % release starts at 3.2 s.
    assert light(0.0, whole[0]) == pytest.approx(0.0)
    assert light(0.4, whole[0]) == pytest.approx(1.0)
    assert light(1.6, whole[0]) == pytest.approx(1.0)      # holding
    assert light(3.2, whole[0]) == pytest.approx(1.0)      # to the release
    assert light(3.9, whole[0]) > 0.0                      # dying
    assert light(4.0, whole[0]) == 0.0                     # out with the note
    # and the eighth runs the same shape eight times faster: 10 % of
    # 0.5 s is 0.05 s, 80 % of it is 0.4 s
    assert light(0.05, eighth[0]) == pytest.approx(1.0)
    assert light(0.4, eighth[0]) == pytest.approx(1.0)
    assert light(0.49, eighth[0]) > 0.0
    assert light(0.5, eighth[0]) == 0.0
    # at the moment the eighth goes out the whole note is still burning
    assert light(0.5, whole[0]) > 0.5


def test_the_glow_window_is_the_effects_duration() -> None:
    """What the applier re-evaluates the trigger inside: a glow with no
    duration would light and never go out."""
    reg = build_presets(FLOOR_OPACITY, {"glow": {"duration": 0.6}})
    assert reg["glow"].duration == pytest.approx(0.6)
