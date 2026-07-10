"""PHASES 1.4 verification: ScoreModel ⇄ Layout identity join.

The join must be a complete bijection on the fixture (all 500 noteheads),
onsets must agree exactly with Verovio's timemap for non-grace notes, and
the known library quirks are pinned so regressions surface loudly:

- 2 D7 chord symbols realize as ChordSymbol pseudo-chords in music21 and
  must be excluded (they engrave as text, not noteheads);
- Verovio's gestural accidental (accid.ges) disagrees with the
  authoritative MusicXML <alter> on exactly 8 notes (5 open-tie targets
  + 3 cross-octave propagations) — which is why alter is not a join key;
- tied-to notes DO appear as fresh timemap onsets: the animation layer
  must consult ScoreNote.tie, not the timemap, to avoid re-triggering.
"""

import pytest

from scoreanim.core.score.join import join_notes


@pytest.fixture(scope="session")
def report(engraved, score_model):
    return join_notes(score_model, engraved.note_records)


def test_join_is_a_complete_bijection(engraved, score_model, report) -> None:
    assert len(score_model.notes) == 500
    assert len(engraved.note_records) == 500
    assert report.is_complete, (
        f"unmatched score: {report.unmatched_score[:3]} "
        f"unmatched layout: {report.unmatched_layout[:3]}")
    assert len(report.matched) == 500
    assert len({eid for eid, _ in report.matched}) == 500


def test_nongrace_onsets_equal_timemap(engraved, report) -> None:
    recs = {r.element_id: r for r in engraved.note_records}
    for eid, note in report.matched:
        if not note.grace:
            assert recs[eid].onset == pytest.approx(note.onset, abs=1e-9), eid


def test_grace_onsets_precede_their_principal(engraved, report) -> None:
    recs = {r.element_id: r for r in engraved.note_records}
    graces = [(recs[eid], note) for eid, note in report.matched if note.grace]
    assert len(graces) == 3
    for rec, note in graces:
        # ScoreModel puts the grace on its principal's beat; the timemap
        # gives it a real earlier stamp
        assert rec.onset < note.onset


def test_pitch_spelling_agrees_except_known_accid_ges_quirks(
        engraved, report) -> None:
    """Verovio's accid.ges is wrong on exactly 8 notes of this fixture
    (spikes/NOTES.md): the 5 open-tie targets get no gestural alter, and
    3 Tbns notes get one over-propagated. Step/octave always agree."""
    recs = {r.element_id: r for r in engraved.note_records}
    disagreements = []
    for eid, note in report.matched:
        rec = recs[eid]
        if note.pitch_step is None:
            assert rec.staff_loc == note.staff_loc, eid
            continue
        assert rec.pitch_step == note.pitch_step, eid
        assert rec.octave == note.octave, eid
        if rec.pitch_alter != note.pitch_alter:
            disagreements.append(eid)
    assert len(disagreements) == 8


def test_tied_to_notes_appear_as_fresh_timemap_onsets(report) -> None:
    """Phase 3 watch item: Verovio's timemap reports every note as an
    'on' event, including tie continuations — all 500 records carry an
    onset and all matched. Reveal logic must gate on ScoreNote.tie."""
    tie_stops = [note for _, note in report.matched if note.tie == "stop"]
    assert len(tie_stops) == 58


def test_unpitched_drums_join_by_staff_position(report) -> None:
    unpitched = [(eid, n) for eid, n in report.matched if n.pitch_step is None]
    assert len(unpitched) == 17
    assert all(n.part == "P7" and n.staff_loc is not None
               for _, n in unpitched)


def test_measures_and_slash_regions(score_model) -> None:
    assert len(score_model.measures) == 19
    m1 = score_model.measure(1)
    assert (m1.start, m1.quarter_length) == (0.0, 4.0)
    assert score_model.measure(5).quarter_length == 2.0     # 2/4
    assert score_model.measure(14).quarter_length == 2.0
    regions = {(r.start_measure, r.stop_measure)
               for r in score_model.slash_regions}
    assert regions == {(3, 10), (11, 16), (16, 18)}
    assert all(r.part == "P7" and r.slash_unit_quarters == 1.0
               for r in score_model.slash_regions)
