"""D1 (L0): reveal-curve coverage and the schedule<->scene id audit.

Every revealed-kind item should have a matching reveal curve. Since the
FINDING-2 fix (2026-07-22) a curve-less item is a CAUGHT condition —
default-hidden clip children + a loud applier warning — so D1 reports it
as a note, not a finding (D3 verifies the containment: such items must
be hidden at every t). The schedule<->scene id audit (F2) remains a
finding.
"""

from __future__ import annotations

from scoreanim.core.animation import REVEALED_KINDS, is_animated
from scoreanim.tools.live_oracle.bundle import Finding, OracleBundle


def check_d1(bundle: OracleBundle,
             log: list[str] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    track_keys = {(tr.system, tr.part) for tr in bundle.tracks}
    layout_ids = {el.identity.element_id
                  for el in bundle.engraved.layout.elements}

    for el in bundle.engraved.layout.elements:
        ident = el.identity
        if ident.kind not in REVEALED_KINDS:
            continue
        # A curve-less / system-less revealed item is CAUGHT since the
        # FINDING-2 fix: its clip children default to hidden and the
        # applier warns on construction. Reported as a note; D3 pins
        # that it really stays hidden at every t.
        if el.system is None:
            if log is not None:
                log.append(
                    f"D1: {ident.element_id} kind={ident.kind.name} "
                    f"part={ident.part} has no system — caught: "
                    f"default-hidden + applier warning")
        elif (el.system, ident.part) not in track_keys:
            if log is not None:
                log.append(
                    f"D1: {ident.element_id} kind={ident.kind.name} "
                    f"sys={el.system} part={ident.part} matches no "
                    f"reveal curve — caught: default-hidden + applier "
                    f"warning")

    for trig in bundle.schedule.triggers:          # F2, schedule → scene
        for eid in trig.element_ids:
            if eid not in layout_ids:
                findings.append(Finding(
                    "D1", "schedule-id-not-in-scene", eid,
                    f"trigger at beat {trig.beats} targets an id absent "
                    f"from the layout/scene — silently dropped"))
    scheduled = set(bundle.schedule.beats_by_element)  # F2, scene → schedule
    for el in bundle.engraved.layout.elements:
        ident = el.identity
        if is_animated(ident) and ident.element_id not in scheduled:
            findings.append(Finding(
                "D1", "animated-id-not-in-schedule", ident.element_id,
                f"kind={ident.kind.name} onset={ident.onset} — never "
                f"triggered, sits at opacity 1.0 forever"))
    return findings
