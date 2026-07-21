"""Measure identity is the 1-based document-order ordinal, uniformly across
music21, the MusicXML DOM and Verovio's MEI — never the printed number, which
is neither unique nor consistent for Dorico's non-numeric "X0"/"X1" bars.

`pickup_min.musicxml` has a pickup bar numbered "X0": music21 parses it to
number 0, the MEI/DOM keep "X0". Before the ordinal-identity fix, the score
side keyed the pickup at 0 and real bar 1 at 1 while the adapter keyed the
pickup at 1 (ordinal fallback) — colliding with real bar 1 — so onsets/systems
were dropped by setdefault and the pickup note failed to join. This pins the
fix: identity is [1,2,3] on both sides, display stays [0,1,2]."""

from pathlib import Path

from scoreanim.core.engraving.provider import EngravingParams
from scoreanim.core.engraving.verovio_adapter import VerovioEngravingProvider
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.model import build_score_model

PICKUP = Path(__file__).resolve().parent.parent / "testdata" / "pickup_min.musicxml"


def _load():
    model = build_score_model(PICKUP)
    prov = VerovioEngravingProvider()
    engraved = prov.load_detailed(PICKUP, EngravingParams(), strict=True)
    return model, engraved


def test_identity_is_ordinal_display_is_number() -> None:
    model, engraved = _load()
    # identity (join key) is the 1-based ordinal on BOTH sides — pickup=1
    assert sorted({n.measure for n in model.notes}) == [1, 2, 3]
    assert sorted({r.measure for r in engraved.note_records}) == [1, 2, 3]
    # display keeps the printed number (music21: "X0" -> 0)
    assert [m.number for m in model.measures] == [0, 1, 2]


def test_pickup_note_joins_no_collision() -> None:
    model, engraved = _load()
    report = join_notes(model, engraved.note_records)
    # the pickup note used to be dropped by the number/ordinal collision
    assert report.is_complete, (
        f"unmatched score={report.unmatched_score} "
        f"layout={report.unmatched_layout}")
    # every note across the pickup and both full bars matched
    assert len(report.matched) == len(model.notes) == 9


def test_measure_keys_are_unique() -> None:
    _, engraved = _load()
    # one distinct ordinal per physical measure — no setdefault collision that
    # would collapse the pickup onto real bar 1
    measures = [r.measure for r in engraved.note_records]
    assert set(measures) == {1, 2, 3}
