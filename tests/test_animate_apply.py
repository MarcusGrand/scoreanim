"""AnimationApplier on the real fixture, offscreen: floor/full states,
statelessness under scrubbing, at-onset inclusivity, tie behavior, pages."""

import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import (FLOOR_OPACITY, StyleRules,  # noqa: E402
                                      build_trigger_schedule)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.timing import TempoEvent, TempoMap  # noqa: E402
from scoreanim.render.animate import AnimationApplier  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402

FLOOR = FLOOR_OPACITY
TEMPO = TempoMap([TempoEvent(0.0, 120.0)])


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def schedule(engraved, join_mapping, score_model):
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures)


@pytest.fixture()
def scenes(qapp, engraved) -> ScoreScenes:
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    return ScoreScenes(engraved.layout, stage)


@pytest.fixture()
def applier(scenes, schedule) -> AnimationApplier:
    return AnimationApplier(scenes.items, schedule, TEMPO, StyleRules())


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
    applier = AnimationApplier(scenes.items, schedule, TEMPO, StyleRules())
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
                     StyleRules()).refresh(7.3)
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


# -- swing (PHASES 4.4): warp slots in upstream of seconds_at ----------------

def test_swing_delays_exactly_the_offbeat_triggers(scenes, schedule) -> None:
    from scoreanim.core.timing import SwingRegion, resolve_seconds

    applier = AnimationApplier(scenes.items, schedule, TEMPO, StyleRules())
    region = SwingRegion((0.0, 8.0), 0.667)
    # an off-beat-eighth trigger inside the region (fixture has many)
    idx = next(i for i, b in enumerate(schedule.beat_values)
               if 0.0 <= b < 8.0 and b % 1.0 == 0.5)
    trigger = schedule.triggers[idx]
    straight_s = TEMPO.seconds_at(trigger.beats)
    swung_s = resolve_seconds([trigger.beats], TEMPO, (region,))[0]
    assert swung_s - straight_s == pytest.approx(0.167 * 0.5, abs=1e-9)

    applier.set_timing(TEMPO, (region,))
    mid = (straight_s + swung_s) / 2               # after straight, before swung
    applier.refresh(mid)
    for eid in trigger.element_ids:
        assert scenes.items[eid].opacity() == pytest.approx(FLOOR), eid
    applier.refresh(swung_s)                        # at-onset inclusive holds
    for eid in trigger.element_ids:
        assert scenes.items[eid].opacity() == pytest.approx(1.0), eid
    # on-beat triggers in the region are NOT moved
    on_beat = next(t for t in schedule.triggers
                   if 0.0 <= t.beats < 8.0 and t.beats % 1.0 == 0.0)
    assert resolve_seconds([on_beat.beats], TEMPO, (region,))[0] \
        == pytest.approx(TEMPO.seconds_at(on_beat.beats))


def test_scrubbing_stateless_with_swing(qapp, engraved, schedule,
                                        scenes) -> None:
    from scoreanim.core.timing import SwingRegion

    region = SwingRegion((0.0, 12.0), 0.62)
    applier = AnimationApplier(scenes.items, schedule, TEMPO, StyleRules())
    applier.set_timing(TEMPO, (region,))
    rng = random.Random(11)
    t = 0.0
    for _ in range(40):
        t = max(-2.0, t + rng.uniform(-9.0, 11.0))
        applier.apply_at(t)
    applier.apply_at(6.1)
    walked = _opacities(scenes)

    fresh_scenes = ScoreScenes(engraved.layout, default_stage_config(
        engraved.prepared, page_content_top(engraved.layout)))
    fresh = AnimationApplier(fresh_scenes.items, schedule, TEMPO,
                             StyleRules())
    fresh.set_timing(TEMPO, (region,))
    fresh.refresh(6.1)
    assert walked == _opacities(fresh_scenes)


# -- per-element effects, timed transition window, scale (PHASES 5.3) --------

def _timed_effect():
    """A pop-shaped test effect (NOT the 5.4 preset): opacity appear +
    a 0.25 s scale decay — exercises the transition window machinery."""
    from scoreanim.core.animation import (OPACITY, SCALE, Easing, Effect,
                                          Envelope, Keyframe)
    return Effect("testpop", {
        OPACITY: Envelope(initial=FLOOR,
                          keyframes=(Keyframe(0.0, 1.0, Easing.STEP),)),
        SCALE: Envelope(initial=1.0,
                        keyframes=(Keyframe(0.0, 1.25, Easing.STEP),
                                   Keyframe(0.25, 1.0, Easing.LINEAR))),
    })


