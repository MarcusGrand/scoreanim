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


def test_document_floor_drives_pretrigger_opacity(scenes, schedule) -> None:
    """Phase 7.2: the floor is StyleRules intent. Floor 0 → un-triggered
    animated ink fully invisible while scaffold (never scheduled) stays
    at 1.0; a set_style floor change moves an existing applier."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO,
                               StyleRules(floor_opacity=0.0))
    scheduled = set(schedule.beats_by_element)
    for eid, item in scenes.items.items():
        expected = 0.0 if eid in scheduled else 1.0
        assert item.opacity() == pytest.approx(expected), eid
    applier.set_style(StyleRules(floor_opacity=0.75))
    for eid, item in scenes.items.items():
        expected = 0.75 if eid in scheduled else 1.0
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


def test_tie_stop_fills_in_at_its_own_onset(
        scenes, schedule, applier, join_mapping) -> None:
    """Grow-with-playhead (ruling A/B revised 2026-07-22): a tie-stop head
    lights at its OWN notated onset — it fills in as the playhead reaches
    its barline, no longer lit early at the chain start. Before its onset it
    sits at the ghost floor."""
    eid = next(e for e, n in join_mapping.items() if n.tie == "stop")
    note = join_mapping[eid]
    trigger_s = TEMPO.seconds_at(schedule.beats_by_element[eid])
    notated_s = TEMPO.seconds_at(note.onset)
    assert trigger_s == pytest.approx(notated_s)       # fires at its own onset

    applier.apply_at(notated_s - 0.5)                  # before its bar
    assert scenes.items[eid].opacity() == pytest.approx(FLOOR)
    applier.apply_at(notated_s + 0.01)                 # crossing notated onset
    assert scenes.items[eid].opacity() == pytest.approx(1.0)


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


def _capped(item, value: float) -> float:
    """What the applier should paint: the ceiling wins where there is
    one, which for a beamed stem is a scale barely over 1.0."""
    return value if item.scale_cap is None else min(value, item.scale_cap)


def test_timed_effect_scales_mid_window(scenes, schedule, pop_rules) -> None:
    """Mid-decay the note sits at the lerped scale — the stem included,
    turning around its own head and stopping at its beam; past the
    window everything is 1.0."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, pop_rules)
    head, stem = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])

    applier.apply_at(trig_s + 0.125)               # mid-decay
    assert scenes.items[head].scale() == pytest.approx(1.125)
    assert scenes.items[head].opacity() == pytest.approx(1.0)
    assert scenes.items[stem].scale() == pytest.approx(
        _capped(scenes.items[stem], 1.125))
    # the stem pivots on a head, not on its own middle
    assert scenes.items[stem].scale_pivot != scenes.items[stem].anchor
    applier.apply_at(trig_s + 0.5)                 # window expired
    assert scenes.items[head].scale() == pytest.approx(1.0)
    assert scenes.items[stem].scale() == pytest.approx(1.0)
    applier.apply_at(trig_s - 0.5)                 # scrub back: pre-onset
    assert scenes.items[head].scale() == pytest.approx(1.0)
    assert scenes.items[head].opacity() == pytest.approx(FLOOR)


def test_a_notehead_pops_about_its_own_centre(scenes, schedule,
                                              pop_rules) -> None:
    """Marcus, 2026-08-01: the pivot is the head's own centre, so a
    chord's heads each grow where they were engraved instead of sliding
    towards a shared point."""
    from scoreanim.core.score.identity import ElementKind
    heads = [i for i in scenes.items.values()
             if i.identity is not None
             and i.identity.kind is ElementKind.NOTEHEAD
             and i.scale_pivot is not None]
    assert heads
    for item in heads:
        assert item.scale_pivot == item.bbox.center()


def test_a_beamed_stem_swells_no_further_than_its_beam(scenes, schedule,
                                                       pop_rules) -> None:
    """Marcus, 2026-08-01: the stem pops with its note, but its ink must
    never come out the far side of the beam. The ceiling is pure policy
    (core/animation/stem_caps.py); the applier just clamps to it."""
    from scoreanim.core.score.identity import ElementKind
    applier = AnimationApplier(scenes.items, schedule, TEMPO, pop_rules)
    stem = next(i for eid, i in scenes.items.items()
                if i.identity is not None
                and i.identity.kind is ElementKind.STEM
                and i.identity.part == "P1"
                and i.scale_cap is not None
                and eid in schedule.beats_by_element)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[stem.element_key])

    assert stem.scale_cap < 1.125                  # there IS a ceiling here
    applier.apply_at(trig_s + 0.125)               # asks for 1.125
    assert stem.scale() == pytest.approx(stem.scale_cap)
    applier.apply_at(trig_s + 0.5)                 # window over: home again
    assert stem.scale() == pytest.approx(1.0)


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


# -- M4.6: note-value timescales, peak offset, retimed windows ---------------

def _visual_state(sc):
    return {eid: (item.opacity(), item.scale())
            for eid, item in sc.items.items()}


@pytest.fixture(scope="module")
def schedule_nv(engraved, join_mapping, score_model):
    """The M4.7 wiring shape: durations resolved and carried by the
    schedule."""
    from scoreanim.core.animation import resolve_durations
    durs = resolve_durations(engraved.layout, join_mapping,
                             engraved.note_durations, score_model.measures)
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures, durs)


_NV_RULES = StyleRules(default_effect="pop",
                       effect_params={"pop": {"note_value": True}})


def _head_with_duration(scenes, schedule, beats: float):
    from scoreanim.core.score.identity import ElementKind
    return next(
        eid for eid, d in schedule.duration_by_element.items()
        if d == beats
        and scenes.items[eid].identity.kind is ElementKind.NOTEHEAD)


def test_note_value_stretches_by_engraved_length(scenes,
                                                 schedule_nv) -> None:
    """At 120 bpm a dotted half (3 beats — testscore's longest note)
    settles over 1.5 s — still mid-scale at +1.0 s — where an eighth
    (0.25 s = the authored settle) has settled at once (F7:
    timescale = dur_seconds / effect.duration)."""
    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO, _NV_RULES)
    long_head = _head_with_duration(scenes, schedule_nv, 3.0)
    eighth = _head_with_duration(scenes, schedule_nv, 0.5)
    for eid in (long_head, eighth):
        trig_s = TEMPO.seconds_at(schedule_nv.beats_by_element[eid])
        applier.refresh(trig_s + 1.0)
        item = scenes.items[eid]
        if eid is long_head:             # 1.5 s window: 2/3 through
            assert item.scale() == pytest.approx(1.25 - 0.25 * (2 / 3))
        else:                            # 0.25 s window: long settled
            assert item.scale() == pytest.approx(1.0)
        assert item.opacity() == pytest.approx(1.0)


