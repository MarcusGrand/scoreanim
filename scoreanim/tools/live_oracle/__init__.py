"""Live-oracle: offscreen diagnosis harness for live-playback timing
(docs/LIVE_TIMING_BRIEF.md, 2026-07-22). DIAGNOSIS ONLY — this tool
changes no behavior; it makes "it only happens live" deterministic.

Every live symptom decomposes into one of three layers (the brief's
governing principle; CLAUDE.md rule 2 — state is a pure function of t):

- L0: the DATA is wrong (trigger, reveal anchor, onset) — pure Python.
- L1: the APPLICATION is wrong — a fresh ``refresh(t)`` disagrees with
  the pure expectation from schedule + curves at that same t.
- L2: the application is SEQUENCE-DEPENDENT — ticking ``apply_at`` like
  live playback leaves the scene differing from one fresh ``refresh``.

Five checks, doctor-style (never a traceback; exit 1 on findings), one
module each — see each module's docstring for the full contract:

- D1 (L0, d1_curves): reveal-curve coverage + schedule<->scene id audit.
- D2 (L0, d2_triggers): trigger-vs-onset deviations, model consistency,
  reveal-anchor inversions, join completeness, sig nesting (F3/F4).
- D3 (L1, d3_state): fresh-state oracle over a time grid.
- D4 (L2, d4_ticks): live-tick differential with divergence bisection.
- D5 (L0, d5_purity): adapter kind/ink purity — straight-ink kinds hold
  no béziers, compact kinds fit sane bounds, and every MEI slur/tie the
  engraver inked yields exactly one SLUR/TIE element on its own part
  (audited against the raw SVG/MEI captured DURING the load).

    python -m scoreanim.tools.live_oracle testdata/complex3.musicxml
    python -m scoreanim.tools.live_oracle testdata/            # batch
    options: [--no-hide] [--strict] [--mode stepped|continuous|both]
             [--grid sampled|measures|full] [--checks d1,d2,d3,d4,d5]

The build path mirrors main_window._engrave_and_wire exactly (fresh-
document defaults: hide_empty_staves ON, strict OFF, 120 bpm, default
StyleRules). The check functions are importable by pytest
(tests/test_live_oracle.py) so CLI and CI probe the same build.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from scoreanim.tools.live_oracle.bundle import (Finding, LoadCapture,
                                                OracleBundle, build_bundle)
from scoreanim.tools.live_oracle.cli import main, run_checks
from scoreanim.tools.live_oracle.d1_curves import check_d1
from scoreanim.tools.live_oracle.d2_triggers import (audit_join,
                                                     audit_model_consistency,
                                                     audit_reveal_anchors,
                                                     audit_signatures,
                                                     audit_triggers,
                                                     check_d2)
from scoreanim.tools.live_oracle.d3_state import check_d3
from scoreanim.tools.live_oracle.d4_ticks import check_d4
from scoreanim.tools.live_oracle.d5_purity import (audit_kind_purity,
                                                   audit_spanner_coverage,
                                                   check_d5)
from scoreanim.tools.live_oracle.scene import build_scene_applier

__all__ = [
    "Finding", "LoadCapture", "OracleBundle", "build_bundle",
    "build_scene_applier", "check_d1", "check_d2", "check_d3", "check_d4",
    "check_d5", "audit_join", "audit_kind_purity",
    "audit_model_consistency", "audit_reveal_anchors", "audit_signatures",
    "audit_spanner_coverage", "audit_triggers", "run_checks", "main",
]
