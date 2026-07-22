"""Spanner clip-reveal through the applier, offscreen, on the
broken-spanner fixture (Phase 5.2): ghosts, grow, segments at reveal 0,
mode switching, scrub statelessness extended to clip edges."""

import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import (FLOOR_OPACITY,  # noqa: E402
                                      REVEALED_KINDS, RevealMode, StyleRules,
                                      build_reveal_tracks,
                                      build_trigger_schedule)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.core.score.join import join_notes  # noqa: E402
from scoreanim.core.score.model import build_score_model  # noqa: E402
from scoreanim.core.timing import TempoEvent, TempoMap  # noqa: E402
from scoreanim.render.animate import AnimationApplier  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402

FLOOR = FLOOR_OPACITY
BPM60 = TempoMap([TempoEvent(0.0, 60.0)])   # seconds == beats


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def spanner_setup(engraved_spanners):
    model = build_score_model(engraved_spanners.prepared,
                              engraved_spanners.timeline)
    report = join_notes(model, engraved_spanners.note_records)
    assert report.is_complete
    schedule = build_trigger_schedule(engraved_spanners.layout,
                                      report.mapping, model.measures)
    score_end = max(m.start + m.quarter_length for m in model.measures)
    tracks = build_reveal_tracks(engraved_spanners.layout, schedule,
                                 score_end)
    return schedule, tracks, score_end


def _scenes(qapp, engraved_spanners) -> ScoreScenes:
    stage = default_stage_config(engraved_spanners.prepared,
                                 page_content_top(engraved_spanners.layout))
    return ScoreScenes(engraved_spanners.layout, stage, ghost_opacity=FLOOR)


def _make(qapp, engraved_spanners, spanner_setup,
          mode=RevealMode.STEPPED):
    scenes = _scenes(qapp, engraved_spanners)
    schedule, tracks, score_end = spanner_setup
    applier = AnimationApplier(scenes.items, schedule, BPM60,
                               StyleRules(reveal_mode=mode), tracks)
    return scenes, applier, score_end


def _clip_states(scenes: ScoreScenes) -> dict:
    return {eid: tuple(c.clip_right for c in item.reveal_children)
            for eid, item in scenes.items.items()
            if item.reveal_children}


def test_spanners_have_ghost_and_reveal_layers(qapp,
                                               engraved_spanners) -> None:
    scenes = _scenes(qapp, engraved_spanners)
    for eid, item in scenes.items.items():
        ident = item.identity
        if ident is None or ident.kind not in REVEALED_KINDS:
            assert not item.reveal_children
            continue
        # one ghost + one reveal child per source path
        assert item.reveal_children
        ghosts = [c for c in item.childItems()
                  if c not in item.reveal_children]
        assert len(ghosts) == len(item.reveal_children)
        assert all(g.opacity() == pytest.approx(FLOOR) for g in ghosts)
        # spanner opacity is NOT trigger-animated: parent stays 1.0
        assert item.opacity() == pytest.approx(1.0)


def test_set_ghost_opacity_redims_ghosts_only(qapp, engraved_spanners,
                                              spanner_setup) -> None:
    """Phase 7.2: the ghost floor is settable after construction. At 0
    the ghosts are invisible but the clip-reveal copies still work —
    a spanner grows out of nothing."""
    scenes, applier, score_end = _make(qapp, engraved_spanners,
                                       spanner_setup)
    scenes.set_ghost_opacity(0.0)
    spanner_items = [item for item in scenes.items.values()
                     if item.reveal_children]
    assert spanner_items
    for item in spanner_items:
        ghosts = [c for c in item.childItems()
                  if c not in item.reveal_children]
        assert all(g.opacity() == pytest.approx(0.0) for g in ghosts)
        # the reveal copies are untouched (clip does the revealing)
        assert all(c.opacity() == pytest.approx(1.0)
                   for c in item.reveal_children)
    applier.refresh(score_end + 1.0)             # reveal still functions
    for item in spanner_items:
        assert all(c.clip_right is None for c in item.reveal_children)
    scenes.set_ghost_opacity(0.6)                # and back up
    for item in spanner_items:
        ghosts = [c for c in item.childItems()
                  if c not in item.reveal_children]
        assert all(g.opacity() == pytest.approx(0.6) for g in ghosts)