def test_scrub_through_stretched_settle_is_stateless(qapp, engraved,
                                                     schedule_nv,
                                                     scenes) -> None:
    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO, _NV_RULES)
    long_head = _head_with_duration(scenes, schedule_nv, 3.0)
    mid = TEMPO.seconds_at(schedule_nv.beats_by_element[long_head]) + 1.0
    rng = random.Random(31)
    t = 0.0
    for _ in range(60):
        t = max(-2.0, t + rng.uniform(-9.0, 11.0))
        applier.apply_at(t)
    applier.apply_at(mid)                       # land mid-stretch
    walked = _visual_state(scenes)

    fresh_scenes = ScoreScenes(engraved.layout, default_stage_config(
        engraved.prepared, page_content_top(engraved.layout)))
    AnimationApplier(fresh_scenes.items, schedule_nv, TEMPO,
                     _NV_RULES).refresh(mid)
    assert walked == _visual_state(fresh_scenes)


_FADE_RULES = StyleRules(default_effect="fade")


def test_fade_ramps_opacity_with_no_applier_change(scenes, schedule) -> None:
    """A timed OPACITY track rides the same transition window pop's
    timed SCALE track does — the applier never learned the word fade.
    At the onset the ink is still at the floor; a fifth of a second in
    the ease-out has it most of the way up; at 0.4 s it is full. A
    backward scrub puts it back (the window stays stateless)."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _FADE_RULES)
    trig = schedule.triggers[0]
    trig_s = TEMPO.seconds_at(trig.beats)
    eids = [eid for eid in trig.element_ids if eid in scenes.items]
    assert eids
    mid = FLOOR + 0.875 * (1.0 - FLOOR)

    def opacities():
        return [scenes.items[eid].opacity() for eid in eids]

    applier.refresh(trig_s)
    assert opacities() == pytest.approx([FLOOR] * len(eids))
    applier.apply_at(trig_s + 0.2)
    assert opacities() == pytest.approx([mid] * len(eids))
    applier.apply_at(trig_s + 0.4)
    assert opacities() == pytest.approx([1.0] * len(eids))
    applier.apply_at(trig_s + 0.2)
    assert opacities() == pytest.approx([mid] * len(eids))


def test_fade_stretches_over_the_note_value(scenes, schedule_nv) -> None:
    """The same generic timescale pop's settle uses: at 120 bpm a dotted
    half fades over 1.5 s — only part-way up at +0.75 s — where an
    eighth (0.25 s) is long full."""
    rules = StyleRules(default_effect="fade",
                       effect_params={"fade": {"note_value": True}})
    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO, rules)
    long_head = _head_with_duration(scenes, schedule_nv, 3.0)
    eighth = _head_with_duration(scenes, schedule_nv, 0.5)
    for eid in (long_head, eighth):
        trig_s = TEMPO.seconds_at(schedule_nv.beats_by_element[eid])
        applier.refresh(trig_s + 0.75)
        opacity = scenes.items[eid].opacity()
        if eid is long_head:             # 1.5 s ramp: halfway in time
            assert opacity == pytest.approx(FLOOR + 0.875 * (1.0 - FLOOR))
        else:
            assert opacity == pytest.approx(1.0)


def test_swell_runs_over_each_note_s_own_length(scenes,
                                                schedule_nv) -> None:
    """The swell's whole point, end to end: at 120 bpm a dotted half
    swells over 1.5 s, so it is at its top at +0.75 s and back to its
    engraved size at +1.5 s — while an eighth (0.25 s) topped out at
    +0.125 s and was home long before. Nothing here is swell-specific
    code: it is the same timescale pop and fade take."""
    applier = AnimationApplier(scenes.items, schedule_nv,
                               TEMPO, StyleRules(default_effect="swell"))
    long_head = _head_with_duration(scenes, schedule_nv, 3.0)
    eighth = _head_with_duration(scenes, schedule_nv, 0.5)
    long_trig = TEMPO.seconds_at(schedule_nv.beats_by_element[long_head])
    eighth_trig = TEMPO.seconds_at(schedule_nv.beats_by_element[eighth])

    applier.refresh(long_trig + 0.75)
    assert scenes.items[long_head].scale() == pytest.approx(1.4)
    applier.refresh(eighth_trig + 0.125)
    assert scenes.items[eighth].scale() == pytest.approx(1.4)

    # at the same distance past its own onset the short note is home and
    # the long one is only starting to grow
    applier.refresh(eighth_trig + 0.25)
    assert scenes.items[eighth].scale() == pytest.approx(1.0)
    applier.refresh(long_trig + 0.25)
    growing = scenes.items[long_head].scale()
    assert 1.0 < growing < 1.4
    applier.refresh(long_trig + 1.5)
    assert scenes.items[long_head].scale() == pytest.approx(1.0)
    # and the note is fully visible throughout, engraved size or not
    assert scenes.items[long_head].opacity() == pytest.approx(1.0)


def test_negative_shift_lights_early_page_cursor_unmoved(
        scenes, schedule) -> None:
    """F3: at peak offset −100 ms the whole effect — including the
    appearance — moves early, but the page cursor bisects UNSHIFTED
    trigger seconds, so the page turn does not move. A backward scrub
    un-lights the early ink (the lead window stays stateless)."""
    rules = StyleRules(default_effect="pop",
                       effect_params={"pop": {"peak_offset": -0.1}})
    applier = AnimationApplier(scenes.items, schedule, TEMPO, rules)
    i2 = next(i for i, tr in enumerate(schedule.triggers) if tr.page == 2)
    tr_s = TEMPO.seconds_at(schedule.triggers[i2].beats)
    applier.refresh(tr_s - 1.0)                 # settle far before
    applier.apply_at(tr_s - 0.05)               # inside the shifted window
    for eid in schedule.triggers[i2].element_ids:
        assert scenes.items[eid].opacity() == pytest.approx(1.0), eid
    assert applier.current_page() == 1          # trigger NOT crossed
    applier.apply_at(tr_s - 0.5)                # scrub back out of the lead
    for eid in schedule.triggers[i2].element_ids:
        assert scenes.items[eid].opacity() == pytest.approx(FLOOR), eid


def test_bpm_change_retimes_the_stretch(qapp, engraved,
                                        schedule_nv, scenes) -> None:
    """set_timing recomputes note-value windows: after a tempo change
    the walked scene equals a FRESH applier built at the new tempo."""
    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO, _NV_RULES)
    long_head = _head_with_duration(scenes, schedule_nv, 3.0)
    slow = TempoMap([TempoEvent(0.0, 60.0)])    # 3 beats now 3.0 s
    mid = slow.seconds_at(schedule_nv.beats_by_element[long_head]) + 1.0
    applier.apply_at(mid)                       # state under the OLD map
    applier.set_timing(slow)
    applier.refresh(mid)
    walked = _visual_state(scenes)
    # a third through the 3 s window: lerp 1/3 done
    assert scenes.items[long_head].scale() == pytest.approx(
        1.25 - 0.25 * (1 / 3))

    fresh_scenes = ScoreScenes(engraved.layout, default_stage_config(
        engraved.prepared, page_content_top(engraved.layout)))
    fresh = AnimationApplier(fresh_scenes.items, schedule_nv, slow,
                             _NV_RULES)
    fresh.refresh(mid)
    assert walked == _visual_state(fresh_scenes)


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


# -- drop: two timed tracks at once, still no applier change ----------------

_DROP_RULES = StyleRules(default_effect="drop")


def test_drop_shrinks_and_solidifies_with_no_applier_change(
        scenes, schedule) -> None:
    """A timed SCALE track and a timed OPACITY track ride the one
    transition window together — the applier never learned the word
    drop. The note enters oversized and part-way solid, touches its
    engraved size, bounces back up, and comes to rest full."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _DROP_RULES)
    head, stem = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])

    applier.refresh(trig_s)                        # the moment it enters
    assert scenes.items[head].scale() == pytest.approx(3.0)
    assert scenes.items[head].opacity() == pytest.approx(0.3)
    # the stem drops with it, out of a head and no further than its beam
    assert scenes.items[stem].scale() == pytest.approx(
        _capped(scenes.items[stem], 3.0))
    assert scenes.items[stem].scale_pivot is not None
    applier.apply_at(trig_s + 0.35 / 2.75)         # first landing
    assert scenes.items[head].scale() == pytest.approx(1.0)
    applier.apply_at(trig_s + 0.35 * 1.5 / 2.75)   # bounced back up
    assert scenes.items[head].scale() == pytest.approx(1.5)
    applier.apply_at(trig_s + 1.0)                 # window over
    assert scenes.items[head].scale() == pytest.approx(1.0)
    assert scenes.items[head].opacity() == pytest.approx(1.0)
    applier.apply_at(trig_s - 0.5)                 # scrub back before it
    assert scenes.items[head].scale() == pytest.approx(1.0)
    assert scenes.items[head].opacity() == pytest.approx(FLOOR)


