"""Live-oracle checks (docs/LIVE_TIMING_BRIEF.md, diagnosis 2026-07-22)
wired as regression pins.

Passing tests pin what the diagnosis found CLEAN (bigband1 everywhere;
the live path — D3/D4 — on every fixture). xfail(strict=True) tests pin
the confirmed findings; a fix session flips its finding's tests to
passing by removing the mark (strict=True makes the flip loud).

Findings (full table in docs/PHASES.md, "Live-timing diagnosis"):

- FINDING-1 (L0, score model): beat-domain shear — ScoreNote onsets /
  MeasureInfo starts / Verovio qstamps disagree on scores with
  irregular-length bars (complex3: X0 pickup 1 beat, m37 12 beats,
  m52 4.5 beats). Triggers import ScoreNote.onset (schedule rule 1),
  so notes light beats-to-measures off, reveal anchors invert
  against x (spanners reveal early), and sig onsets (engraved
  domain) shear against the note stream (sigs read ~2 measures
  late).
- FINDING-2 (L0, reveal coverage): a revealed-kind element whose
  (system, part) matches no reveal curve is silently visible from
  t=0 (brief F1) — complex3 P2:m69 hairpin seg1 in sys18.
- FINDING-3 (accepted limit, BACKLOG 10): per-part (not per-voice)
  edges let one voice's note anchor reveal past another voice's
  later-resolving rest — testscore sys5 P7.
- FINDING-4 (L0, adapter F4): cautionary/courtesy sigs nest in the
  measure BEFORE their change (testscore m4 meter → change m5;
  complex3 m26 → m27 etc.), lighting a measure early at the nesting
  measure's downbeat.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scoreanim.core.animation import RevealMode
from scoreanim.tools.live_oracle import (audit_join,
                                         audit_model_consistency,
                                         audit_reveal_anchors,
                                         audit_signatures, audit_triggers,
                                         build_bundle, check_d1, check_d3,
                                         check_d4)

TESTDATA = Path(__file__).resolve().parent.parent / "testdata"

_XF1 = "FINDING-1: beat-domain shear (irregular bars; model vs engraved)"
_XF2 = "FINDING-2: curve-less revealed spanner visible from t=0"
_XF3 = "FINDING-3: per-part edge vs multi-voice rest (BACKLOG 10)"
_XF4 = "FINDING-4: cautionary sig nests in pre-change measure"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="session")
def bundle_testscore(engraved):
    return build_bundle(TESTDATA / "testscore.musicxml", engraved=engraved)


@pytest.fixture(scope="session")
def bundle_bigband(engraved_bigband_hidden):
    return build_bundle(TESTDATA / "bigband1.musicxml",
                        engraved=engraved_bigband_hidden)


@pytest.fixture(scope="session")
def bundle_complex3(engraved_complex3_hidden):
    return build_bundle(TESTDATA / "complex3.musicxml",
                        engraved=engraved_complex3_hidden)


def _bundle(request, name):
    return request.getfixturevalue(f"bundle_{name}")


# -- D1: curve audit ---------------------------------------------------------

@pytest.mark.parametrize("fixture", [
    "testscore",
    "bigband",
    pytest.param("complex3",
                 marks=pytest.mark.xfail(reason=_XF2, strict=True)),
])
def test_d1_every_revealed_item_has_a_curve(request, fixture):
    assert check_d1(_bundle(request, fixture)) == []


# -- D2: trigger / model audits ---------------------------------------------

@pytest.mark.parametrize("fixture", [
    "testscore",
    "bigband",
    pytest.param("complex3",
                 marks=pytest.mark.xfail(reason=_XF1, strict=True)),
])
def test_d2_triggers_match_engraved_onsets(request, fixture):
    assert audit_triggers(_bundle(request, fixture)) == []


@pytest.mark.parametrize("fixture", [
    "testscore",
    "bigband",
    pytest.param("complex3",
                 marks=pytest.mark.xfail(reason=_XF1, strict=True)),
])
def test_d2_model_consistent_with_itself_and_engraving(request, fixture):
    assert audit_model_consistency(_bundle(request, fixture)) == []


@pytest.mark.parametrize("fixture", [
    pytest.param("testscore",
                 marks=pytest.mark.xfail(reason=_XF3, strict=True)),
    "bigband",
    pytest.param("complex3",
                 marks=pytest.mark.xfail(reason=_XF1, strict=True)),
])
def test_d2_reveal_anchors_monotone_in_x(request, fixture):
    assert audit_reveal_anchors(_bundle(request, fixture)) == []


@pytest.mark.parametrize("fixture", ["testscore", "bigband", "complex3"])
def test_d2_join_complete(request, fixture):
    assert audit_join(_bundle(request, fixture)) == []


@pytest.mark.parametrize("fixture", [
    pytest.param("testscore",
                 marks=pytest.mark.xfail(reason=_XF4, strict=True)),
    "bigband",
    pytest.param("complex3",
                 marks=pytest.mark.xfail(reason=_XF4, strict=True)),
])
def test_d2_sig_nesting_measures(request, fixture):
    findings = audit_signatures(_bundle(request, fixture))
    assert [f for f in findings if f.code == "sig-nesting"] == []


@pytest.mark.parametrize("fixture", [
    "testscore",
    "bigband",
    pytest.param("complex3",
                 marks=pytest.mark.xfail(reason=_XF1, strict=True)),
])
def test_d2_sig_onsets_match_model_measure_starts(request, fixture):
    findings = audit_signatures(_bundle(request, fixture))
    assert [f for f in findings
            if f.code == "sig-onset-vs-measure-start"] == []


# -- D3: fresh-state oracle (L1) — clean everywhere: the pin -----------------

@pytest.mark.parametrize("fixture,mode", [
    ("testscore", RevealMode.STEPPED),
    ("testscore", RevealMode.CONTINUOUS),
    ("bigband", RevealMode.STEPPED),
    ("complex3", RevealMode.STEPPED),
])
def test_d3_refresh_matches_pure_expectation(qapp, request, fixture, mode):
    findings = check_d3(_bundle(request, fixture), mode, "measures", [])
    assert findings == []


# -- D4: live-tick differential (L2) — clean everywhere: the pin -------------

@pytest.mark.parametrize("fixture,mode", [
    ("testscore", RevealMode.STEPPED),
    ("testscore", RevealMode.CONTINUOUS),
    ("bigband", RevealMode.STEPPED),
    ("complex3", RevealMode.STEPPED),
])
def test_d4_ticking_equals_fresh_refresh(qapp, request, fixture, mode):
    findings = check_d4(_bundle(request, fixture), mode, [])
    assert findings == []
