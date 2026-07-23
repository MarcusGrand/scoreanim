"""The oracle bundle: one score, built exactly as the app builds it,
plus the raw-truth load capture D5 audits against and the small helpers
every check shares (Finding, measure-ordinal parsing).

Pure data path — no Qt here; scene/applier construction lives in
scene.py so the L0 checks stay importable without a display stack.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from scoreanim.core.animation import (RevealCurve, SystemRevealTrack,
                                      TriggerSchedule, build_reveal_tracks,
                                      build_trigger_schedule)
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import (EngravedScore,
                                              VerovioEngravingProvider)
# Adapter-stage internals, for the D5 capture only: the purity check
# audits Verovio ids against our elements, which is inherently
# adapter-internal work. Diagnosis only — nothing here feeds animation
# (rule 4 intact).
from scoreanim.core.engraving.verovio import decompose as _decompose_mod
from scoreanim.core.engraving.verovio import identity as _identity_mod
from scoreanim.core.engraving.verovio.records import _LoadState
from scoreanim.core.project.document import DEFAULT_BPM
from scoreanim.core.score.join import JoinReport, join_notes
from scoreanim.core.score.model import ScoreModel, build_score_model
from scoreanim.core.timing import TempoMap
from scoreanim.core.timing.tempo_map import TempoEvent

_MEASURE_RE = re.compile(r":m(\d+):")


# -- findings ----------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    check: str                   # "D1" | "D2" | "D3" | "D4" | "D5"
    code: str                    # mechanism slug, e.g. "curve-less-key"
    element_id: str              # proving element ("" for aggregates)
    detail: str                  # human-readable specifics


# -- load capture (D5) -------------------------------------------------------

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


# -- the bundle --------------------------------------------------------------

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


# -- shared helpers ----------------------------------------------------------

def _measure_of(eid: str) -> int | None:
    m = _MEASURE_RE.search(eid)
    return int(m.group(1)) if m else None


def _measure_starts(model: ScoreModel) -> dict[int, float]:
    """Ordinal (1-based document order, ARCHITECTURE §3 item 12) →
    start beat."""
    return {i + 1: m.start for i, m in enumerate(model.measures)}
