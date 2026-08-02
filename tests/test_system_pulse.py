"""The whole page breathing.

Every system takes ONE size at time t and turns around the centre of its
own ink. Two things move it, and both are wired here: the recording's
loudness, which moves the whole page together, and a bump on every beat,
which moves only the system the notes landed in and needs no recording
at all.

What is pinned here: that both amounts at 0 leave the systems untouched
rather than written with 1.0, that the size is a pure function of t (so
scrubbing, playing and exporting agree), that a tempo edit moves every
bump with the beats, and that an unchanged number costs no writes.

The values' own arithmetic is pinned in test_pulse.py, and the reading
the follow half multiplies in test_intensity.py. These tests are about
the wiring: the driver, the applier seam, and the group items.
"""

import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import (StyleRules,  # noqa: E402
                                      build_bumps, build_trigger_schedule,
                                      intensity_at, peak_reference, pop_at,
                                      pulse_scale, read_pulse)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.timing import TempoEvent, TempoMap  # noqa: E402
from scoreanim.render.animate import AnimationApplier  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402
from scoreanim.render.system_group import SystemGroupItem  # noqa: E402

TEMPO = TempoMap([TempoEvent(0.0, 120.0)])
HALF_TEMPO = TempoMap([TempoEvent(0.0, 60.0)])     # every beat twice as late
AMOUNT = 0.1
# A pop big enough to read off the numbers, and a low notes_for_full so
# ordinary beats on the fixture reach full strength.
POP = {"pop_amount": 0.1, "notes_for_full": 4, "settle": 0.25}


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def schedule(engraved, join_mapping, score_model):
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures)


def _build_scenes(engraved) -> ScoreScenes:
    return ScoreScenes(engraved.layout,
                       default_stage_config(engraved.prepared,
                                            page_content_top(engraved.layout)))


@pytest.fixture()
def scenes(qapp, engraved) -> ScoreScenes:
    return _build_scenes(engraved)


@pytest.fixture()
def writes(monkeypatch):
    """Every `set_system_scale` that actually reaches a group.

    Records the CALL, not the change, so "the systems are never touched"
    means what it says: the driver has to decide not to ask, not lean on
    the group's own unchanged-value guard."""
    seen: list[float] = []
    original = SystemGroupItem.set_system_scale

    def spy(self, scale):
        seen.append(scale)
        return original(self, scale)

    monkeypatch.setattr(SystemGroupItem, "set_system_scale", spy)
    return seen


def _applier(scenes, schedule, style, peaks=None,
             offset=0.0) -> AnimationApplier:
    applier = AnimationApplier(scenes.items, schedule, TEMPO, style, (),
                              scenes.system_groups.values())
    if peaks is not None:
        applier.set_audio(peaks, offset)
    return applier


def _sizes(scenes) -> dict:
    return {key: group.system_scale
            for key, group in scenes.system_groups.items()}


def _loud_after(seconds: float, duration: float = 30.0, rate: int = 44100):
    """Near-silent up to `seconds`, loud after — so a moment before and
    a moment after read plainly different numbers."""
    import numpy as np

    from scoreanim.core.audio import PeakCacheBuilder

    samples = np.full(int(duration * rate), 1.0, dtype=np.float32)
    samples[:int(seconds * rate)] = 0.02
    builder = PeakCacheBuilder(rate)
    builder.add_samples(samples)
    return builder.snapshot()


def _silence(duration: float = 20.0, rate: int = 44100):
    import numpy as np

    from scoreanim.core.audio import PeakCacheBuilder

    builder = PeakCacheBuilder(rate)
    builder.add_samples(np.zeros(int(duration * rate), dtype=np.float32))
    return builder.snapshot()


def _expected(peaks, t: float, amount: float, offset: float = 0.0) -> float:
    """The size the page should be, worked out here from the pure
    functions rather than copied off the driver."""
    return pulse_scale(
        intensity_at(peaks, t + offset, peak_reference(peaks)),
        read_pulse({"amount": amount}))


