"""D2 (L0): the data audits — trigger-vs-onset deviations clustered by
(part, staff, delta) so misjoins and beat-domain shears cluster (F3),
the score model against itself and against Verovio's engraved time,
reveal-anchor beat-vs-x inversions, join completeness, and KEY/METER/
CLEF nesting-measure attribution vs the musical change stream (F4,
including the FINDING-4 courtesy retime).
"""

from __future__ import annotations

from collections import defaultdict
from xml.etree import ElementTree

from scoreanim.core.animation.schedule import SIG_KINDS
from scoreanim.core.score.identity import ElementKind
from scoreanim.tools.live_oracle.bundle import (Finding, OracleBundle,
                                                _measure_of, _measure_starts)

_SIG_KINDS = SIG_KINDS           # the schedule's kind-policy set


def audit_triggers(bundle: OracleBundle, *,
                   beat_tolerance: float = 1.0) -> list[Finding]:
    """Trigger-vs-engraved-onset deviations, clustered by (part, staff,
    rounded delta) — misjoins and beat-domain shears cluster (F3)."""
    ident_by_id = {el.identity.element_id: el.identity
                   for el in bundle.engraved.layout.elements}
    mapping = bundle.join.mapping
    rest_kinds = (ElementKind.REST, ElementKind.MREST)
    clusters: dict[tuple, list[tuple[int | None, str]]] = defaultdict(list)
    for eid, trigger in bundle.schedule.beats_by_element.items():
        ident = ident_by_id.get(eid)
        if ident is None or ident.onset is None:
            continue
        delta = trigger - ident.onset
        if abs(delta) <= beat_tolerance:
            continue
        if ident.kind in rest_kinds and delta > 0:
            continue                     # retrospective by design (rule 4)
        source = "join" if eid in mapping else "group-table"
        clusters[(ident.part, ident.staff, round(delta * 4) / 4,
                  source)].append((_measure_of(eid), str(eid)))
    findings: list[Finding] = []
    for (part, staff, delta, source), members in sorted(
            clusters.items(), key=lambda kv: -len(kv[1])):
        ms = sorted(m for m, _ in members if m is not None)
        span = f"m{ms[0]}..m{ms[-1]}" if ms else "?"
        sample = ", ".join(eid for _, eid in members[:3])
        findings.append(Finding(
            "D2", "trigger-onset-shift", sample.split(",")[0],
            f"part={part} staff={staff} delta~{delta:+.2f} beats via "
            f"{source}: {len(members)} elements over {span} "
            f"(e.g. {sample})"))
    return findings


def audit_model_consistency(bundle: OracleBundle) -> list[Finding]:
    """The score model against ITSELF and against Verovio's engraved
    time: ScoreNote onsets outside their own measure's span, and bars
    whose engraved (qstamp) length disagrees with the model's nominal
    quarter_length — irregular/X bars counted differently are the root
    of every beat-domain shear."""
    findings: list[Finding] = []
    starts = _measure_starts(bundle.model)
    qlen = {i + 1: m.quarter_length
            for i, m in enumerate(bundle.model.measures)}

    outside: dict[str | None, list[tuple[int, float]]] = defaultdict(list)
    for note in bundle.model.notes:
        s = starts.get(note.measure)
        if s is None or note.grace:
            continue
        if note.onset < s - 1e-6 \
                or note.onset >= s + qlen[note.measure] + 1e-6:
            outside[note.part].append((note.measure, note.onset))
    for part, members in sorted(outside.items(), key=lambda kv: str(kv[0])):
        ms = sorted(m for m, _ in members)
        m0, o0 = members[0]
        findings.append(Finding(
            "D2", "note-outside-measure", "",
            f"part={part}: {len(members)} ScoreNote onsets outside their "
            f"own measure's model span, m{ms[0]}..m{ms[-1]} (e.g. m{m0} "
            f"onset={o0} vs span [{starts[m0]}, {starts[m0] + qlen[m0]}))"
            f" — the model disagrees with itself"))

    # engraved bar length (min anchor-kind qstamp spacing) vs nominal —
    # rests/slashes/mRests included so covered downbeats still anchor
    from scoreanim.core.animation import ANCHOR_KINDS
    qstamp_min: dict[int, float] = {}
    for el in bundle.engraved.layout.elements:
        if (el.identity.kind in ANCHOR_KINDS
                and el.identity.onset is not None):
            m = _measure_of(el.identity.element_id)
            if m is not None:
                q = qstamp_min.get(m)
                qstamp_min[m] = el.identity.onset if q is None \
                    else min(q, el.identity.onset)
    ms = sorted(qstamp_min)
    for a, z in zip(ms, ms[1:]):
        if z != a + 1:
            continue                     # need adjacent sounded downbeats
        actual = qstamp_min[z] - qstamp_min[a]
        if abs(actual - qlen[a]) > 0.5:
            findings.append(Finding(
                "D2", "irregular-bar-mismatch", "",
                f"m{a} (printed {bundle.model.measures[a - 1].number}): "
                f"engraved span {actual:g} beats vs model nominal "
                f"{qlen[a]:g} — irregular bar counted differently "
                f"(min-qstamp heuristic; verify downbeats sounded)"))
    return findings


