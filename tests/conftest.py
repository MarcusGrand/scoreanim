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
# Real production score (Phase 10 fixture): 7 score-parts with a
# multi-staff Piano (<staves>2</staves>), two-voice displaced rests with
# ledger dashes, ties whose continuation ink spans 3+ systems, 6 ties
# Verovio drops (empty <g>s), bracketSpan/mSpace classes, trills,
# fermatas, ppp, wedges, chord-symbol bass notes.
VIDEO_SCORE = Path(__file__).resolve().parent.parent / "testdata" / \
    "video_test.musicxml"
# Dorico robustness fixture (Phase 11): 14 single-staff parts, 3 pages,
# 921 notes. Exercises a bowed tremolo (bTrem), a two-voice measure that
# displaces an mRest onto a ledger dash, 26 grace notes (the appoggiatura
# join gap, Phase 12.1), 26 tuplets, unpitched percussion, and 6
# transposed parts. Loaded strict (pytest default) — it must decompose
# cleanly with no unknown-class degradation.
COMPLEX1_SCORE = Path(__file__).resolve().parent.parent / "testdata" / \
    "complex1.musicxml"
# Minimal bar-repeat fixture (Phase 12.2): the Bongos part extracted from
# complex2 (mm.1-6), carrying a <measure-repeat> region [2,7). Verovio
# imports the repeat bars as empty <space>, so the adapter synthesizes
# five BAR_REPEAT symbols (one per bar, onset on the downbeat).
BAR_REPEAT_SCORE = Path(__file__).resolve().parent.parent / "testdata" / \
    "bar_repeat_min.musicxml"
# Two like parts for condensing (Phase 12.3): Flute 1 (P1) + Flute 2 (P2)
# extracted from complex2 (a busy divergent passage, mm.60-68). Condensing
# merges them onto one staff as voices 1 and 2 ("Flute 1.2").
CONDENSE_SCORE = Path(__file__).resolve().parent.parent / "testdata" / \
    "condense_min.musicxml"


@pytest.fixture(scope="session")
def engraved() -> EngravedScore:
    return VerovioEngravingProvider().load_detailed(TESTSCORE, EngravingParams())


@pytest.fixture(scope="session")
def engraved_bar_repeat() -> EngravedScore:
    return VerovioEngravingProvider().load_detailed(BAR_REPEAT_SCORE,
                                                    EngravingParams())


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


@pytest.fixture(scope="session")
def engraved_video() -> EngravedScore:
    # Deliberately hide_empty_staves=False: this fixture exercises the
    # flat layout (implausible-tie suppression, repagination paths).
    return VerovioEngravingProvider().load_detailed(VIDEO_SCORE,
                                                    EngravingParams())


@pytest.fixture(scope="session")
def engraved_video_hidden() -> EngravedScore:
    # The new-document default configuration (Phase 10R): empty staves
    # hidden per system, as the score's encoded page layout assumes.
    return VerovioEngravingProvider().load_detailed(
        VIDEO_SCORE, EngravingParams(), hide_empty_staves=True)


@pytest.fixture(scope="session")
def engraved_complex1() -> EngravedScore:
    return VerovioEngravingProvider().load_detailed(COMPLEX1_SCORE,
                                                    EngravingParams())


@pytest.fixture(scope="session")
def complex1_score_model():
    from scoreanim.core.score.model import build_score_model
    return build_score_model(COMPLEX1_SCORE)


@pytest.fixture(scope="session")
def video_score_model():
    # Deliberately independent of engraved_video: build_score_model is
    # prep + music21 only, no engraving.
    from scoreanim.core.score.model import build_score_model
    return build_score_model(VIDEO_SCORE)


@pytest.fixture(scope="session")
def video_join_mapping(engraved_video, video_score_model):
    from scoreanim.core.score.join import join_notes
    report = join_notes(video_score_model, engraved_video.note_records)
    assert report.is_complete
    return report.mapping
