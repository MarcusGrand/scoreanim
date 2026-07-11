"""AnimationApplier on the real fixture, offscreen: floor/full states,
statelessness under scrubbing, at-onset inclusivity, tie behavior, pages."""

import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import appear, build_trigger_schedule  # noqa: E402
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.timing import TempoEvent, TempoMap  # noqa: E402
from scoreanim.render.animate import AnimationApplier  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402

FLOOR = 0.3
TEMPO = TempoMap([TempoEvent(0.0, 120.0)])


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def schedule(engraved, join_mapping):
    return build_trigger_schedule(engraved.layout, join_mapping)


@pytest.fixture()
def scenes(qapp, engraved) -> ScoreScenes:
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    return ScoreScenes(engraved.layout, stage)


@pytest.fixture()
def applier(scenes, schedule) -> AnimationApplier:
    return AnimationApplier(scenes.items, schedule, TEMPO, appear(FLOOR))


def _opacities(scenes: ScoreScenes) -> dict:
    return {eid: item.opacity() for eid, item in scenes.items.items()}


def test_construction_leaves_preroll_state(scenes, schedule, applier) -> None:
    scheduled = set(schedule.beats_by_element)
    for eid, item in scenes.items.items():
        expected = FLOOR if eid in scheduled else 1.0
        assert item.opacity() == pytest.approx(expected), eid


def test_past_the_end_everything_full(scenes, schedule, applier) -> None:
    applier.refresh(1e6)
    assert all(item.opacity() == pytest.approx(1.0)
               for item in scenes.items.values())


def test_at_onset_inclusive(scenes, schedule, applier) -> None:
    trigger = schedule.triggers[5]
    exact_seconds = TEMPO.seconds_at(trigger.beats)
    applier.apply_at(exact_seconds)
    for eid in trigger.element_ids:
        assert scenes.items[eid].opacity() == pytest.approx(1.0), eid


def test_scrubbing_is_stateless(qapp, engraved, schedule, scenes) -> None:
    """A wild walk forward and back lands in exactly the state a fresh
    applier produces for the final t."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, appear(FLOOR))
    rng = random.Random(7)
    t = 0.0
    for _ in range(60):
        t = max(-2.0, t + rng.uniform(-9.0, 11.0))
        applier.apply_at(t)
    applier.apply_at(7.3)
    walked = _opacities(scenes)

    fresh_scenes = ScoreScenes(engraved.layout, default_stage_config(
        engraved.prepared, page_content_top(engraved.layout)))
    AnimationApplier(fresh_scenes.items, schedule, TEMPO,
                     appear(FLOOR)).refresh(7.3)
    assert walked == _opacities(fresh_scenes)


def test_tie_stop_lit_before_its_bar_and_never_restepped(
        scenes, schedule, applier, join_mapping) -> None:
    eid = next(e for e, n in join_mapping.items() if n.tie == "stop")
    note = join_mapping[eid]
    trigger_s = TEMPO.seconds_at(schedule.beats_by_element[eid])
    notated_s = TEMPO.seconds_at(note.onset)
    assert trigger_s < notated_s

    applier.apply_at((trigger_s + notated_s) / 2)      # mid-tie
    assert scenes.items[eid].opacity() == pytest.approx(1.0)
    applier.apply_at(notated_s + 0.01)                 # crossing notated onset
    assert scenes.items[eid].opacity() == pytest.approx(1.0)
    applier.apply_at(trigger_s - 0.01)                 # scrub before the chain
    assert scenes.items[eid].opacity() == pytest.approx(FLOOR)


def test_diff_apply_touches_only_crossed_triggers(scenes, schedule,
                                                  applier) -> None:
    applier.refresh(0.0)
    a = TEMPO.seconds_at(schedule.triggers[10].beats)
    b = TEMPO.seconds_at(schedule.triggers[12].beats)
    applier.apply_at(a)
    expected = sum(len([e for e in t.element_ids if e in scenes.items])
                   for t in schedule.triggers[11:13]
                   if TEMPO.seconds_at(t.beats) <= b)
    assert applier.apply_at(b) == expected
    assert applier.apply_at(b) == 0                    # same t: no work


def test_current_page_steps_through_the_score(schedule, applier) -> None:
    assert applier.current_page() == 1
    seen = [1]
    for trig in schedule.triggers:
        applier.apply_at(TEMPO.seconds_at(trig.beats))
        page = applier.current_page()
        if page != seen[-1]:
            seen.append(page)
    assert seen == [1, 2, 3]
    applier.apply_at(-1.0)
    assert applier.current_page() == 1