def _beamed_group(scenes):
    """A beamed group on the fixture: its beam, the head of the note the
    beam starts on, and a head that comes later under the same beam."""
    from scoreanim.core.score.identity import ElementKind
    heads = [i for i in scenes.items.values()
             if i.identity is not None
             and i.identity.kind is ElementKind.NOTEHEAD
             and i.identity.onset is not None]
    for item in scenes.items.values():
        ident = item.identity
        if (ident is None or ident.kind is not ElementKind.BEAM
                or ident.extent is None or ident.onset is None):
            continue
        mine = [h for h in heads
                if (h.identity.part, h.identity.staff, h.identity.voice)
                == (ident.part, ident.staff, ident.voice)
                and ident.extent[0] <= h.identity.onset <= ident.extent[1]]
        first = [h for h in mine if h.identity.onset == ident.onset]
        # an eighth or more later, so the beam is genuinely further along
        # its drop by the time that note takes its turn
        later = [h for h in mine if h.identity.onset >= ident.onset + 0.5]
        if first and later:
            return (item, first[0],
                    min(later, key=lambda h: h.identity.onset))
    raise AssertionError("no beamed group in the fixture")


def test_a_beam_appears_with_its_note_but_never_grows(scenes,
                                                      schedule) -> None:
    """Marcus's rule for beams (2026-08-01): a beam comes in with the
    note it starts on, straight at its engraved size. It belongs to
    several notes at once, so it never scales — the notes under it do."""
    beam, first, later = _beamed_group(scenes)
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _DROP_RULES)
    first_s = TEMPO.seconds_at(schedule.beats_by_element[first.element_key])
    later_s = TEMPO.seconds_at(schedule.beats_by_element[later.element_key])
    assert later_s > first_s
    assert beam.scale_pivot is None                # never scales at all

    applier.refresh(first_s - 0.5)
    assert beam.opacity() == pytest.approx(FLOOR)  # a ghost before its turn
    applier.refresh(first_s)
    assert beam.scale() == 1.0                     # full size, straight away
    assert beam.opacity() == pytest.approx(0.3)    # it appears with note 1
    assert first.scale() == pytest.approx(3.0)     # which is still growing
    assert later.scale() == pytest.approx(1.0)     # not its turn yet
    assert later.opacity() == pytest.approx(FLOOR)

    applier.refresh(later_s)
    assert later.scale() == pytest.approx(3.0)     # now it drops
    assert beam.scale() == 1.0                     # and the beam sits still


def test_a_ledger_line_fades_in_but_never_grows(scenes, schedule) -> None:
    """Marcus, 2026-07-31: a ledger line is ruled at staff size and stays
    that size while its note drops onto it — but it still fades in with
    the note, like any animated ink."""
    from scoreanim.core.score.identity import ElementKind
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _DROP_RULES)
    dash = next(item for eid, item in scenes.items.items()
                if item.identity is not None
                and item.identity.kind is ElementKind.LEDGER_LINES
                and eid in schedule.beats_by_element)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[dash.element_key])

    applier.refresh(trig_s - 0.5)
    assert dash.opacity() == pytest.approx(FLOOR)    # a ghost, at its size
    assert dash.scale() == 1.0
    applier.refresh(trig_s)                          # its note is 3× here
    assert dash.opacity() == pytest.approx(0.3)      # fading in with it
    assert dash.scale() == 1.0
    applier.refresh(trig_s + 1.0)
    assert dash.opacity() == pytest.approx(1.0)
    assert dash.scale() == 1.0


