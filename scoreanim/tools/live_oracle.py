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

Four checks, doctor-style (never a traceback; exit 1 on findings):

- D1 (L0): every revealed-kind item should have a matching reveal
  curve. Since the FINDING-2 fix (2026-07-22) a curve-less item is a
  CAUGHT condition — default-hidden clip children + a loud applier
  warning — so D1 reports it as a note, not a finding (D3 verifies the
  containment: such items must be hidden at every t). The
  schedule<->scene id audit (F2) remains a finding.
- D2 (L0): trigger-vs-onset deviations clustered by (part, staff,
  measure) — misjoins cluster (F3); keysig/meter/clef nesting-measure
  attribution vs the musical change stream (F4).
- D3 (L1): fresh-state oracle over a time grid — refresh(t) vs the pure
  expectation from element_state / reveal_x.
- D4 (L2): live-tick differential — apply_at over a dense forward grid
  (with backward scrub seeks) vs fresh refresh at checkpoints; on
  divergence, bisect to the first diverging tick.
- D5 (L0, adapter): kind/ink purity. (a) straight-ink kinds (stem,
  ledger, beam) must hold no bézier paths, and compact kinds must fit
  sane per-kind bbox bounds — a stem 30 staff-spaces wide is somebody
  else's ink. (b) every MEI slur/tie that the engraver actually inked
  must yield exactly ONE SLUR/TIE element on its own staff's part —
  audited against the raw page SVG and MEI captured DURING the load
  (Verovio reuses xml:ids across element types under hide-empty-staves
  and can nest a spanner's curve inside a foreign stem/flag group; the
  reused id also masks the dropped-spanner warning, so the absorption
  is silent everywhere else).

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

import re
import sys
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Iterable, Iterator, Mapping, Sequence
from xml.etree import ElementTree

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from scoreanim.core.animation import (OPACITY, PRESETS, REVEALED_KINDS,
                                      RevealCurve, RevealMode, StyleRules,
                                      SystemRevealTrack, TriggerSchedule,
                                      build_presets, build_reveal_tracks,
                                      build_trigger_schedule, effect_for,
                                      element_state, is_animated,
                                      quantize_beats, reveal_x)
from scoreanim.core.animation.schedule import SIG_KINDS
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import (EngravedScore,
                                              VerovioEngravingProvider)
# Adapter-stage internals, for D5 only: the purity check audits Verovio
# ids against our elements, which is inherently adapter-internal work.
# Diagnosis only — nothing here feeds animation (rule 4 intact).
from scoreanim.core.engraving.verovio import decompose as _decompose_mod
from scoreanim.core.engraving.verovio import identity as _identity_mod
from scoreanim.core.engraving.verovio.kinds import _SVG_NS, _XML_ID
from scoreanim.core.engraving.verovio.records import _LoadState
from scoreanim.core.project.document import DEFAULT_BPM
from scoreanim.core.project.stage_config import (default_stage_config,
                                                 page_content_top)
from scoreanim.core.score.identity import ElementId, ElementKind
from scoreanim.core.score.join import JoinReport, join_notes
from scoreanim.core.score.model import ScoreModel, build_score_model
from scoreanim.core.timing import TempoMap, resolve_seconds
from scoreanim.core.timing.tempo_map import TempoEvent
from scoreanim.render.animate import AnimationApplier
from scoreanim.render.scene import ScoreScenes

_EPS_S = 1e-3                    # grid epsilon around events (seconds)
_MEASURE_RE = re.compile(r":m(\d+):")
_SIG_KINDS = SIG_KINDS           # the schedule's kind-policy set
_GRID_CAP = 500                  # sampled-grid trigger points (logged)


def _ensure_app() -> QApplication:
    return QApplication.instance() or QApplication([])


# -- findings ----------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    check: str                   # "D1" | "D2" | "D3" | "D4"
    code: str                    # mechanism slug, e.g. "curve-less-key"
    element_id: str              # proving element ("" for aggregates)
    detail: str                  # human-readable specifics