def _bumps(scenes, schedule, stored, tempo=TEMPO) -> dict:
    """Every system's bumps, built the way the applier builds them —
    from each item's OWN system — but independently of it."""
    rows = [[(None if scenes.items[eid].identity is None
              else scenes.items[eid].identity.kind, scenes.items[eid].system)
             for eid in trig.element_ids if eid in scenes.items]
            for trig in schedule.triggers]
    return build_bumps([tempo.seconds_at(trig.beats)
                        for trig in schedule.triggers],
                       rows, read_pulse(stored))


def _expected_sizes(scenes, schedule, stored, t: float, peaks=None,
                    tempo=TEMPO) -> dict:
    """What every group should be at t: the loudness for the whole page,
    each system's own bump on top."""
    pulse = read_pulse(stored)
    bumps = _bumps(scenes, schedule, stored, tempo)
    intensity = (intensity_at(peaks, t, peak_reference(peaks))
                 if peaks is not None else 0.0)
    return {(page, system): pulse_scale(intensity, pulse,
                                        pop_at(bumps.get(system), t, pulse))
            for page, system in scenes.system_groups}


def _busiest_beat(scenes, schedule, stored) -> float:
    """The moment the heaviest bump on the fixture fires."""
    bumps = _bumps(scenes, schedule, stored)
    return max(((strength, t) for entry in bumps.values()
                for t, strength in zip(entry.seconds, entry.strengths)))[1]


# -- off means untouched -------------------------------------------------


@pytest.mark.parametrize("stored", [
    {}, {"amount": 0.0}, {"amount": 0.0, "pop_amount": 0.0},
    # the shape settings alone are not a reason to touch anything
    {"pop_amount": 0.0, "notes_for_full": 2, "settle": 1.0},
])
def test_amount_zero_never_touches_a_system(scenes, schedule, writes,
                                            stored) -> None:
    """Off is not "written with 1.0 every frame" — no system is scaled
    at all, so the page is bit-for-bit what it was before this feature,
    even with the recording loaded and playing."""
    peaks = _loud_after(4.0)
    applier = _applier(scenes, schedule, StyleRules(pulse=stored), peaks)
    for t in (0.0, 3.0, 5.0, 8.0, 12.0):
        applier.apply_at(t)
    applier.refresh(6.0)

    assert writes == []
    for group in scenes.system_groups.values():
        assert group.system_scale == 1.0
        assert group.sceneTransform().isIdentity()