def test_preroll_hidden_past_end_revealed(qapp, engraved_spanners,
                                          spanner_setup) -> None:
    scenes, applier, score_end = _make(qapp, engraved_spanners,
                                       spanner_setup)
    for eid, item in scenes.items.items():
        for child in item.reveal_children:
            assert child.hidden, eid
    applier.refresh(score_end + 1.0)
    for eid, item in scenes.items.items():
        for child in item.reveal_children:
            assert child.clip_right is None, eid       # fully revealed


def test_slur_over_broken_ties_grows_with_the_playhead(
        qapp, engraved_spanners, spanner_setup) -> None:
    """Grow-with-playhead (ruling A/B revised 2026-07-22): the broken slur
    over the m8→m9 tied notes reveals PROGRESSIVELY as each side's own
    playhead sweeps it. The continuation segment (system 3) is hidden before
    its system's playhead reaches it, grows monotonically across, and stands
    full by the slur's own end — it no longer pops to the tied value at the
    chain start (there is no chain-start retiming any more; seconds==beats)."""
    scenes, applier, _ = _make(qapp, engraved_spanners, spanner_setup)
    _, tracks, _ = spanner_setup
    layout = engraved_spanners.layout
    slur = next(e for e in layout.elements
                if e.identity.kind is ElementKind.SLUR
                and ":seg" not in str(e.identity.element_id))
    seg = next(e for e in layout.elements
               if e.identity.kind is ElementKind.SLUR
               and ":seg" in str(e.identity.element_id))
    seg_children = scenes.items[seg.identity.element_id].reveal_children
    # the seg's OWN (system, part) reveal track drives it
    track = next(t for t in tracks
                 if t.system == seg.system and t.part == seg.identity.part)

    # before its system's playhead has entered, the continuation is hidden
    applier.refresh(track.beats[0] - 0.01)
    assert all(c.hidden for c in seg_children)

    # sweeping forward across the seg's own anchors, its clip only advances
    def clips():
        return [float("inf") if c.clip_right is None else c.clip_right
                for c in seg_children]
    prev = clips()
    for beat in track.beats:
        applier.refresh(beat)
        now = clips()
        assert all(a <= b for a, b in zip(prev, now)), beat  # never retreats
        prev = now

    # by the slur's own end note the continuation is fully revealed
    _, slur_end = slur.identity.extent
    applier.refresh(slur_end)
    assert all(c.clip_right is None for c in seg_children)


def test_stepped_holds_between_onsets_continuous_moves(
        qapp, engraved_spanners, spanner_setup) -> None:
    scenes, applier, _ = _make(qapp, engraved_spanners, spanner_setup)
    layout = engraved_spanners.layout
    hp = next(e for e in layout.elements
              if e.identity.kind is ElementKind.HAIRPIN
              and ":seg" not in str(e.identity.element_id))
    start, end = hp.identity.extent
    eid = hp.identity.element_id
    applier.refresh(start + 0.05)               # just after an onset
    stepped_a = _clip_states(scenes)[eid]
    applier.apply_at(start + 0.45)              # still before the next beat
    stepped_b = _clip_states(scenes)[eid]
    assert stepped_a == stepped_b               # STEPPED holds

    applier.set_style(StyleRules(reveal_mode=RevealMode.CONTINUOUS))
    cont_a = _clip_states(scenes)[eid]
    applier.apply_at(start + 0.7)
    cont_b = _clip_states(scenes)[eid]
    assert cont_a != cont_b                     # CONTINUOUS sweeps


def test_scrub_statelessness_includes_clips(qapp, engraved_spanners,
                                            spanner_setup) -> None:
    scenes, applier, _ = _make(qapp, engraved_spanners, spanner_setup,
                               RevealMode.CONTINUOUS)
    rng = random.Random(3)
    t = 0.0
    for _ in range(50):
        t = max(-2.0, t + rng.uniform(-7.0, 9.0))
        applier.apply_at(t)
    applier.apply_at(21.3)
    walked = _clip_states(scenes)

    fresh_scenes, fresh_applier, _ = _make(qapp, engraved_spanners,
                                           spanner_setup,
                                           RevealMode.CONTINUOUS)
    fresh_applier.refresh(21.3)
    assert walked == _clip_states(fresh_scenes)