# -- the bundle: one score, built exactly as the app builds it ---------------

@dataclass
class LoadCapture:
    """Raw truth captured DURING the load, at the provider's blessed
    monkeypatch seam (stages are called module-qualified): the final
    engrave's page SVGs, the _LoadState, and the attributed accumulators
    exactly as _build_elements received them. D5 audits against these;
    the retry loops (hide-unavailable / repagination / scale-to-fit)
    re-engrave, so each fresh page-1 decompose resets the page capture
    and the LAST _build_elements call wins — the one that produced the
    returned EngravedScore."""
    svg_pages: dict[int, str] = field(default_factory=dict)
    state: _LoadState | None = None
    accumulators: list = field(default_factory=list)


@contextmanager
def _capturing_load(cap: LoadCapture) -> Iterator[None]:
    real_decomposer = _decompose_mod._PageDecomposer
    real_build = _identity_mod._build_elements

    class _CapturingDecomposer(real_decomposer):  # type: ignore[misc,valid-type]
        def __init__(self, svg_text: str, page: int, adapter) -> None:
            if page == 1:                # a retry loop started a fresh engrave
                cap.svg_pages.clear()
            cap.svg_pages[page] = svg_text
            super().__init__(svg_text, page, adapter)

    def _capturing_build(accumulators, st):
        cap.state = st
        cap.accumulators = list(accumulators)
        return real_build(accumulators, st)

    _decompose_mod._PageDecomposer = _CapturingDecomposer
    _identity_mod._build_elements = _capturing_build
    try:
        yield
    finally:
        _decompose_mod._PageDecomposer = real_decomposer
        _identity_mod._build_elements = real_build


@dataclass
class OracleBundle:
    path: Path
    engraved: EngravedScore
    model: ScoreModel
    join: JoinReport
    schedule: TriggerSchedule
    score_end: float
    tracks: tuple[SystemRevealTrack, ...]
    tempo_map: TempoMap
    capture: LoadCapture | None = None
    curves: tuple[RevealCurve, ...] = field(init=False)
    curve_by_key: dict[tuple, RevealCurve] = field(init=False)

    def __post_init__(self) -> None:
        self.curves = tuple(tr.resolve(self.tempo_map) for tr in self.tracks)
        self.curve_by_key = {(c.system, c.part): c for c in self.curves}


def build_bundle(path: Path, *, hide_empty_staves: bool = True,
                 strict: bool = False,
                 engraved: EngravedScore | None = None) -> OracleBundle:
    """Mirror of main_window._engrave_and_wire's data path. ``engraved``
    lets pytest reuse its session-cached loads (no capture then — D5's
    spanner-coverage sub-check needs a fresh capturing load)."""
    capture: LoadCapture | None = None
    if engraved is None:
        capture = LoadCapture()
        with _capturing_load(capture):
            engraved = VerovioEngravingProvider().load_detailed(
                path, EngravingParams(),
                hide_empty_staves=hide_empty_staves, strict=strict)
    model = build_score_model(engraved.prepared, engraved.timeline)
    join = join_notes(model, engraved.note_records)
    schedule = build_trigger_schedule(engraved.layout, join.mapping,
                                      model.measures)
    score_end = max((m.start + m.quarter_length for m in model.measures),
                    default=0.0)
    tracks = build_reveal_tracks(engraved.layout, schedule, score_end)
    tempo_map = TempoMap([TempoEvent(0.0, DEFAULT_BPM)])
    return OracleBundle(path=path, engraved=engraved, model=model,
                        join=join, schedule=schedule, score_end=score_end,
                        tracks=tracks, tempo_map=tempo_map, capture=capture)


