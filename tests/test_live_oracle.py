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
- FINDING-2 (L0, reveal coverage) FIXED 2026-07-22: a revealed-kind
  element whose (system, part) matches no reveal curve WAS silently
  visible from t=0 (brief F1) — complex3 P2:m69 hairpin seg1 in
  sys18. Now its clip children default to hidden and the applier
  warns loudly; the D1 pin passes and
  test_finding2_curveless_spanner_hidden_and_warned pins the
  containment.
- FINDING-3 (accepted limit, BACKLOG 10): per-part (not per-voice)
  edges let one voice's note anchor reveal past another voice's
  later-resolving rest — testscore sys5 P7.
- FINDING-4 (L0, adapter F4) FIXED 2026-07-23: cautionary/courtesy
  sigs nest in the measure BEFORE their change (testscore m4 meter →
  change m5; complex3 m26 → m27, m52 → m53), so they lit a measure
  early at the nesting measure's downbeat. The adapter now retimes an
  end-of-system courtesy to its CHANGE measure's start; the nesting
  pins pass and test_finding4_courtesy_sig_lights_with_change pins
  the retime.
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

# FINDING-1 (beat-domain shear) FIXED 2026-07-22: the model's beat
# accounting is reconciled to the engraved MeasureTimeline, so its four
# complex3 pins below are plain passing regression tests now.
# FINDING-2 (curve-less spanner) FIXED 2026-07-22: default-hidden clip
# children + loud applier warning — the D1 pin passes and the
# containment pin below replaces the xfail.
# FINDING-4 (courtesy sig nesting) FIXED 2026-07-23: an end-of-system
# courtesy sig retimes to its change measure — the sig-nesting pins
# below are plain passing regression tests now.
_XF3 = "FINDING-3: per-part edge vs multi-voice rest (BACKLOG 10)"


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

@pytest.mark.parametrize("fixture", ["testscore", "bigband", "complex3"])
def test_d1_every_revealed_item_has_a_curve(request, fixture):
    """Curve-less keys are notes (caught: default-hidden + warning),
    never findings; the id audits (F2) must stay clean."""
    log: list[str] = []
    assert check_d1(_bundle(request, fixture), log) == []
    expected_notes = 1 if fixture == "complex3" else 0
    assert len(log) == expected_notes


def test_finding2_curveless_spanner_hidden_and_warned(
        qapp, bundle_complex3, capsys):
    """FINDING-2 regression pin (fixed 2026-07-22): complex3's sys-18 P2
    hairpin segment matches no reveal curve — it must default to hidden
    at every t (never silently visible from t=0) and the applier must
    warn loudly on construction."""
    from scoreanim.core.animation import StyleRules
    from scoreanim.core.score.identity import ElementId
    from scoreanim.tools.live_oracle import build_scene_applier

    eid = ElementId("P2:m69:s1:v0:hairpin:0:seg1")
    scenes, applier = build_scene_applier(
        bundle_complex3, StyleRules(reveal_mode=RevealMode.STEPPED))
    assert applier.uncovered_reveal_keys == {(18, "P2"): (eid,)}
    err = capsys.readouterr().err
    assert "curve-less-key" in err and str(eid) in err

    item = scenes.items[eid]
    assert item.reveal_children
    for t in (0.0, bundle_complex3.score_end / 2,
              bundle_complex3.score_end + 10.0):
        applier.refresh(t)
        assert all(c.hidden for c in item.reveal_children), t


# -- D2: trigger / model audits ---------------------------------------------

@pytest.mark.parametrize("fixture", ["testscore", "bigband", "complex3"])
def test_d2_triggers_match_engraved_onsets(request, fixture):
    assert audit_triggers(_bundle(request, fixture)) == []


@pytest.mark.parametrize("fixture", ["testscore", "bigband", "complex3"])
def test_d2_model_consistent_with_itself_and_engraving(request, fixture):
    assert audit_model_consistency(_bundle(request, fixture)) == []


@pytest.mark.parametrize("fixture", [
    pytest.param("testscore",
                 marks=pytest.mark.xfail(reason=_XF3, strict=True)),
    "bigband",
    "complex3",
])
def test_d2_reveal_anchors_monotone_in_x(request, fixture):
    assert audit_reveal_anchors(_bundle(request, fixture)) == []


@pytest.mark.parametrize("fixture", ["testscore", "bigband", "complex3"])
def test_d2_join_complete(request, fixture):
    assert audit_join(_bundle(request, fixture)) == []


@pytest.mark.parametrize("fixture", ["testscore", "bigband", "complex3"])
def test_d2_sig_nesting_measures(request, fixture):
    findings = audit_signatures(_bundle(request, fixture))
    assert [f for f in findings if f.code == "sig-nesting"] == []


def test_finding4_courtesy_sig_lights_with_change(bundle_testscore):
    """FINDING-4 regression pin (fixed 2026-07-23): testscore's m4
    end-of-system courtesy meter sig lights WITH the m5 change it
    announces; the m5 in-place sig and a system-start restatement keep
    their own measure's start."""
    starts = bundle_testscore.engraved.timeline.starts
    onsets = {str(el.identity.element_id): el.identity.onset
              for el in bundle_testscore.engraved.layout.elements}
    for part in ("P1", "P2", "P3", "P4", "P5", "P6", "P7"):
        assert onsets[f"{part}:m4:s1:v0:meter_sig:0"] == starts[5]  # 16.0
    assert onsets["P1:m5:s1:v0:meter_sig:0"] == starts[5]
    # m5 starts system 2: its key restatement stays at its own downbeat
    assert onsets["P1:m5:s1:v0:key_sig:0"] == starts[5]
    assert starts[5] != starts[4]


@pytest.mark.parametrize("fixture", ["testscore", "bigband", "complex3"])
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
