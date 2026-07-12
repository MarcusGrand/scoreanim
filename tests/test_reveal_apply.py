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
    model = build_score_model(engraved_spanners.prepared)
    report = join_notes(model, engraved_spanners.note_records)
    assert report.is_complete
    schedule = build_trigger_schedule(engraved_spanners.layout,
                                      report.mapping)
    score_end = max(m.start + m.quarter_length for m in model.measures)
    tracks = build_reveal_tracks(engraved_spanners.layout, score_end)
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


def test_source_grows_while_later_segment_sits_at_zero(
        qapp, engraved_spanners, spanner_setup) -> None:
    """The broken slur: its source lives in system 2, its continuation
    in system 3. Mid-slur, the source is partially revealed (neither
    hidden nor complete) while the segment is still fully hidden."""
    scenes, applier, _ = _make(qapp, engraved_spanners, spanner_setup,
                               RevealMode.CONTINUOUS)
    layout = engraved_spanners.layout
    slur = next(e for e in layout.elements
                if e.identity.kind is ElementKind.SLUR
                and ":seg" not in str(e.identity.element_id))
    seg = next(e for e in layout.elements
               if e.identity.kind is ElementKind.SLUR
               and ":seg" in str(e.identity.element_id))
    start, end = slur.identity.extent
    applier.refresh((start + end) / 2)          # seconds == beats
    src_children = scenes.items[slur.identity.element_id].reveal_children
    seg_children = scenes.items[seg.identity.element_id].reveal_children
    assert all(not c.hidden and c.clip_right is not None
               for c in src_children)
    assert all(c.hidden for c in seg_children)
    # once time reaches the segment's system, the segment grows too
    applier.refresh(end + 0.01)
    assert all(not c.hidden for c in seg_children)


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