def test_note_value_stretch_keeps_a_note_together(scenes,
                                                  schedule_nv) -> None:
    """durations.py hands a stem its notehead group's length, so a
    stretched settle moves head and stem at the same rate."""
    from scoreanim.core.score.identity import ElementKind
    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO, _NV_RULES)
    head = _head_with_duration(scenes, schedule_nv, 3.0)
    ident = scenes.items[head].identity
    stem = next(item for item in scenes.items.values()
                if item.identity is not None
                and item.identity.kind is ElementKind.STEM
                and (item.identity.part, item.identity.staff,
                     item.identity.voice, item.identity.onset)
                == (ident.part, ident.staff, ident.voice, ident.onset))
    trig_s = TEMPO.seconds_at(schedule_nv.beats_by_element[head])
    applier.refresh(trig_s + 1.0)                  # 2/3 through the stretch
    assert scenes.items[head].scale() > 1.0        # genuinely mid-stretch
    assert stem.scale() == pytest.approx(scenes.items[head].scale())


# -- slide: two NEW properties, composed with the document's own nudge ------

_SLIDE_RULES = StyleRules(default_effect="slide")


def _positions(sc):
    return {eid: (item.pos().x(), item.pos().y())
            for eid, item in sc.items.items()}


def test_slide_travels_in_and_lands_exactly_in_place(scenes,
                                                     schedule) -> None:
    """The default slide: the note appears at its trigger 120 units above
    its place and eases down onto it. Nothing sits away from its place
    before the trigger or after the window."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _SLIDE_RULES)
    head, stem = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    item = scenes.items[head]

    applier.refresh(trig_s - 0.5)                  # a ghost, in its place
    assert item.pos().y() == 0.0
    assert item.opacity() == pytest.approx(FLOOR)
    applier.refresh(trig_s)                        # it enters, up the page
    assert item.pos().y() == pytest.approx(-120.0)
    assert item.pos().x() == 0.0
    assert item.opacity() == pytest.approx(1.0)
    assert scenes.items[stem].pos().y() == pytest.approx(-120.0)
    applier.apply_at(trig_s + 0.175)               # most of the way home
    assert item.pos().y() == pytest.approx(-15.0)
    applier.apply_at(trig_s + 1.0)                 # window over
    assert (item.pos().x(), item.pos().y()) == (0.0, 0.0)
    applier.apply_at(trig_s - 0.5)                 # scrub back before it
    assert (item.pos().x(), item.pos().y()) == (0.0, 0.0)


def test_slide_direction_reaches_both_axes(scenes, schedule) -> None:
    rules = StyleRules(default_effect="slide",
                       effect_params={"slide": {"direction": 270,
                                                "distance": 300.0}})
    applier = AnimationApplier(scenes.items, schedule, TEMPO, rules)
    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    applier.refresh(trig_s)
    item = scenes.items[head]
    assert item.pos().x() == pytest.approx(-300.0)     # in from the left
    assert item.pos().y() == pytest.approx(0.0)


def test_a_slide_never_fights_the_document_nudge(scenes, schedule) -> None:
    """The trap: the nudge owns the position too. A nudged note must
    slide to its NUDGED place, and end there exactly."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _SLIDE_RULES)
    head, _ = _p1_head_and_stem(scenes, schedule)
    item = scenes.items[head]
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])

    scenes.set_element_offset(head, 12.0, -4.0)
    applier.refresh(trig_s)                        # mid-slide, nudged
    assert (item.pos().x(), item.pos().y()) == pytest.approx((12.0, -124.0))
    applier.apply_at(trig_s + 1.0)                 # landed, still nudged
    assert (item.pos().x(), item.pos().y()) == pytest.approx((12.0, -4.0))
    # and the nudge still moves it while the animation holds an offset
    applier.refresh(trig_s)
    scenes.set_element_offset(head, 0.0, 0.0)
    assert (item.pos().x(), item.pos().y()) == pytest.approx((0.0, -120.0))


def test_set_style_resets_a_stale_slide(scenes, schedule) -> None:
    """An element whose effect lost its offset tracks snaps back into
    place, the way a lost scale track does."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _SLIDE_RULES)
    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    applier.apply_at(trig_s)
    assert scenes.items[head].pos().y() == pytest.approx(-120.0)
    applier.set_style(StyleRules())                # back to plain appear
    assert scenes.items[head].animated_offset == (0.0, 0.0)
    assert (scenes.items[head].pos().x(),
            scenes.items[head].pos().y()) == (0.0, 0.0)


def test_scrubbing_a_slide_is_stateless(qapp, engraved, schedule,
                                        scenes) -> None:
    """The check Marcus asked for, headless: however wildly the playhead
    is scrubbed, every note is where a fresh applier would put it — and
    past the end every one of them is exactly in place."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _SLIDE_RULES)
    head, _ = _p1_head_and_stem(scenes, schedule)
    mid = TEMPO.seconds_at(schedule.beats_by_element[head]) + 0.1
    rng = random.Random(13)
    t = 0.0
    for _ in range(60):
        t = max(-2.0, t + rng.uniform(-9.0, 11.0))
        applier.apply_at(t)
    applier.apply_at(mid)                          # land mid-slide
    assert scenes.items[head].pos().y() != 0.0     # genuinely travelling
    walked = _positions(scenes)

    fresh_scenes = ScoreScenes(engraved.layout, default_stage_config(
        engraved.prepared, page_content_top(engraved.layout)))
    AnimationApplier(fresh_scenes.items, schedule, TEMPO,
                     _SLIDE_RULES).refresh(mid)
    assert walked == _positions(fresh_scenes)

    applier.apply_at(1e6)
    for eid, item in scenes.items.items():
        assert (item.pos().x(), item.pos().y()) == (0.0, 0.0), eid


def test_drop_leaves_every_played_note_at_its_size(scenes, schedule) -> None:
    """The check Marcus asked for, headless: however wildly the playhead
    is scrubbed, nothing is left oversized. Past the end every element
    sits at exactly its engraved size, fully solid."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _DROP_RULES)
    rng = random.Random(11)
    t = 0.0
    for _ in range(40):
        t = max(-2.0, t + rng.uniform(-9.0, 11.0))
        applier.apply_at(t)
    applier.apply_at(1e6)
    for eid, item in scenes.items.items():
        assert item.scale() == pytest.approx(1.0), eid
        assert item.opacity() == pytest.approx(1.0), eid


# -- effects that run together ("drop+fade") ---------------------------------

def test_a_single_effect_states_exactly_as_it_did_before(scenes,
                                                         schedule) -> None:
    """The bit-identical pin: with one effect the applier's state must
    equal the plain kernel's, evaluated straight off the preset."""
    from scoreanim.core.animation import (OPACITY, PRESETS, SCALE,
                                          element_state)
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _DROP_RULES)
    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    for dt in (-0.5, 0.0, 0.1, 0.2, 0.35, 1.0):
        applier.refresh(trig_s + dt)
        want = element_state(trig_s, PRESETS["drop"], trig_s + dt)
        assert scenes.items[head].opacity() == pytest.approx(want[OPACITY])
        assert scenes.items[head].scale() == pytest.approx(want[SCALE])