@pytest.fixture()
def pop_rules(monkeypatch):
    from scoreanim.core.animation import ElementStyle, presets
    from scoreanim.core.score.identity import PartId

    monkeypatch.setitem(presets.PRESETS, "testpop", _timed_effect())
    return StyleRules(parts={PartId("P1"): ElementStyle(effect="testpop")})


def _p1_head_and_stem(scenes, schedule):
    from scoreanim.core.score.identity import ElementKind

    head = next(eid for eid in schedule.beats_by_element
                if scenes.items[eid].identity.kind is ElementKind.NOTEHEAD
                and scenes.items[eid].identity.part == "P1")
    stem = next(eid for eid in schedule.beats_by_element
                if scenes.items[eid].identity.kind is ElementKind.STEM
                and scenes.items[eid].identity.part == "P1")
    return head, stem


def test_timed_effect_scales_mid_window(scenes, schedule, pop_rules) -> None:
    """Mid-decay the notehead sits at the lerped scale; stems never
    scale (render-side kind rule); past the window everything is 1.0."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, pop_rules)
    head, stem = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])

    applier.apply_at(trig_s + 0.125)               # mid-decay
    assert scenes.items[head].scale() == pytest.approx(1.125)
    assert scenes.items[head].opacity() == pytest.approx(1.0)
    assert scenes.items[stem].scale() == pytest.approx(1.0)
    applier.apply_at(trig_s + 0.5)                 # window expired
    assert scenes.items[head].scale() == pytest.approx(1.0)
    applier.apply_at(trig_s - 0.5)                 # scrub back: pre-onset
    assert scenes.items[head].scale() == pytest.approx(1.0)
    assert scenes.items[head].opacity() == pytest.approx(FLOOR)


def test_seek_mid_pop_lands_and_advances(scenes, schedule,
                                         pop_rules) -> None:
    """refresh() must seed the transition window: a seek landing
    mid-decay paints the mid-scale AND subsequent ticks keep advancing
    it (Plan-agent finding 8)."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, pop_rules)
    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])

    applier.refresh(trig_s + 0.05)                 # seek mid-pop
    assert scenes.items[head].scale() == pytest.approx(1.2)
    applier.apply_at(trig_s + 0.20)                # tick without crossing
    assert scenes.items[head].scale() == pytest.approx(1.05)


def test_set_style_resets_stale_scale(scenes, schedule, pop_rules) -> None:
    applier = AnimationApplier(scenes.items, schedule, TEMPO, pop_rules)
    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    applier.apply_at(trig_s + 0.125)
    assert scenes.items[head].scale() == pytest.approx(1.125)
    applier.set_style(StyleRules())                # back to plain appear
    assert scenes.items[head].scale() == pytest.approx(1.0)
    assert scenes.items[head].opacity() == pytest.approx(1.0)


def test_scrubbing_stateless_with_timed_effect(qapp, engraved, schedule,
                                               scenes, pop_rules) -> None:
    """The random-walk statelessness pin extended to scale: landing
    mid-decay after a wild scrub equals a fresh refresh at that t."""
    def visual_state(sc):
        return {eid: (item.opacity(), item.scale())
                for eid, item in sc.items.items()}

    applier = AnimationApplier(scenes.items, schedule, TEMPO, pop_rules)
    rng = random.Random(23)
    t = 0.0
    for _ in range(60):
        t = max(-2.0, t + rng.uniform(-9.0, 11.0))
        applier.apply_at(t)
    head, _ = _p1_head_and_stem(scenes, schedule)
    final = TEMPO.seconds_at(schedule.beats_by_element[head]) + 0.1
    applier.apply_at(final)                        # land mid-decay
    walked = visual_state(scenes)

    fresh_scenes = ScoreScenes(engraved.layout, default_stage_config(
        engraved.prepared, page_content_top(engraved.layout)))
    AnimationApplier(fresh_scenes.items, schedule, TEMPO,
                     pop_rules).refresh(final)
    assert walked == visual_state(fresh_scenes)


def test_tinted_note_still_dims_and_appears(scenes, schedule) -> None:
    """Color and opacity are independent: tint mutates child brushes,
    animation opacity sits on the parent — a tinted note still floors
    before its trigger and lights at it."""
    from PySide6.QtGui import QColor

    from scoreanim.core.score.identity import PartId

    applier = AnimationApplier(scenes.items, schedule, TEMPO, StyleRules())
    head, _ = _p1_head_and_stem(scenes, schedule)
    scenes.set_part_color(PartId("P1"), QColor("#cc2222"))
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])

    applier.refresh(trig_s - 0.5)
    item = scenes.items[head]
    assert item.opacity() == pytest.approx(FLOOR)
    assert item.color.name() == "#cc2222"          # tint survives the floor
    applier.refresh(trig_s)
    assert item.opacity() == pytest.approx(1.0)
    assert item.color.name() == "#cc2222"
