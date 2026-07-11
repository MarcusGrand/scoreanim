"""Shared fixtures. The Verovio+music21 load is the expensive step, so it
runs once per session; everything downstream of it is pure data."""

from pathlib import Path

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio_adapter import (EngravedScore,
                                                      VerovioEngravingProvider)

TESTSCORE = Path(__file__).resolve().parent.parent / "testdata" / "testscore.musicxml"


@pytest.fixture(scope="session")
def engraved() -> EngravedScore:
    return VerovioEngravingProvider().load_detailed(TESTSCORE, EngravingParams())


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
