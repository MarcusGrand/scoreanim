"""Shared fixtures. The Verovio+music21 load is the expensive step, so it
runs once per session; everything downstream of it is pure data."""

from pathlib import Path

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import (EngravedScore,
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
# 25 staves on a single 2-measure system (from complex2): taller than its
# page and unpaginatable, so the never-clip path scales the engraving to
# fit (Phase 12.5).
TALL_SYSTEM_SCORE = Path(__file__).resolve().parent.parent / "testdata" / \
    "tall_system_min.musicxml"
# 4-part big-band chart (Alto/Bari/Tpt/Tbn). Under hide-empty-staves (the
# default) the optimize round-trip makes Verovio reuse an xml:id across a
# stem group and a tie group, nesting later-system tie/slur curves INSIDE
# earlier notes' stem/flag groups — the cross-system stray-path leak
# (2026-07-21). Loaded hidden to exercise _rehome_stray_paths.
BIGBAND_SCORE = Path(__file__).resolve().parent.parent / "testdata" / \
    "bigband1.musicxml"
# 14-part orchestral chart with a Dorico "X0" pickup bar (measure-identity
# fixture) and 69 spanner sources whose end note is hidden under
# hide-empty-staves — the phantom-slur condition (test_phantom_slur).
# Skip-if-absent: large production score, may not ship everywhere.
COMPLEX3_SCORE = Path(__file__).resolve().parent.parent / "testdata" / \
    "complex3.musicxml"
# 3-bar "X0"-pickup unit fixture for the measure-identity invariant.
PICKUP_SCORE = Path(__file__).resolve().parent.parent / "testdata" / \
    "pickup_min.musicxml"


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
def engraved_bigband_hidden() -> EngravedScore:
    # hide_empty_staves=True (the new-document default) is the trigger for
    # the stray-path artifact; strict=False so the unknown 'gliss' class
    # degrades instead of raising (the leak is unrelated to it).
    return VerovioEngravingProvider().load_detailed(
        BIGBAND_SCORE, EngravingParams(), hide_empty_staves=True,
        strict=False)


@pytest.fixture(scope="session")
def engraved_complex1() -> EngravedScore:
    return VerovioEngravingProvider().load_detailed(COMPLEX1_SCORE,
                                                    EngravingParams())


@pytest.fixture(scope="session")
def engraved_complex3_hidden() -> EngravedScore:
    # Promoted from test_phantom_slur's module fixture (Phase R.0) so the
    # golden suite shares the load. Skip-if-absent kept.
    if not COMPLEX3_SCORE.exists():
        pytest.skip("complex3.musicxml fixture not present")
    return VerovioEngravingProvider().load_detailed(
        COMPLEX3_SCORE, EngravingParams(), hide_empty_staves=True,
        strict=True)


@pytest.fixture(scope="session")
def engraved_pickup() -> EngravedScore:
    return VerovioEngravingProvider().load_detailed(PICKUP_SCORE,
                                                    EngravingParams())


@pytest.fixture(scope="session")
def engraved_condense_flat() -> EngravedScore:
    return VerovioEngravingProvider().load_detailed(CONDENSE_SCORE,
                                                    EngravingParams())


@pytest.fixture(scope="session")
def engraved_condense_grouped() -> EngravedScore:
    # One condense group (the test_condense spec): exercises the prep-seam
    # part-list rewrite branch the golden suite must pin.
    from scoreanim.core.score.musicxml_prep import PartCondenseSpec
    spec = PartCondenseSpec(parts=("P1", "P2"), name="Flute 1.2",
                            abbreviation="Fl. 1.2")
    return VerovioEngravingProvider().load_detailed(
        CONDENSE_SCORE, EngravingParams(), condense=(spec,))


@pytest.fixture(scope="session")
def engraved_tall_system() -> EngravedScore:
    # strict=False matching test_scale_to_fit — exercises the
    # scale-to-fit retry path.
    return VerovioEngravingProvider().load_detailed(
        TALL_SYSTEM_SCORE, EngravingParams(), strict=False)


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