def audit_reveal_anchors(bundle: OracleBundle, *,
                         beat_tolerance: float = 1.0) -> list[Finding]:
    """Beat-vs-x inversions inside each (system, part) reveal track: an
    anchor RIGHT of another with an EARLIER beat drags the edge to its x
    that many beats early — every spanner left of it reveals before its
    music (the early slur/tie mechanism). One finding per track, worst
    gap first."""
    from scoreanim.core.animation import ANCHOR_KINDS
    raw: dict[tuple, list[tuple[float, float, str]]] = defaultdict(list)
    for el in bundle.engraved.layout.elements:
        ident = el.identity
        if (el.system is None or ident.part is None or ident.onset is None
                or ident.kind not in ANCHOR_KINDS):
            continue
        beat = bundle.schedule.beats_by_element.get(ident.element_id,
                                                    ident.onset)
        raw[(el.system, ident.part)].append(
            (beat, el.bbox.x2, str(ident.element_id)))
    findings: list[Finding] = []
    rows: list[tuple[float, tuple, int, str]] = []
    for key, entries in raw.items():
        entries.sort(key=lambda e: e[1])            # by x
        best: tuple[float, str] | None = None
        worst_gap, worst_detail, count = 0.0, "", 0
        for beat, _x, eid in entries:
            if best is not None and beat < best[0] - beat_tolerance:
                count += 1
                gap = best[0] - beat
                if gap > worst_gap:
                    worst_gap = gap
                    worst_detail = (f"{eid} (beat {beat:g}) sits right of "
                                    f"{best[1]} (beat {best[0]:g})")
            if best is None or beat > best[0]:
                best = (beat, eid)
        if count:
            rows.append((worst_gap, key, count, worst_detail))
    for gap, (system, part), count, detail in sorted(rows, reverse=True):
        findings.append(Finding(
            "D2", "reveal-anchor-inversion", detail.split(" ")[0],
            f"sys{system} part={part}: {count} anchor inversion(s), edge "
            f"up to {gap:.2f} beats early — {detail}"))
    return findings


def audit_join(bundle: OracleBundle) -> list[Finding]:
    """Join incompleteness (unmatched notes feed the group-table
    fallback and shift timing)."""
    findings: list[Finding] = []
    by_pm: dict[tuple, int] = defaultdict(int)
    for note in bundle.join.unmatched_score:
        by_pm[("score", note.part, note.measure)] += 1
    for rec in bundle.join.unmatched_layout:
        by_pm[("layout", rec.part, rec.measure)] += 1
    for (side, part, measure), n in sorted(by_pm.items()):
        findings.append(Finding(
            "D2", f"join-unmatched-{side}", "",
            f"part={part} m={measure}: {n} unmatched {side} note(s)"))
    return findings


def _system_start_measures(bundle: OracleBundle) -> set[int]:
    """First measure ordinal of each system. ANCHOR_KINDS elements only:
    cross-system spanner continuation segments keep their START measure's
    ordinal while sitting in the NEXT system, so an unfiltered minimum
    claims the previous system's last measure (found on complex3 —
    sys3's min was m10 via a tie segment when the system starts m11)."""
    from scoreanim.core.animation import ANCHOR_KINDS
    first: dict[int, int] = {}
    for el in bundle.engraved.layout.elements:
        if el.system is None or el.identity.kind not in ANCHOR_KINDS:
            continue
        m = _measure_of(el.identity.element_id)
        if m is None:
            continue
        if el.system not in first or m < first[el.system]:
            first[el.system] = m
    return set(first.values())


