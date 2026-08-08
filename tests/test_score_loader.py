"""Load pipeline (M1.7), offscreen: one real engrave of testscore
through ScoreLoader returns a complete LoadedScore bundle, and the
applied-input diff (`needs_reengrave`) trips on exactly the four
prep-seam inputs — staff groups, part-label overrides, hide-empty-
staves, condense groups.
"""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import StyleRules  # noqa: E402
from scoreanim.core.engraving.types import EngravingParams  # noqa: E402
from scoreanim.core.project import (PartTextOverride,  # noqa: E402
                                    ProjectDoc, StaffGroup)
from scoreanim.core.score.identity import PartId  # noqa: E402
from scoreanim.ui.score_loader import ScoreLoader  # noqa: E402

TESTSCORE = Path(__file__).parent.parent / "testdata" / "testscore.musicxml"


@pytest.fixture(scope="module")
def loaded(qapp_and_loader):
    loader, bundle = qapp_and_loader
    return bundle


@pytest.fixture(scope="module")
def qapp_and_loader():
    QApplication.instance() or QApplication([])
    loader = ScoreLoader()
    # engrave with a fresh document's inputs (hide-empty defaults ON)
    bundle = loader.load(TESTSCORE, EngravingParams(), None, StyleRules(),
                         hide_empty_staves=ProjectDoc().hide_empty_staves)
    return loader, bundle


def test_bundle_is_complete(loaded) -> None:
    assert loaded.scenes.page_count >= 1
    assert loaded.scenes.items                     # decomposed elements
    assert loaded.measures                         # rebased score model
    assert len(loaded.parts) == 7                  # testscore's parts
    assert 1 in loaded.band_by_system              # system framing rects
    assert loaded.applier is not None
    assert loaded.animation_inputs.stage is loaded.stage
    assert not loaded.overflow                     # testscore fits its pages
    assert "elements on" in loaded.status_line     # the timing status line


def test_stage_seeded_when_none_given(loaded) -> None:
    """stage=None means fresh score: config seeds from the credits."""
    assert loaded.stage is not None


def test_needs_reengrave_trips_on_prep_seam_inputs_only(
        qapp_and_loader) -> None:
    loader, _ = qapp_and_loader
    doc = ProjectDoc()                             # matches the load above
    assert not loader.needs_reengrave(doc)
    assert loader.needs_reengrave(
        replace(doc, hide_empty_staves=not doc.hide_empty_staves))
    assert loader.needs_reengrave(replace(doc, text_overrides={
        PartId("P1"): PartTextOverride(name="Fl.", abbreviation="")}))
    assert loader.needs_reengrave(replace(doc, staff_groups=(
        StaffGroup(parts=(PartId("P1"), PartId("P2")), symbol="bracket",
                   join_barlines=True),)))
    assert loader.needs_reengrave(replace(doc, hide_first_system=True))
    # a non-engraving change (timing, style, stage) never trips it
    assert not loader.needs_reengrave(
        replace(doc, style=replace(doc.style, floor_opacity=0.9)))


# --- trigger overrides: reschedule without a re-engrave (2026-08-08) -------

def _movable(bundle):
    """A real dynamic and a beat from another trigger row."""
    from scoreanim.core.score.identity import ElementKind
    layout = bundle.animation_inputs.layout
    schedule = bundle.animation_inputs.schedule
    dynamic = next(el.identity.element_id for el in layout.elements
                   if el.identity.kind is ElementKind.DYNAMIC
                   and el.identity.onset is not None)
    target = next(b for b in schedule.beat_values
                  if b != schedule.beats_by_element[dynamic])
    return dynamic, target


def test_trigger_overrides_reschedule_not_reengrave(qapp_and_loader) -> None:
    """The override is not an engraving input: needs_reengrave never
    sees it, needs_reschedule trips on it and clears after the rebuild,
    and the rebuild costs no Verovio."""
    loader, bundle = qapp_and_loader
    doc = ProjectDoc()
    dynamic, target = _movable(bundle)
    moved_doc = replace(doc, trigger_overrides={dynamic: target})

    assert not loader.needs_reengrave(moved_doc)
    assert not loader.needs_reschedule(doc)
    assert loader.needs_reschedule(moved_doc)

    rebuilt = loader.rebuild_schedule(moved_doc)
    assert rebuilt.beats_by_element[dynamic] == target
    assert not loader.needs_reschedule(moved_doc)    # cache updated

    # back to automatic: the rebuild equals the load's own schedule
    assert loader.rebuild_schedule(doc) == bundle.animation_inputs.schedule
    assert not loader.needs_reschedule(doc)


def test_rebuild_is_none_before_any_load() -> None:
    assert ScoreLoader().rebuild_schedule(ProjectDoc()) is None


def test_rebuild_matches_a_fresh_load_and_stale_ids_warn(
        qapp_and_loader) -> None:
    """The live rebuild and a fresh load with the same overrides derive
    the same schedule, and a stale id costs exactly one
    trigger-override-inert warning."""
    loader, bundle = qapp_and_loader
    dynamic, target = _movable(bundle)
    overrides = {dynamic: target, "ghost:m1:s1:v1:dynam:9": 1.0}

    fresh = ScoreLoader().load(
        TESTSCORE, EngravingParams(), None, StyleRules(),
        hide_empty_staves=ProjectDoc().hide_empty_staves,
        trigger_overrides=overrides)
    doc = replace(ProjectDoc(), trigger_overrides=overrides)
    assert loader.rebuild_schedule(doc) == fresh.animation_inputs.schedule

    inert = [w for w in fresh.warnings
             if w.code == "trigger-override-inert"]
    assert len(inert) == 1
    assert "ghost" in inert[0].message
    assert "1 moved onset(s)" in inert[0].message

    # leave the module-scoped loader's cache as the other tests expect
    loader.rebuild_schedule(ProjectDoc())
