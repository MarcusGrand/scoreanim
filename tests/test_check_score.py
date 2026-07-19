"""Score-doctor CLI (Phase 11.0): a total triage function — PASS with a
census, or a named failure point, never a traceback."""

from pathlib import Path

from scoreanim.tools.check_score import check, main

from .conftest import TESTSCORE


def test_doctor_passes_testscore():
    report = check(TESTSCORE, strict=True)
    assert report.ok
    assert report.pages == 3
    assert report.note_records == 500
    assert report.matched == report.model_notes == 500
    assert report.warnings["dropped-spanner"] == 5
    assert "PASS" in str(report)


def test_doctor_reports_failure_point_not_traceback(tmp_path):
    # A file Verovio cannot load fails at the engrave/decompose stage
    # with a named message, not an exception escaping check().
    bad = tmp_path / "not_a_score.musicxml"
    bad.write_text("<score-partwise><part/></score-partwise>")
    report = check(bad, strict=True)
    assert not report.ok
    assert report.stage
    assert report.message
    assert "FAIL" in str(report)


def test_doctor_main_returns_nonzero_on_missing_path():
    assert main(["/no/such/path.musicxml"]) == 2