def _system_last_measures(bundle: OracleBundle) -> set[int]:
    """Last measure ordinal of each system — the _system_start_measures
    idiom. A max is provably immune to :seg intrusion (a continuation
    segment carries its start measure's EARLIER ordinal forward), but
    the ANCHOR_KINDS filter is kept so the two derivations stay twins."""
    from scoreanim.core.animation import ANCHOR_KINDS
    last: dict[int, int] = {}
    for el in bundle.engraved.layout.elements:
        if el.system is None or el.identity.kind not in ANCHOR_KINDS:
            continue
        m = _measure_of(el.identity.element_id)
        if m is None:
            continue
        if el.system not in last or m > last[el.system]:
            last[el.system] = m
    return set(last.values())


def _musical_changes(bundle: OracleBundle) -> dict[
        ElementKind, dict[str | None, set[int]]]:
    """Per part, the measure ordinals whose MusicXML <attributes> carry a
    key / time / clef change — parsed INDEPENDENTLY of the adapter from
    the canonical (prepared) MusicXML, so it can arbitrate F4."""
    root = ElementTree.fromstring(bundle.engraved.prepared.canonical_xml)
    out: dict[ElementKind, dict[str | None, set[int]]] = {
        k: defaultdict(set) for k in _SIG_KINDS}
    tag_kind = (("key", ElementKind.KEY_SIG),
                ("time", ElementKind.METER_SIG),
                ("clef", ElementKind.CLEF))
    for part in root.iter("part"):
        pid = part.get("id")
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            for attrs in measure.findall("attributes"):
                for tag, kind in tag_kind:
                    if attrs.find(tag) is not None:
                        out[kind][pid].add(ordinal)
    return out


def audit_signatures(bundle: OracleBundle) -> list[Finding]:
    """KEY_SIG / METER_SIG / CLEF measure attribution vs the musical
    change stream (F4). Each glyph's EXPECTED lighting measure is its
    own nesting measure for an in-place change or a system-start
    restatement, and the CHANGE measure m+1 for an end-of-system
    courtesy (the FINDING-4 retime, ruled 2026-07-23); a glyph matching
    neither shape is a sig-nesting finding, and any onset that differs
    from the expected measure's start is a sig-onset finding."""
    findings: list[Finding] = []
    starts = _measure_starts(bundle.model)
    sys_starts = _system_start_measures(bundle)
    sys_lasts = _system_last_measures(bundle)
    changes = _musical_changes(bundle)
    onset_mismatch: dict[int, list[str]] = defaultdict(list)
    for el in bundle.engraved.layout.elements:
        ident = el.identity
        if ident.kind not in _SIG_KINDS:
            continue
        m = _measure_of(ident.element_id)
        if m is None:
            findings.append(Finding(
                "D2", "sig-no-measure", ident.element_id,
                f"kind={ident.kind.name} — id carries no :m<n>: segment"))
            continue
        per_part = changes[ident.kind]
        change_set = (per_part.get(ident.part)
                      if ident.part is not None
                      else set().union(*per_part.values())
                      if per_part else set())
        change_set = change_set or set()
        if m in change_set or m in sys_starts:
            expected = m        # in-place change / system-start restatement
        elif m in sys_lasts and m + 1 in change_set:
            expected = m + 1    # end-of-system courtesy → change measure
        else:
            expected = m
            prev = max((c for c in change_set if c < m), default=None)
            nxt = min((c for c in change_set if c > m), default=None)
            findings.append(Finding(
                "D2", "sig-nesting", ident.element_id,
                f"kind={ident.kind.name} part={ident.part} nests in m={m} "
                f"(not a change measure, not a system start, not an "
                f"end-of-system courtesy; nearest changes: "
                f"prev={prev} next={nxt}) — lights at m{m}'s downbeat"))
        start = starts.get(expected)
        if ident.onset is not None and start is not None \
                and abs(ident.onset - start) > 1e-6:
            onset_mismatch[expected].append(str(ident.element_id))
    for m, eids in sorted(onset_mismatch.items()):
        s = starts[m]
        findings.append(Finding(
            "D2", "sig-onset-vs-measure-start", eids[0],
            f"m{m}: {len(eids)} sig glyph(s) with onset != the expected "
            f"measure start {s:g} (e.g. {eids[0]})"))
    return findings


def check_d2(bundle: OracleBundle) -> list[Finding]:
    return (audit_triggers(bundle)
            + audit_model_consistency(bundle)
            + audit_reveal_anchors(bundle)
            + audit_join(bundle)
            + audit_signatures(bundle))