def build_scene_applier(bundle: OracleBundle,
                        style: StyleRules) -> tuple[ScoreScenes,
                                                    AnimationApplier]:
    """Scenes + applier as the window builds them (fresh-document
    defaults; ghost opacity = the style's floor, as _sync_styles ends up
    applying)."""
    _ensure_app()
    stage = default_stage_config(bundle.engraved.prepared,
                                 page_content_top(bundle.engraved.layout))
    scenes = ScoreScenes(bundle.engraved.layout, stage,
                         ghost_opacity=style.floor_opacity)
    applier = AnimationApplier(scenes.items, bundle.schedule,
                               bundle.tempo_map, style, bundle.tracks)
    return scenes, applier


# -- shared helpers ----------------------------------------------------------

def _measure_of(eid: str) -> int | None:
    m = _MEASURE_RE.search(eid)
    return int(m.group(1)) if m else None


def _measure_starts(model: ScoreModel) -> dict[int, float]:
    """Ordinal (1-based document order, ARCHITECTURE §3 item 12) →
    start beat."""
    return {i + 1: m.start for i, m in enumerate(model.measures)}


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


def _trigger_seconds_by_eid(bundle: OracleBundle) -> dict[ElementId, float]:
    eids = list(bundle.schedule.beats_by_element)
    secs = resolve_seconds(
        [bundle.schedule.beats_by_element[e] for e in eids],
        bundle.tempo_map, ())
    return dict(zip(eids, secs))


def _effects_by_eid(bundle: OracleBundle, style: StyleRules) -> dict:
    """Effect resolution exactly as the applier resolves it — recomputed
    here so the oracle's expectation is independent of the applier's
    caches."""
    presets = {**PRESETS, **build_presets(style.floor_opacity)}
    ident_by_id = {el.identity.element_id: el.identity
                   for el in bundle.engraved.layout.elements}
    return {eid: effect_for(style.resolve(ident_by_id[eid]).effect, presets)
            for eid in bundle.schedule.beats_by_element
            if eid in ident_by_id}


# -- D1 (L0): curve audit ----------------------------------------------------

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


# -- D2 (L0): trigger audit --------------------------------------------------

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


# -- observable state --------------------------------------------------------

def _snapshot(scenes: ScoreScenes) -> dict:
    out = {}
    for eid, item in scenes.items.items():
        clips = tuple(
            (None if c.clip_right is None else round(c.clip_right, 4),
             c.hidden)
            for c in item.reveal_children)
        out[eid] = (round(item.opacity(), 6), round(item.scale(), 6), clips)
    return out


def _expected_clip(child, edge_scene_x: float):
    """set_clip_right's math with a FRESHLY inverted scene transform (the
    cached one is an F5 suspect)."""
    inv, ok = child.sceneTransform().inverted()
    if not ok:
        return None, False
    local_x = inv.map(QPointF(edge_scene_x, 0.0)).x()
    br = child.boundingRect()
    clip = min(max(local_x, br.left()), br.right())
    if clip >= br.right():
        return None, False
    return clip, clip <= br.left()


# -- D3 (L1): fresh-state oracle ---------------------------------------------

