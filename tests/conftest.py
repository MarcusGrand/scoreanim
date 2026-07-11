"""Shared fixtures. The Verovio+music21 load is the expensive step, so it
runs once per session; everything downstream of it is pure data."""

from pathlib import Path

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio_adapter import (EngravedScore,
                                                      VerovioEngravingProvider)

TESTSCORE = Path(__file__).resolve().parent.parent / "testdata" / "testscore.musicxml"
# Dorico export with a hairpin broken across the m4→m5 system break, a slur
# broken across m8→m9, and ties broken across m8→m9 (Phase 5 fixture).
SPANNER_SCORE = Path(__file__).resolve().parent.parent / "testdata" / \
    "broken_hairpin_and_slur_test.musicxml"


@pytest.fixture(scope="session")
def engraved() -> EngravedScore:
    return VerovioEngravingProvider().load_detailed(TESTSCORE, EngravingParams())


@pytest.fixture(scope="session")
def engraved_spanners() -> EngravedScore:
    return VerovioEngravingProvider().load_detailed(SPANNER_SCORE,
                                                    EngravingParams())


@pytest.fixture(scope="session")
def score_model(engraved):
    from scoreanim.core.score.model import build_score_model
    return build_score_model(engraved.prepared)


@pytest.fixture(scope="session")
def join_mapping(engraved, score_model):
    from scoreanim.core.score.join import join_notes
    report = join_notes(score_model, engraved.note_records)
    assert report.is_complete
    return report.mapping
