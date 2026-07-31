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


def test_timed_effect_scales_mid_window(scenes, schedule, pop_rules) -> None:
    """Mid-decay the whole note sits at the lerped scale — the stem
    included, turning around the SAME point as its head, so the note
    pops as one object; past the window everything is 1.0."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, pop_rules)
    head, stem = _p1_head_and_stem(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])

    applier.apply_at(trig_s + 0.125)               # mid-decay
    assert scenes.items[head].scale() == pytest.approx(1.125)
    assert scenes.items[head].opacity() == pytest.approx(1.0)
    assert scenes.items[stem].scale() == pytest.approx(1.125)
    assert scenes.items[stem].scale_pivot == scenes.items[head].scale_pivot
    # the stem pivots on its head, not on its own middle
    assert scenes.items[stem].scale_pivot != scenes.items[stem].anchor
    applier.apply_at(trig_s + 0.5)                 # window expired
    assert scenes.items[head].scale() == pytest.approx(1.0)
    assert scenes.items[stem].scale() == pytest.approx(1.0)
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
    # the stem drops with it, around the same point
    assert scenes.items[stem].scale() == pytest.approx(3.0)
    assert scenes.items[stem].scale_pivot == scenes.items[head].scale_pivot
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


def test_a_beam_drops_with_the_first_note_of_its_group(scenes,
                                                      schedule) -> None:
    """Marcus's rule for beams: the whole beam falls in with the note it
    starts on, and the notes after it drop onto it with their own stems.
    It comes free from the group key — a beam's onset is its first
    note's."""
    beam, first, later = _beamed_group(scenes)
    applier = AnimationApplier(scenes.items, schedule, TEMPO, _DROP_RULES)
    first_s = TEMPO.seconds_at(schedule.beats_by_element[first.element_key])
    later_s = TEMPO.seconds_at(schedule.beats_by_element[later.element_key])
    assert later_s > first_s

    applier.refresh(first_s)
    assert beam.scale() == pytest.approx(3.0)      # it rides note 1
    assert beam.scale_pivot == first.scale_pivot   # around note 1's head
    assert later.scale() == pytest.approx(1.0)     # not its turn yet
    assert later.opacity() == pytest.approx(FLOOR)

    applier.refresh(later_s)
    assert later.scale() == pytest.approx(3.0)     # now it drops
    assert beam.scale() < 1.6                      # nearly home already
    assert beam.scale() < later.scale()


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