def _time_grid(bundle: OracleBundle, grid: str,
               log: list[str]) -> list[float]:
    beats = sorted({m.start for m in bundle.model.measures})
    pts: list[float] = []
    for s in resolve_seconds(beats, bundle.tempo_map, ()):
        pts += [s - _EPS_S, s + _EPS_S]
    if grid != "measures":
        trig = resolve_seconds([t.beats for t in bundle.schedule.triggers],
                               bundle.tempo_map, ())
        if grid == "sampled" and len(trig) > _GRID_CAP:
            stride = -(-len(trig) // _GRID_CAP)
            log.append(f"D3 grid: sampling every {stride}th of "
                       f"{len(trig)} triggers (use --grid full for all)")
            trig = trig[::stride]
        for s in trig:
            pts += [s - _EPS_S, s + _EPS_S]
    return sorted({round(p, 6) for p in pts if p >= 0.0})


def check_d3(bundle: OracleBundle, mode: RevealMode, grid: str,
             log: list[str]) -> list[Finding]:
    style = StyleRules(reveal_mode=mode)
    scenes, applier = build_scene_applier(bundle, style)
    trig_s = _trigger_seconds_by_eid(bundle)
    effects = _effects_by_eid(bundle, style)

    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()   # (code, eid): first-t only
    for t in _time_grid(bundle, grid, log):
        applier.refresh(t)
        # opacity vs the pure kernel
        for eid, eff in effects.items():
            item = scenes.items.get(eid)
            if item is None:
                continue                 # D1's schedule-id-not-in-scene
            expected = element_state(trig_s[eid], eff, t).get(OPACITY)
            if expected is None:
                continue
            if abs(item.opacity() - expected) > 1e-6 \
                    and ("opacity", eid) not in seen:
                seen.add(("opacity", eid))
                findings.append(Finding(
                    "D3", "opacity-mismatch", eid,
                    f"t={t:.3f}s ({mode.name}): scene opacity "
                    f"{item.opacity():.4f} != expected {expected:.4f}"))
        # reveal clips vs reveal_x
        for eid, item in scenes.items.items():
            ident = item.identity
            if (ident is None or ident.kind not in REVEALED_KINDS
                    or item.system is None):
                continue
            curve = bundle.curve_by_key.get((item.system, ident.part))
            if curve is None:
                # FINDING-2 containment: a curve-less item never
                # receives an edge, so it must sit at the hidden
                # construction default at EVERY t
                for k, child in enumerate(item.reveal_children):
                    if not child.hidden and ("clip", eid) not in seen:
                        seen.add(("clip", eid))
                        findings.append(Finding(
                            "D3", "curveless-not-hidden", eid,
                            f"t={t:.3f}s ({mode.name}) child {k}: no "
                            f"reveal curve for (sys {item.system}, part "
                            f"{ident.part}) yet clip_right="
                            f"{child.clip_right} is not hidden — "
                            f"visible-from-t0 regression (FINDING-2)"))
                continue
            edge = reveal_x(curve, t, mode)
            for k, child in enumerate(item.reveal_children):
                exp_clip, exp_hidden = _expected_clip(child, edge)
                got = child.clip_right
                clip_ok = ((got is None and exp_clip is None)
                           or (got is not None and exp_clip is not None
                               and abs(got - exp_clip) <= 1e-4))
                if (not clip_ok or child.hidden != exp_hidden) \
                        and ("clip", eid) not in seen:
                    seen.add(("clip", eid))
                    findings.append(Finding(
                        "D3", "clip-mismatch", eid,
                        f"t={t:.3f}s ({mode.name}) child {k}: clip_right "
                        f"{got} != expected {exp_clip} "
                        f"(hidden {child.hidden} vs {exp_hidden})"))
    return findings


# -- D4 (L2): live-tick differential -----------------------------------------

def _tick_times(bundle: OracleBundle) -> list[float]:
    """Dense forward grid (~4 ticks/beat) with two backward scrub seeks:
    at 40% jump back to 15% and replay, at 75% jump back to 55%."""
    n = max(2, int(bundle.score_end * 4))
    beats = [bundle.score_end * i / n for i in range(n + 1)]
    base = resolve_seconds(beats, bundle.tempo_map, ())
    i40, i15 = int(len(base) * 0.40), int(len(base) * 0.15)
    i75, i55 = int(len(base) * 0.75), int(len(base) * 0.55)
    return (base[:i40] + base[i15:i75] + base[i55:])


def _checkpoints(bundle: OracleBundle) -> set[float]:
    beats = sorted({m.start for m in bundle.model.measures})
    secs = resolve_seconds(beats, bundle.tempo_map, ())
    return {round(s, 9) for s in secs}


def check_d4(bundle: OracleBundle, mode: RevealMode,
             log: list[str]) -> list[Finding]:
    style = StyleRules(reveal_mode=mode)
    scenes_a, app_a = build_scene_applier(bundle, style)
    scenes_b, app_b = build_scene_applier(bundle, style)
    ticks = _tick_times(bundle)
    checkpoints = _checkpoints(bundle)
    checkpoints.add(round(ticks[-1], 9))

    diverged_at: int | None = None
    diff_ids: list[str] = []
    for i, t in enumerate(ticks):
        app_a.apply_at(t)
        if round(t, 9) not in checkpoints:
            continue
        snap_a = _snapshot(scenes_a)
        app_b.refresh(t)
        snap_b = _snapshot(scenes_b)
        if snap_a != snap_b:
            diverged_at = i
            diff_ids = [str(k) for k in snap_a
                        if snap_a[k] != snap_b.get(k)]
            break
    if diverged_at is None:
        return []

    # bisect the tick prefix to the first diverging tick: smallest m such
    # that replaying ticks[:m+1] differs from a fresh refresh at ticks[m]
    def prefix_diverges(m: int) -> list[str]:
        scenes_c, app_c = build_scene_applier(bundle, style)
        for t in ticks[:m + 1]:
            app_c.apply_at(t)
        app_b.refresh(ticks[m])
        snap_c, snap_b2 = _snapshot(scenes_c), _snapshot(scenes_b)
        return [str(k) for k in snap_c if snap_c[k] != snap_b2.get(k)]

    lo, hi = 0, diverged_at              # hi known-diverging
    while lo < hi:
        mid = (lo + hi) // 2
        if prefix_diverges(mid):
            hi = mid
        else:
            lo = mid + 1
    first_diff = prefix_diverges(lo) or diff_ids
    back = " (a backward-seek tick)" if lo > 0 \
        and ticks[lo] < ticks[lo - 1] else ""
    log.append(f"D4 ({mode.name}): first divergence at tick {lo} "
               f"t={ticks[lo]:.3f}s{back}, {len(first_diff)} item(s)")
    return [Finding(
        "D4", "sequence-divergence", eid,
        f"{mode.name}: apply_at ticking diverges from refresh at tick "
        f"{lo} (t={ticks[lo]:.3f}s{back})") for eid in first_diff[:50]]


# -- D5 (L0): kind/ink purity ------------------------------------------------

# Kinds whose own ink is straight by construction: stems are rects,
# ledger dashes are lines, beams are polygons. A C/S/Q bézier inside one
# of these is foreign ink (a spanner curve swallowed by id reuse).
_STRAIGHT_INK_KINDS = {ElementKind.STEM, ElementKind.LEDGER_LINES,
                       ElementKind.BEAM}

# Sane per-kind bbox bounds, in staff spaces (max_w, max_h). Generous —
# a cross-staff piano stem spans two staves and the gap (~16sp tall);
# the corrupted hosts measure 15-35sp WIDE, an order of magnitude out.
_KIND_BBOX_SP: dict[ElementKind, tuple[float, float]] = {
    ElementKind.STEM: (4.0, 24.0),
    ElementKind.FLAG: (6.0, 12.0),
    ElementKind.NOTEHEAD: (8.0, 8.0),
    ElementKind.ACCIDENTAL: (6.0, 12.0),
    ElementKind.ARTICULATION: (8.0, 8.0),
    ElementKind.LEDGER_LINES: (12.0, 3.0),
}

_CURVE_CMD_RE = re.compile(r"[CcSsQqTt]")
_SPANNER_SVG_CLASSES = ("slur", "tie", "lv")
_SPANNER_KIND_BY_TAG = {"slur": ElementKind.SLUR, "tie": ElementKind.TIE,
                        "lv": ElementKind.TIE}
_DRAWABLE_TAGS = {"use", "path", "rect", "line", "polygon", "polyline",
                  "ellipse", "circle", "text"}


def _staff_space(bundle: OracleBundle) -> float | None:
    """One staff space in layout units: median STAFF_LINES bbox height is
    4 spaces. Scale-to-fit shrinks both, so bounds track the engraving."""
    heights = [el.bbox.h for el in bundle.engraved.layout.elements
               if el.identity.kind is ElementKind.STAFF_LINES
               and el.bbox.h > 0]
    return median(heights) / 4.0 if heights else None


def audit_kind_purity(bundle: OracleBundle,
                      log: list[str] | None = None) -> list[Finding]:
    """(a) Straight-ink kinds must hold no bézier paths; compact kinds
    must fit sane per-kind bbox bounds. Either violation means the
    element carries somebody else's ink and will fire it at ITS onset —
    the early-slur mechanism."""
    findings: list[Finding] = []
    sp = _staff_space(bundle)
    if sp is None or sp <= 0:
        if log is not None:
            log.append("D5: no staff-lines geometry — purity bounds skipped")
        return findings
    for el in bundle.engraved.layout.elements:
        kind = el.identity.kind
        eid = str(el.identity.element_id)
        if kind in _STRAIGHT_INK_KINDS:
            curved = sum(1 for p in el.glyph.paths
                         if _CURVE_CMD_RE.search(p.d))
            if curved:
                findings.append(Finding(
                    "D5", "kind-curve-ink", eid,
                    f"kind={kind.name} carries {curved} bézier path(s) of "
                    f"{len(el.glyph.paths)} — foreign curve ink folded in "
                    f"(bbox {el.bbox.w:.0f}x{el.bbox.h:.0f} = "
                    f"{el.bbox.w / sp:.1f}x{el.bbox.h / sp:.1f} sp)"))
                continue                 # one finding per element suffices
        bound = _KIND_BBOX_SP.get(kind)
        if bound is not None:
            max_w, max_h = bound
            if el.bbox.w > max_w * sp or el.bbox.h > max_h * sp:
                findings.append(Finding(
                    "D5", "kind-bbox-oversize", eid,
                    f"kind={kind.name} bbox {el.bbox.w:.0f}x{el.bbox.h:.0f} "
                    f"= {el.bbox.w / sp:.1f}x{el.bbox.h / sp:.1f} sp exceeds "
                    f"the sane bound {max_w:g}x{max_h:g} sp — foreign ink "
                    f"folded in"))
    return findings


def audit_spanner_coverage(bundle: OracleBundle,
                           log: list[str] | None = None) -> list[Finding]:
    """(b) Every MEI slur/tie the engraver inked must yield exactly one
    SLUR/TIE element attributed to its own staff's part. Two truth
    sources from the load capture: the raw page SVGs (which spanner
    groups actually carry ink) and the accumulator list (where each id's
    ink ended up). Identity minting is re-run over the captured
    accumulators — the same pure loop _build_elements runs — so the
    reported ElementIds match the layout exactly."""
    cap = bundle.capture
    if cap is None or cap.state is None:
        if log is not None:
            log.append("D5: prebuilt engraving, no load capture — "
                       "spanner-coverage sub-check skipped")
        return []
    st = cap.state
    findings: list[Finding] = []
    layout_ids = {str(el.identity.element_id)
                  for el in bundle.engraved.layout.elements}

    # Independent SVG truth: id-bearing slur/tie groups that carry ink.
    svg_inked: dict[str, int] = {}
    for page in sorted(cap.svg_pages):
        root = ElementTree.fromstring(cap.svg_pages[page])
        for g in root.iter(f"{_SVG_NS}g"):
            cls = (g.get("class") or "").split()[0] if g.get("class") else ""
            if cls not in _SPANNER_SVG_CLASSES:
                continue
            cid = g.get(_XML_ID) or g.get("id")
            if not cid:
                continue         # id-less continuation segment (own pipeline)
            if any(e.tag.removeprefix(_SVG_NS) in _DRAWABLE_TAGS
                   for e in g.iter() if e is not g):
                svg_inked.setdefault(cid, page)

    # Where each verovio id's ink ended up, with the identity it minted —
    # the exact _build_elements first-pass loop (same skips, same
    # counters), so eids match the layout byte for byte.
    counters: dict[tuple, int] = defaultdict(int)
    minted: dict[str, list] = defaultdict(list)
    for page, acc in cap.accumulators:
        if acc.continuation:
            continue
        if acc.verovio_id in st.suppressed_spanners:
            continue
        ident = _identity_mod._identity_for(acc, page, st, counters)
        if acc.verovio_id:
            minted[acc.verovio_id].append((acc, ident))

    for vid, tag in sorted(st.mei.spanner_tags.items()):
        want = _SPANNER_KIND_BY_TAG.get(tag)
        if want is None:
            continue             # hairpin/octave: out of D5's slur/tie scope
        if vid in st.suppressed_spanners:
            continue             # implausible tie: intentionally absent
        entries = minted.get(vid, [])
        spanner_entries = [(a, i) for a, i in entries
                           if a.svg_class in _SPANNER_SVG_CLASSES]
        host_entries = [(a, i) for a, i in entries
                        if a.svg_class not in _SPANNER_SVG_CLASSES]
        start_id, _ = st.mei.spanners.get(vid, (None, None))
        start_note = st.mei.notes.get(start_id or "")
        staff_n = (start_note.staff if start_note is not None
                   else st.mei.staff_attr_by_id.get(vid, 0))
        expected_part = (st.prep.part_for_staff(staff_n).part_id
                         if staff_n else None)
        where = (f"starts {expected_part} m{start_note.measure}"
                 if start_note is not None else f"staff {staff_n or '?'}")

        if not spanner_entries:
            if host_entries:
                hosts = ", ".join(
                    f"{i.element_id}"
                    + ("(+curve ink)" if any(_CURVE_CMD_RE.search(p.d)
                                             for p in a.paths) else "")
                    for a, i in host_entries)
                findings.append(Finding(
                    "D5", "spanner-absorbed", vid,
                    f"{tag} ({where}): no {want.name} element minted — its "
                    f"reused id is claimed by non-spanner group(s) {hosts}; "
                    f"the reused id also masks the dropped-spanner warning"))
            elif vid in svg_inked:
                findings.append(Finding(
                    "D5", "spanner-ink-lost", vid,
                    f"{tag} ({where}): inked <g> on page {svg_inked[vid]} "
                    f"but no element and no accumulator — decompose lost it"))
            # else: engraver drew nothing — the dropped-spanner warning path
            continue
        if len(spanner_entries) > 1:
            findings.append(Finding(
                "D5", "spanner-duplicate", vid,
                f"{tag} ({where}): {len(spanner_entries)} spanner elements "
                f"minted for one id: "
                f"{', '.join(str(i.element_id) for _, i in spanner_entries)}"))
        acc, ident = spanner_entries[0]
        if ident.kind is not want:
            findings.append(Finding(
                "D5", "spanner-wrong-kind", vid,
                f"{tag} ({where}): minted {ident.element_id} "
                f"kind={ident.kind.name}, expected {want.name}"))
        if expected_part is not None and ident.part != expected_part:
            findings.append(Finding(
                "D5", "spanner-wrong-part", vid,
                f"{tag} ({where}): minted {ident.element_id} on part "
                f"{ident.part}, expected {expected_part}"))
        if str(ident.element_id) not in layout_ids:
            findings.append(Finding(
                "D5", "spanner-element-missing", vid,
                f"{tag} ({where}): identity {ident.element_id} minted but "
                f"absent from the layout (ink-less accumulator)"))

    # SVG cross-check: an inked spanner group whose id minted no spanner
    # element and isn't an MEI spanner at all (should never happen).
    for cid, page in sorted(svg_inked.items()):
        if cid not in st.mei.spanner_tags:
            findings.append(Finding(
                "D5", "spanner-unknown-id", cid,
                f"inked spanner <g> on page {page} with an id the MEI has "
                f"no slur/tie/hairpin for"))
    return findings


def check_d5(bundle: OracleBundle,
             log: list[str] | None = None) -> list[Finding]:
    return audit_kind_purity(bundle, log) + audit_spanner_coverage(bundle, log)


# -- report / CLI ------------------------------------------------------------

_SHOW = 10                       # element ids listed per finding group


def _print_report(path: Path, bundle: OracleBundle,
                  findings: Sequence[Finding], log: Iterable[str],
                  checks: Sequence[str]) -> None:
    warn = defaultdict(int)
    for w in bundle.engraved.warnings:
        warn[w.code] += 1
    print(f"{path.name}")
    print(f"  census  elements={len(bundle.engraved.layout.elements)} "
          f"triggers={len(bundle.schedule.triggers)} "
          f"tracks={len(bundle.tracks)} "
          f"join={len(bundle.join.matched)}/{len(bundle.model.notes)} "
          f"warnings={dict(sorted(warn.items())) or 'none'}")
    for line in log:
        print(f"  note    {line}")
    by_check: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_check[f.check].append(f)
    for check in checks:
        fs = by_check.get(check.upper(), [])
        if not fs:
            print(f"  {check.upper()}      PASS")
            continue
        by_code: dict[str, list[Finding]] = defaultdict(list)
        for f in fs:
            by_code[f.code].append(f)
        print(f"  {check.upper()}      FAIL  {len(fs)} finding(s)")
        for code, group in sorted(by_code.items()):
            print(f"    [{code}] x{len(group)}")
            for f in group[:_SHOW]:
                eid = f"{f.element_id}  " if f.element_id else ""
                print(f"      {eid}{f.detail}")
            if len(group) > _SHOW:
                print(f"      ... +{len(group) - _SHOW} more")


def run_checks(bundle: OracleBundle, checks: Sequence[str],
               modes: Sequence[RevealMode], grid: str,
               log: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    if "d1" in checks:
        findings += check_d1(bundle, log)
    if "d2" in checks:
        findings += check_d2(bundle)
    if "d3" in checks:
        for mode in modes:
            findings += check_d3(bundle, mode, grid, log)
    if "d4" in checks:
        for mode in modes:
            findings += check_d4(bundle, mode, log)
    if "d5" in checks:
        findings += check_d5(bundle, log)
    return findings


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    def _opt(name: str, default: str | None = None) -> str | None:
        if name in args:
            i = args.index(name)
            args.pop(i)
            return args.pop(i)
        return default

    hide = "--no-hide" not in args
    if not hide:
        args.remove("--no-hide")
    strict = "--strict" in args
    if strict:
        args.remove("--strict")
    mode_arg = _opt("--mode", "both")
    grid = _opt("--grid", "sampled")
    checks = (_opt("--checks", "d1,d2,d3,d4,d5") or "").lower().split(",")
    if len(args) != 1 or mode_arg not in ("stepped", "continuous", "both") \
            or grid not in ("sampled", "measures", "full"):
        print(__doc__)
        return 2
    modes = {"stepped": [RevealMode.STEPPED],
             "continuous": [RevealMode.CONTINUOUS],
             "both": [RevealMode.STEPPED, RevealMode.CONTINUOUS]}[mode_arg]

    root = Path(args[0])
    if not root.exists():
        print(f"no such file or directory: {root}")
        return 2
    targets = sorted(root.glob("*.musicxml")) if root.is_dir() else [root]
    if not targets:
        print(f"no .musicxml files in {root}")
        return 2

    failures = 0
    for path in targets:
        log: list[str] = []
        try:
            bundle = build_bundle(path, hide_empty_staves=hide,
                                  strict=strict)
        except Exception as exc:                          # noqa: BLE001
            print(f"{path.name}\n  FAIL  [build] "
                  f"{type(exc).__name__}: {exc}")
            failures += 1
            continue
        findings = run_checks(bundle, checks, modes, grid, log)
        _print_report(path, bundle, findings, log, checks)
        if findings:
            failures += 1

    if len(targets) > 1:
        print(f"\n{len(targets) - failures}/{len(targets)} clean")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
