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