def test_with_no_groups_the_pulse_can_do_nothing(scenes, schedule) -> None:
    """The default, which is what lets every other test build an applier
    out of the item map alone."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO,
                               StyleRules(pulse={"amount": AMOUNT}))
    applier.set_audio(_loud_after(4.0), 0.0)
    applier.apply_at(6.0)

    assert _sizes(scenes) == {key: 1.0 for key in scenes.system_groups}


# -- the size itself -----------------------------------------------------


def test_a_known_recording_and_amount_give_the_expected_size(
        scenes, schedule) -> None:
    peaks = _loud_after(4.0)
    applier = _applier(scenes, schedule,
                       StyleRules(pulse={"amount": AMOUNT}), peaks)
    t = 6.0
    applier.refresh(t)

    expected = _expected(peaks, t, AMOUNT)
    # non-vacuity: the page really is bigger than it was engraved
    assert expected > 1.05
    for group in scenes.system_groups.values():
        assert group.system_scale == pytest.approx(expected)
        assert not group.sceneTransform().isIdentity()


def test_every_system_takes_the_same_size(scenes, schedule) -> None:
    """One value drives them all — that is what makes the page read as
    one breathing object rather than a set of independent ones."""
    applier = _applier(scenes, schedule,
                       StyleRules(pulse={"amount": AMOUNT}), _loud_after(4.0))
    applier.refresh(6.0)

    sizes = _sizes(scenes)
    assert len(sizes) > 1                      # non-vacuity
    assert len(set(sizes.values())) == 1
    assert next(iter(sizes.values())) != 1.0


def test_each_system_turns_around_its_own_centre(scenes, schedule) -> None:
    """The seam the group items already carry: a system grows where it
    sits, so a bigger page is not a page whose systems have slid into
    each other."""
    applier = _applier(scenes, schedule,
                       StyleRules(pulse={"amount": AMOUNT}), _loud_after(4.0))
    pivots = {key: group.pivot
              for key, group in scenes.system_groups.items()}
    applier.refresh(6.0)

    for key, group in scenes.system_groups.items():
        assert group.mapToScene(pivots[key]) == pivots[key]


def test_a_louder_moment_is_a_bigger_page(scenes, schedule) -> None:
    applier = _applier(scenes, schedule,
                       StyleRules(pulse={"amount": AMOUNT}), _loud_after(6.0))
    applier.refresh(3.0)                       # in the quiet stretch
    quiet = _sizes(scenes)
    applier.refresh(9.0)                       # in the loud one
    loud = _sizes(scenes)

    for key in quiet:
        assert loud[key] > quiet[key] + 0.05


# -- a pure function of t ------------------------------------------------


def test_scrubbing_gives_the_same_size_as_arriving_fresh(qapp, engraved,
                                                         schedule) -> None:
    """The rule-2 guarantee for this driver: walking to a time and
    jumping to it cold must leave the page exactly the same size, so a
    scrub shows what playback will show."""
    peaks = _loud_after(5.0)
    style = StyleRules(pulse={"amount": AMOUNT})
    mid = 7.3

    walked_scenes = _build_scenes(engraved)
    walked = _applier(walked_scenes, schedule, style, peaks)
    rng = random.Random(17)
    t = 0.0
    for _ in range(40):
        t = max(-2.0, t + rng.uniform(-9.0, 11.0))
        walked.apply_at(t)
    for step in range(20):                     # and tick up to it
        walked.apply_at(mid - 0.4 + step * 0.02)
    walked.apply_at(mid)

    fresh_scenes = _build_scenes(engraved)
    fresh = _applier(fresh_scenes, schedule, style, peaks)
    fresh.refresh(mid)

    assert _sizes(walked_scenes) == _sizes(fresh_scenes)
    # non-vacuity: the page really is mid-breath at `mid`
    assert next(iter(_sizes(fresh_scenes).values())) != 1.0


def test_the_offset_moves_which_part_of_the_recording_is_read(
        scenes, schedule) -> None:
    """Score seconds in, audio seconds out — the one conversion, and it
    must be the same one the triggers make."""
    peaks = _loud_after(6.0)
    applier = _applier(scenes, schedule,
                       StyleRules(pulse={"amount": AMOUNT}), peaks)
    t = 3.0
    applier.refresh(t)
    assert next(iter(_sizes(scenes).values())) == \
        pytest.approx(_expected(peaks, t, AMOUNT))

    applier.set_audio(peaks, 5.0)              # beat 0 is 5 s in
    applier.refresh(t)
    assert next(iter(_sizes(scenes).values())) == \
        pytest.approx(_expected(peaks, t, AMOUNT, offset=5.0))


@pytest.mark.parametrize("t", [-1.0, 40.0])
def test_a_time_outside_the_recording_sits_at_exactly_one(scenes, schedule,
                                                          t) -> None:
    """Before it starts (the applier's own pre-roll time is negative)
    and past what has been decoded, the reading is 0 — which is the
    engraved size exactly, not merely close to it."""
    applier = _applier(scenes, schedule,
                       StyleRules(pulse={"amount": AMOUNT}),
                       _loud_after(4.0, duration=20.0))
    applier.refresh(t)

    for group in scenes.system_groups.values():
        assert group.system_scale == 1.0
        assert group.sceneTransform().isIdentity()


# -- an unchanged value costs nothing ------------------------------------


def test_the_same_time_twice_writes_nothing_the_second_time(
        scenes, schedule, writes) -> None:
    applier = _applier(scenes, schedule,
                       StyleRules(pulse={"amount": AMOUNT}), _loud_after(4.0))
    n_groups = len(scenes.system_groups)
    writes.clear()

    applier.apply_at(6.0)
    assert len(writes) == n_groups             # every system, once
    writes.clear()

    applier.apply_at(6.0)
    assert writes == []


def test_silence_costs_no_writes(scenes, schedule, writes) -> None:
    """A quiet passage reads 0, which is one size, which is written once
    and then held — playing through it costs one lookup a frame and
    nothing else."""
    applier = _applier(scenes, schedule,
                       StyleRules(pulse={"amount": AMOUNT}), _silence())
    writes.clear()

    for step in range(30):
        applier.apply_at(step * 0.1)

    assert writes == []
    assert set(_sizes(scenes).values()) == {1.0}


# -- turning it off again ------------------------------------------------


def test_turning_it_off_puts_the_systems_back(scenes, schedule) -> None:
    """Amount 0 has to mean the engraved size, not whatever size the
    page happened to be breathing at when it was turned down."""
    applier = _applier(scenes, schedule,
                       StyleRules(pulse={"amount": AMOUNT}), _loud_after(4.0))
    applier.apply_at(6.0)
    assert next(iter(_sizes(scenes).values())) != 1.0

    applier.set_style(StyleRules(pulse={}))

    for group in scenes.system_groups.values():
        assert group.system_scale == 1.0
        assert group.sceneTransform().isIdentity()


# -- the onset pop -------------------------------------------------------


def test_a_pop_needs_no_recording_at_all(scenes, schedule) -> None:
    """The whole point of this mode: it is driven by the schedule, so it
    works with nothing loaded."""
    applier = _applier(scenes, schedule, StyleRules(pulse=POP))
    t = _busiest_beat(scenes, schedule, POP)
    applier.refresh(t)

    sizes = _sizes(scenes)
    assert sizes == pytest.approx(_expected_sizes(scenes, schedule, POP, t))
    assert max(sizes.values()) == pytest.approx(1.1)   # a full-strength beat


def test_only_the_system_the_notes_landed_in_bumps(scenes,
                                                   schedule) -> None:
    """Unlike the follow half, this one is per system: a page whose other
    systems are resting leaves them at exactly their engraved size."""
    applier = _applier(scenes, schedule, StyleRules(pulse=POP))
    applier.refresh(_busiest_beat(scenes, schedule, POP))

    sizes = _sizes(scenes)
    assert len(set(sizes.values())) > 1                # they really differ
    assert 1.0 in set(sizes.values())                  # some system rests
    assert max(sizes.values()) > 1.0


def test_a_bump_rises_at_the_beat_and_settles_back(scenes,
                                                   schedule) -> None:
    """Walked forward, the way playback reaches it: biggest at the beat,
    falling after it, and exactly back to engraved size by the settle."""
    applier = _applier(scenes, schedule, StyleRules(pulse=POP))
    t = _busiest_beat(scenes, schedule, POP)
    key = max(_expected_sizes(scenes, schedule, POP, t).items(),
              key=lambda kv: kv[1])[0]

    applier.apply_at(t - 0.5)
    before = _sizes(scenes)[key]
    walked = []
    for step in range(26):
        applier.apply_at(t + step * 0.01)
        walked.append(_sizes(scenes)[key])

    assert before == 1.0
    assert walked[0] == pytest.approx(1.1)             # up at the beat
    assert walked == sorted(walked, reverse=True)      # and only falling
    applier.apply_at(t + 0.25)
    assert _sizes(scenes)[key] == 1.0                  # gone at the settle


def test_scrubbing_a_bump_gives_the_same_size_as_arriving_fresh(
        qapp, engraved, schedule) -> None:
    """Rule 2 for the pop half, with no audio anywhere in it: walking to
    a time and jumping to it cold leave the page the same size."""
    style = StyleRules(pulse=POP)
    walked_scenes = _build_scenes(engraved)
    walked = _applier(walked_scenes, schedule, style)
    mid = _busiest_beat(walked_scenes, schedule, POP) + 0.11   # mid-bump

    rng = random.Random(23)
    t = 0.0
    for _ in range(40):
        t = max(-2.0, t + rng.uniform(-9.0, 11.0))
        walked.apply_at(t)
    for step in range(20):                             # and tick up to it
        walked.apply_at(mid - 0.4 + step * 0.02)
    walked.apply_at(mid)

    fresh_scenes = _build_scenes(engraved)
    fresh = _applier(fresh_scenes, schedule, style)
    fresh.refresh(mid)

    assert _sizes(walked_scenes) == _sizes(fresh_scenes)
    # non-vacuity: a bump really is mid-fall at `mid`
    assert 1.0 < max(_sizes(fresh_scenes).values()) < 1.1


def test_a_tempo_change_moves_every_bump(scenes, schedule) -> None:
    """Same beat, new seconds. The bumps are built where the trigger
    seconds are, so a tempo edit has to carry them along."""
    applier = _applier(scenes, schedule, StyleRules(pulse=POP))
    t = _busiest_beat(scenes, schedule, POP)
    applier.refresh(t)
    before = _sizes(scenes)
    assert max(before.values()) > 1.0                  # non-vacuity

    applier.set_timing(HALF_TEMPO)
    applier.refresh(t)
    assert set(_sizes(scenes).values()) == {1.0}       # nothing fires here now

    applier.refresh(t * 2.0)                           # the same beat, later
    assert _sizes(scenes) == pytest.approx(before)
    assert _sizes(scenes) == pytest.approx(
        _expected_sizes(scenes, schedule, POP, t * 2.0, tempo=HALF_TEMPO))


def test_the_settings_moving_rebuilds_the_bumps(scenes, schedule) -> None:
    """notes_for_full is what a strength is measured against, so turning
    it changes every bump without the beats moving at all."""
    applier = _applier(scenes, schedule, StyleRules(pulse=POP))
    t = _busiest_beat(scenes, schedule, POP)
    applier.refresh(t)
    at_four = _sizes(scenes)

    applier.set_style(StyleRules(pulse={**POP, "notes_for_full": 24}))
    applier.refresh(t)

    assert _sizes(scenes) != pytest.approx(at_four)
    assert _sizes(scenes) == pytest.approx(
        _expected_sizes(scenes, schedule, {**POP, "notes_for_full": 24}, t))


def test_a_resting_system_costs_no_writes(scenes, schedule,
                                          writes) -> None:
    """The saving is per group now: playing through a passage writes the
    system that just fired, not the whole page."""
    applier = _applier(scenes, schedule, StyleRules(pulse=POP))
    t = _busiest_beat(scenes, schedule, POP)
    applier.apply_at(t)
    writes.clear()

    applier.apply_at(t + 0.01)
    assert 0 < len(writes) < len(scenes.system_groups)


# -- both halves at once -------------------------------------------------


def test_the_two_halves_add_on_the_page(scenes, schedule) -> None:
    """A bump lands on top of however swollen the recording has the page
    already: the deviations add."""
    peaks = _loud_after(0.0)
    both = {"amount": AMOUNT, **POP}
    applier = _applier(scenes, schedule, StyleRules(pulse=both), peaks)
    t = _busiest_beat(scenes, schedule, POP)
    applier.refresh(t)
    sizes = _sizes(scenes)

    assert sizes == pytest.approx(
        _expected_sizes(scenes, schedule, both, t, peaks=peaks))
    follow_only = _expected(peaks, t, AMOUNT)
    assert min(sizes.values()) == pytest.approx(follow_only)
    assert max(sizes.values()) == pytest.approx(follow_only + 0.1)


def test_losing_the_recording_leaves_the_pop_alone(scenes,
                                                   schedule) -> None:
    """The pop half never reads the audio, so it must survive the
    recording going away."""
    both = {"amount": AMOUNT, **POP}
    applier = _applier(scenes, schedule, StyleRules(pulse=both),
                       _loud_after(0.0))
    t = _busiest_beat(scenes, schedule, POP)

    applier.set_audio(None, 0.0)
    applier.refresh(t)

    assert _sizes(scenes) == pytest.approx(
        _expected_sizes(scenes, schedule, both, t))
    assert max(_sizes(scenes).values()) == pytest.approx(1.1)


def test_losing_the_recording_puts_the_systems_back(scenes,
                                                    schedule) -> None:
    applier = _applier(scenes, schedule,
                       StyleRules(pulse={"amount": AMOUNT}), _loud_after(4.0))
    applier.apply_at(6.0)
    assert next(iter(_sizes(scenes).values())) != 1.0

    applier.set_audio(None, 0.0)

    assert set(_sizes(scenes).values()) == {1.0}