def test_drop_and_fade_run_together(scenes, schedule) -> None:
    """A combined name: the note lands like a stamp AND rises out of the
    ghost. The scale is drop's; the opacity is the dimmer of the two,
    which through the whole entry is fade's."""
    from scoreanim.core.animation import (OPACITY, PRESETS, SCALE,
                                          element_state)
    rules = StyleRules(default_effect="drop+fade")
    applier = AnimationApplier(scenes.items, schedule, TEMPO, rules)
    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    item = scenes.items[head]

    applier.refresh(trig_s - 0.5)                  # a ghost, AT the floor
    assert item.opacity() == pytest.approx(FLOOR)  # not FLOOR squared
    assert item.scale() == pytest.approx(1.0)
    applier.refresh(trig_s)                        # enters big, still dim
    assert item.scale() == pytest.approx(3.0)
    assert item.opacity() == pytest.approx(FLOOR)
    applier.apply_at(trig_s + 0.2)                 # mid-entry
    assert item.scale() == pytest.approx(
        element_state(trig_s, PRESETS["drop"], trig_s + 0.2)[SCALE])
    assert item.opacity() == pytest.approx(
        element_state(trig_s, PRESETS["fade"], trig_s + 0.2)[OPACITY])
    applier.apply_at(trig_s + 1.0)                 # both windows over
    assert item.scale() == pytest.approx(1.0)
    assert item.opacity() == pytest.approx(1.0)
    applier.apply_at(trig_s - 0.5)                 # scrub back: a ghost
    assert item.opacity() == pytest.approx(FLOOR)
    assert item.scale() == pytest.approx(1.0)


def test_slide_and_fade_run_together(scenes, schedule) -> None:
    """Two effects touching different properties: the offsets are
    slide's, the opacity fade's."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO,
                               StyleRules(default_effect="slide+fade"))
    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    item = scenes.items[head]

    applier.refresh(trig_s)
    assert item.pos().y() == pytest.approx(-120.0)
    assert item.opacity() == pytest.approx(FLOOR)   # slide alone would be 1
    applier.apply_at(trig_s + 1.0)
    assert (item.pos().x(), item.pos().y()) == (0.0, 0.0)
    assert item.opacity() == pytest.approx(1.0)


def test_the_window_covers_the_longest_component(scenes, schedule) -> None:
    """Components with different durations AND different shifts: the
    trigger's window reaches the far end of the slowest one, and the
    lead reaches the earliest one. Pop is shifted −0.3 s and settles in
    0.1 s; fade runs 2 s from the trigger."""
    rules = StyleRules(default_effect="pop+fade",
                       effect_params={"pop": {"peak_offset": -0.3,
                                              "settle": 0.1},
                                      "fade": {"duration": 2.0}})
    applier = AnimationApplier(scenes.items, schedule, TEMPO, rules)
    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    item = scenes.items[head]

    applier.refresh(trig_s - 1.0)                  # before everything
    assert item.opacity() == pytest.approx(FLOOR)
    # the lead: pop has already fired 0.2 s before the trigger, and its
    # opacity step rides the shift, so the note is lit — but fade is
    # dimmer at its own t=0, so the floor still wins
    applier.apply_at(trig_s - 0.2)
    assert item.scale() == pytest.approx(1.0)      # pop settled in 0.1 s
    assert item.opacity() == pytest.approx(FLOOR)
    # the window: 1.5 s in, fade is still climbing and must be re-evaluated
    applier.apply_at(trig_s + 1.5)
    assert FLOOR < item.opacity() < 1.0
    applier.apply_at(trig_s + 2.0)
    assert item.opacity() == pytest.approx(1.0)


def test_a_combination_can_stretch_only_one_component(scenes,
                                                      schedule_nv) -> None:
    """Each component keeps its OWN timescale: pop settles over the
    note's engraved length while fade runs at its authored 0.4 s."""
    rules = StyleRules(default_effect="pop+fade",
                       effect_params={"pop": {"note_value": True}})
    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO, rules)
    long_head = _head_with_duration(scenes, schedule_nv, 3.0)
    trig_s = TEMPO.seconds_at(schedule_nv.beats_by_element[long_head])
    item = scenes.items[long_head]

    applier.refresh(trig_s + 1.0)                  # 2/3 into a 1.5 s settle
    assert item.scale() == pytest.approx(1.25 - 0.25 * (2 / 3))
    assert item.opacity() == pytest.approx(1.0)    # fade finished at 0.4 s


def test_set_style_resets_a_stale_combination(scenes, schedule) -> None:
    """Leaving a combination that carried scale AND offsets for a plain
    fade puts both back: nothing is left oversized or off its place."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO,
                               StyleRules(default_effect="drop+slide"))
    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    applier.apply_at(trig_s)
    assert scenes.items[head].scale() == pytest.approx(3.0)
    assert scenes.items[head].pos().y() == pytest.approx(-120.0)

    applier.set_style(_FADE_RULES)
    assert scenes.items[head].scale() == pytest.approx(1.0)
    assert scenes.items[head].animated_offset == (0.0, 0.0)


def test_scrubbing_a_combination_is_stateless(qapp, engraved, schedule,
                                              scenes) -> None:
    """The statelessness pin, on a combination: however wildly the
    playhead is scrubbed, every note is where a fresh applier would put
    it, and past the end nothing is left oversized or out of place."""
    rules = StyleRules(default_effect="drop+slide")
    applier = AnimationApplier(scenes.items, schedule, TEMPO, rules)
    head, _ = _p1_head_and_stem(scenes, schedule)
    mid = TEMPO.seconds_at(schedule.beats_by_element[head]) + 0.1
    rng = random.Random(17)
    t = 0.0
    for _ in range(60):
        t = max(-2.0, t + rng.uniform(-9.0, 11.0))
        applier.apply_at(t)
    applier.apply_at(mid)
    assert scenes.items[head].scale() > 1.0        # genuinely mid-entry
    walked = _visual_state(scenes), _positions(scenes)

    fresh_scenes = ScoreScenes(engraved.layout, default_stage_config(
        engraved.prepared, page_content_top(engraved.layout)))
    AnimationApplier(fresh_scenes.items, schedule, TEMPO,
                     rules).refresh(mid)
    assert walked == (_visual_state(fresh_scenes), _positions(fresh_scenes))

    applier.apply_at(1e6)
    for eid, item in scenes.items.items():
        assert item.scale() == pytest.approx(1.0), eid
        assert (item.pos().x(), item.pos().y()) == (0.0, 0.0), eid


# -- the volume response ---------------------------------------------------

def _loud_at(seconds, duration=30.0, rate=44100):
    """A cache that is loud at each of `seconds` and silent elsewhere."""
    import numpy as np

    from scoreanim.core.audio import PeakCacheBuilder

    samples = np.zeros(int(duration * rate), dtype=np.float32)
    for start in seconds:
        lo = int(start * rate)
        samples[lo:lo + int(0.1 * rate)] = 1.0
    builder = PeakCacheBuilder(rate)
    builder.add_samples(samples)
    return builder.snapshot()


def _two_p1_heads(scenes, schedule):
    """Two noteheads in P1 on different beats — the pair whose loudness
    the tests below make differ."""
    from scoreanim.core.score.identity import ElementKind

    heads = sorted(
        (eid for eid in schedule.beats_by_element
         if scenes.items[eid].identity.kind is ElementKind.NOTEHEAD
         and scenes.items[eid].identity.part == "P1"),
        key=lambda eid: schedule.beats_by_element[eid])
    first = heads[0]
    later = next(eid for eid in heads
                 if schedule.beats_by_element[eid]
                 > schedule.beats_by_element[first] + 0.5)
    return first, later


def _full_state(scenes):
    return {eid: (item.opacity(), item.scale(), item.animated_offset)
            for eid, item in scenes.items.items()}


def test_no_audio_leaves_every_state_exactly_as_it_was(scenes, schedule,
                                                       pop_rules) -> None:
    """With no recording the applier must be bit-for-bit what it was
    before the volume response existed — even with the response turned
    all the way up."""
    from dataclasses import replace

    rules = replace(pop_rules, volume={"amount": 1.0})
    applier = AnimationApplier(scenes.items, schedule, TEMPO, rules)
    head, _ = _p1_head_and_stem(scenes, schedule)
    t = TEMPO.seconds_at(schedule.beats_by_element[head]) + 0.125
    applier.apply_at(t)
    before = _full_state(scenes)
    applier.set_audio(None, 0.0)
    applier.refresh(t)
    assert _full_state(scenes) == before


def test_amount_zero_leaves_every_state_exactly_as_it_was(scenes, schedule,
                                                          pop_rules) -> None:
    """The same guarantee from the other side: a recording is loaded,
    but the response is off. Not approximately equal — equal."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, pop_rules)
    head, _ = _p1_head_and_stem(scenes, schedule)
    t = TEMPO.seconds_at(schedule.beats_by_element[head]) + 0.125
    applier.apply_at(t)
    before = _full_state(scenes)
    applier.set_audio(_loud_at([t - 0.125]), 0.0)
    applier.refresh(t)
    assert _full_state(scenes) == before


def test_a_loud_beat_pops_harder_than_a_quiet_one(scenes, schedule,
                                                  pop_rules) -> None:
    """The feature itself. testpop jumps to 1.25 and settles over
    0.25 s, so mid-decay it sits at 1.125 — a departure of 0.125 from
    rest. At gain 1.5 that departure becomes 0.1875, at gain 0.5 it
    becomes 0.0625."""
    from dataclasses import replace

    loud_head, quiet_head = _two_p1_heads(scenes, schedule)
    loud_s = TEMPO.seconds_at(schedule.beats_by_element[loud_head])
    quiet_s = TEMPO.seconds_at(schedule.beats_by_element[quiet_head])
    rules = replace(pop_rules,
                    volume={"amount": 1.0, "quiet": 0.5, "loud": 1.5})
    applier = AnimationApplier(scenes.items, schedule, TEMPO, rules)
    applier.set_audio(_loud_at([loud_s]), 0.0)

    applier.refresh(loud_s + 0.125)
    loud_scale = scenes.items[loud_head].scale()
    applier.refresh(quiet_s + 0.125)
    quiet_scale = scenes.items[quiet_head].scale()

    # non-vacuity: the two beats must genuinely differ in loudness, or
    # this test would pass on a dead sample forever
    assert loud_scale != pytest.approx(quiet_scale)
    assert loud_scale == pytest.approx(1.0 + 0.125 * 1.5)
    assert quiet_scale == pytest.approx(1.0 + 0.125 * 0.5)


def test_a_quiet_note_still_becomes_fully_visible(scenes, schedule,
                                                  pop_rules) -> None:
    """Opacity is never modulated: the score has to stay readable
    wherever the playing is soft."""
    from dataclasses import replace

    loud_head, quiet_head = _two_p1_heads(scenes, schedule)
    loud_s = TEMPO.seconds_at(schedule.beats_by_element[loud_head])
    quiet_s = TEMPO.seconds_at(schedule.beats_by_element[quiet_head])
    rules = replace(pop_rules,
                    volume={"amount": 1.0, "quiet": 0.1, "loud": 2.0})
    applier = AnimationApplier(scenes.items, schedule, TEMPO, rules)
    applier.set_audio(_loud_at([loud_s]), 0.0)

    applier.refresh(quiet_s + 0.05)
    assert scenes.items[quiet_head].opacity() == pytest.approx(1.0)
    applier.refresh(loud_s + 0.05)
    assert scenes.items[loud_head].opacity() == pytest.approx(1.0)


def test_the_offset_moves_which_part_of_the_recording_is_read(
        scenes, schedule, pop_rules) -> None:
    """Triggers carry score seconds; the cache is indexed from the start
    of the sound file. Move the offset and a beat lands on a different
    moment of the waveform."""
    from dataclasses import replace

    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    rules = replace(pop_rules,
                    volume={"amount": 1.0, "quiet": 0.5, "loud": 1.5})
    applier = AnimationApplier(scenes.items, schedule, TEMPO, rules)
    # the burst sits 2 s into the recording; at offset 0 the beat misses
    # it, at offset 2 it lands on it
    applier.set_audio(_loud_at([trig_s + 2.0]), 0.0)
    applier.refresh(trig_s + 0.125)
    assert scenes.items[head].scale() == pytest.approx(1.0 + 0.125 * 0.5)
    applier.set_audio(_loud_at([trig_s + 2.0]), 2.0)
    applier.refresh(trig_s + 0.125)
    assert scenes.items[head].scale() == pytest.approx(1.0 + 0.125 * 1.5)


def test_settings_and_tempo_both_move_the_gains(scenes, schedule,
                                                pop_rules) -> None:
    """The three seams that can move a gain: the audio, the settings and
    the seconds axis. set_style and set_timing must both re-read."""
    from dataclasses import replace

    head, _ = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    applier = AnimationApplier(scenes.items, schedule, TEMPO, pop_rules)
    applier.set_audio(_loud_at([trig_s]), 0.0)
    applier.refresh(trig_s + 0.125)
    assert scenes.items[head].scale() == pytest.approx(1.125)   # off

    louder = replace(pop_rules,
                     volume={"amount": 1.0, "quiet": 0.5, "loud": 1.5})
    applier.set_style(louder)
    applier.refresh(trig_s + 0.125)
    assert scenes.items[head].scale() == pytest.approx(1.0 + 0.125 * 1.5)

    # half tempo: the beat now falls at twice the second, off the burst
    slow = TempoMap([TempoEvent(0.0, 60.0)])
    applier.set_timing(slow)
    slow_s = slow.seconds_at(schedule.beats_by_element[head])
    assert slow_s != pytest.approx(trig_s)          # non-vacuity
    applier.refresh(slow_s + 0.125)
    assert scenes.items[head].scale() == pytest.approx(1.0 + 0.125 * 0.5)


# -- the gain follows each element's own duration (2026-08-01) -----------------

def _quiet_after(seconds: float, duration: float = 12.0, rate: int = 44100):
    """A recording that is loud up to `seconds` and near-silent after —
    so how much of it a note reads depends on how long the note is."""
    import numpy as np

    from scoreanim.core.audio import PeakCacheBuilder

    samples = np.full(int(duration * rate), 0.02, dtype=np.float32)
    samples[:int(seconds * rate)] = 1.0
    builder = PeakCacheBuilder(rate)
    builder.add_samples(samples)
    return builder.snapshot()


def _mixed_duration_trigger(scenes, schedule):
    """A trigger carrying two noteheads of DIFFERENT notated length —
    testscore has one at beat 6 (a quarter against a dotted quarter)."""
    from scoreanim.core.score.identity import ElementKind

    durs = schedule.duration_by_element
    for i, trig in enumerate(schedule.triggers):
        heads = {eid: durs[eid] for eid in trig.element_ids
                 if eid in durs and eid in scenes.items
                 and scenes.items[eid].identity.kind is ElementKind.NOTEHEAD}
        if len(set(heads.values())) > 1:
            by_length = sorted(heads.items(), key=lambda kv: kv[1])
            return i, by_length[0], by_length[-1]
    raise AssertionError("no trigger carries two different note lengths")


def test_two_notes_on_one_beat_pop_by_their_own_lengths(scenes,
                                                        schedule_nv) -> None:
    """The feature. Two noteheads fire on the same beat, one shorter
    than the other, over a recording that is loud at that beat and quiet
    after. The short note reads only the loud part, the long note
    averages the quiet in — so they pop by different amounts, which a
    per-trigger gain could never do."""
    i, (short, short_beats), (long, long_beats) = \
        _mixed_duration_trigger(scenes, schedule_nv)
    trig_s = TEMPO.seconds_at(schedule_nv.triggers[i].beats)
    short_s = TEMPO.seconds_at(schedule_nv.triggers[i].beats + short_beats)
    assert long_beats > short_beats                       # non-vacuity

    rules = StyleRules(default_effect="pop",
                       volume={"amount": 1.0, "quiet": 0.5, "loud": 1.5})
    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO, rules)
    applier.set_audio(_quiet_after(short_s), 0.0)
    applier.refresh(trig_s + 0.05)

    short_scale = scenes.items[short].scale()
    long_scale = scenes.items[long].scale()
    assert short_scale > long_scale
    # the short note read the loud part alone, so it sits at the loud end
    assert short_scale > 1.0


def test_gains_are_one_per_element_not_one_per_trigger(scenes,
                                                       schedule_nv) -> None:
    """A structural pin: the gains are shaped like the items, so a
    future change cannot quietly go back to one number per beat."""
    i, (_, short_beats), _ = _mixed_duration_trigger(scenes, schedule_nv)
    short_s = TEMPO.seconds_at(schedule_nv.triggers[i].beats + short_beats)

    rules = StyleRules(default_effect="pop", volume={"amount": 1.0})
    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO, rules)
    applier.set_audio(_quiet_after(short_s), 0.0)
    gains = applier._audio.gains
    assert gains is not None
    assert [len(row) for row in gains] \
        == [len(items) for items in applier._index.items]
    assert len(set(gains[i])) > 1          # they really do differ


def test_ink_with_no_notated_length_still_reads_the_attack(scenes,
                                                           schedule_nv,
                                                           schedule) -> None:
    """Dynamics, texts and rests never enter the duration map, so they
    get exactly the reading every element used to get. Pinned against a
    schedule carrying no durations at all — where every element takes
    the attack reading."""
    rules = StyleRules(default_effect="pop",
                       volume={"amount": 1.0, "quiet": 0.5, "loud": 1.5})
    peaks = _quiet_after(3.0)

    with_durations = AnimationApplier(scenes.items, schedule_nv, TEMPO, rules)
    with_durations.set_audio(peaks, 0.0)
    plain = AnimationApplier(scenes.items, schedule, TEMPO, rules)
    plain.set_audio(peaks, 0.0)
    # the two schedules differ only in the duration map, so the element
    # rows line up and the gains can be compared position by position
    assert with_durations._index.ids \
        == plain._index.ids

    lengthless = moved = 0
    for row, mine, theirs in zip(with_durations._index.ids,
                                 with_durations._audio.gains,
                                 plain._audio.gains):
        for eid, a, b in zip(row, mine, theirs):
            if eid is not None and eid in schedule_nv.duration_by_element:
                moved += a != pytest.approx(b)
                continue
            lengthless += 1
            assert a == pytest.approx(b)
    assert lengthless                      # non-vacuity: some ink has none
    assert moved                           # and the notes really did move


# --- following the recording while the note sounds -------------------------

_FOLLOW_VOLUME = {"amount": 1.0, "quiet": 0.5, "loud": 1.5}


def _loud_after(seconds: float, duration: float = 30.0, rate: int = 44100):
    """The mirror of _quiet_after: near-silent up to `seconds`, loud
    after — so a note's average over its whole length and how loud the
    recording is at one moment inside it are plainly different numbers."""
    import numpy as np

    from scoreanim.core.audio import PeakCacheBuilder

    samples = np.full(int(duration * rate), 1.0, dtype=np.float32)
    samples[:int(seconds * rate)] = 0.02
    builder = PeakCacheBuilder(rate)
    builder.add_samples(samples)
    return builder.snapshot()


def _follow_rules(follower):
    """Everything pops over its own note value; the one element handed
    in swells and follows the recording instead."""
    from scoreanim.core.animation import ElementStyle

    return StyleRules(
        default_effect="pop",
        elements={follower: ElementStyle(effect="swell")},
        effect_params={"pop": {"note_value": True},
                       "swell": {"follow": True}},
        volume=_FOLLOW_VOLUME)


def _row_index(applier, i: int, eid) -> int:
    return list(applier._index.ids[i]).index(eid)


def test_a_following_element_reads_the_moment_and_its_neighbour_does_not(
        scenes, schedule_nv) -> None:
    """The feature, in one frame. Two noteheads on the same beat over a
    recording that is quiet at the beat and loud a moment later. The
    following one is modulated by how loud the recording is RIGHT THEN;
    the plain one still carries the one average over its own note."""
    from scoreanim.core.animation import (VolumeResponse, combined_state,
                                          gain_for, intensity_at,
                                          modulate_state)
    from scoreanim.core.animation.effect import SCALE

    i, (plain, plain_beats), (follower, follow_beats) = \
        _mixed_duration_trigger(scenes, schedule_nv)
    assert follow_beats > plain_beats                      # non-vacuity
    trig_s = TEMPO.seconds_at(schedule_nv.triggers[i].beats)
    short_s = TEMPO.seconds_at(
        schedule_nv.triggers[i].beats + plain_beats) - trig_s
    # quiet over most of the shorter note, loud from there on, and the
    # frame taken late enough to be well inside the loud part but early
    # enough that BOTH notes are still animating
    peaks = _loud_after(trig_s + 0.7 * short_s)
    t = trig_s + 0.9 * short_s

    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO,
                               _follow_rules(follower))
    applier.set_audio(peaks, 0.0)
    applier.refresh(t)

    volume = VolumeResponse(**_FOLLOW_VOLUME)
    live = gain_for(intensity_at(peaks, t), volume)
    j_follow = _row_index(applier, i, follower)
    j_plain = _row_index(applier, i, plain)
    average = applier._audio.gains[i][j_follow]
    # the two numbers really are different, or the test proves nothing
    assert live > average + 0.1

    def expected(j, gain):
        state = combined_state(
            trig_s,
            tuple(zip(applier._effects_per_trigger[i][j],
                      applier._timescales_per_trigger[i][j])),
            t)
        return modulate_state(state, gain)[SCALE]

    assert scenes.items[follower].scale() == \
        pytest.approx(expected(j_follow, live))
    assert scenes.items[plain].scale() == \
        pytest.approx(expected(j_plain, applier._audio.gains[i][j_plain]))
    # and the follower is plainly NOT on its own average
    assert scenes.items[follower].scale() != \
        pytest.approx(expected(j_follow, average))


def test_a_following_element_moves_with_the_recording(scenes,
                                                      schedule_nv) -> None:
    """Two frames of the same note: quiet early, loud later, and the
    ink is bigger in the loud one. Its own average never moves, so this
    can only come from the live reading."""
    long_head = _head_with_duration(scenes, schedule_nv, 3.0)
    trig_s = TEMPO.seconds_at(schedule_nv.beats_by_element[long_head])
    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO,
                               _follow_rules(long_head))
    applier.set_audio(_loud_after(trig_s + 0.75), 0.0)

    # both times sit on the plateau (10 %..85 % of a 1.5 s window)
    applier.refresh(trig_s + 0.4)
    quiet_frame = scenes.items[long_head].scale()
    applier.refresh(trig_s + 1.1)
    loud_frame = scenes.items[long_head].scale()
    assert loud_frame > quiet_frame + 0.1
    # and it still lands at exactly its engraved size at the end
    applier.refresh(trig_s + 1.5)
    assert scenes.items[long_head].scale() == 1.0


def test_no_audio_leaves_a_follow_swell_playing_its_plateau(
        scenes, schedule_nv) -> None:
    """With no recording, or the response off, there are no gains at
    all — a follow swell simply plays the shape as authored."""
    long_head = _head_with_duration(scenes, schedule_nv, 3.0)
    trig_s = TEMPO.seconds_at(schedule_nv.beats_by_element[long_head])
    rules = _follow_rules(long_head)
    silent = AnimationApplier(scenes.items, schedule_nv, TEMPO, rules)
    silent.refresh(trig_s + 0.75)
    assert silent._audio.gains is None
    assert scenes.items[long_head].scale() == pytest.approx(1.4)  # the plateau


def test_scrubbing_a_following_element_is_stateless(qapp, engraved,
                                                    schedule_nv,
                                                    scenes) -> None:
    """The live reading is a pure function of t, so walking forward to a
    time and jumping straight to it must leave the same ink. Every other
    volume test refreshes only; this one walks."""
    long_head = _head_with_duration(scenes, schedule_nv, 3.0)
    trig_s = TEMPO.seconds_at(schedule_nv.beats_by_element[long_head])
    rules = _follow_rules(long_head)
    peaks = _loud_after(trig_s + 0.75)
    mid = trig_s + 1.0                        # on the plateau, in the loud part

    applier = AnimationApplier(scenes.items, schedule_nv, TEMPO, rules)
    applier.set_audio(peaks, 0.0)
    rng = random.Random(31)
    t = 0.0
    for _ in range(60):
        t = max(-2.0, t + rng.uniform(-9.0, 11.0))
        applier.apply_at(t)
    for step in range(20):                    # and tick up to it in small hops
        applier.apply_at(mid - 0.4 + step * 0.02)
    applier.apply_at(mid)
    walked = _visual_state(scenes)

    fresh_scenes = ScoreScenes(engraved.layout, default_stage_config(
        engraved.prepared, page_content_top(engraved.layout)))
    fresh = AnimationApplier(fresh_scenes.items, schedule_nv, TEMPO, rules)
    fresh.set_audio(peaks, 0.0)
    fresh.refresh(mid)
    assert walked == _visual_state(fresh_scenes)
    # non-vacuity: the followed note really is animating at `mid`
    assert walked[long_head][1] != 1.0
