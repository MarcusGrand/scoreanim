"""Public records and the per-load shared state.

AdapterNoteRecord / EngravedScore are the adapter's public data surface
(the ScoreModel join and every tool read them). _LoadState is the
per-load state every pipeline stage reads — and some write — placed next
to the records it feeds; each stage module's docstring lists exactly
which fields it reads and writes. Plain data; no Verovio types (rule 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scoreanim.core.engraving.svg_geom import path_bbox
from scoreanim.core.engraving.types import (Layout, LoadWarning,
                                            MeasureTimeline, Rect)
from scoreanim.core.engraving.verovio.mei_index import _MeiIndex
from scoreanim.core.score.identity import Beats, ElementId, PartId
from scoreanim.core.score.musicxml_prep import PreparedScore

# ---------------------------------------------------------------------------
# Note records exposed for the ScoreModel join (plan D2). Plain data — no
# Verovio ids or types.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AdapterNoteRecord:
    element_id: ElementId
    part: PartId
    measure: int
    staff: int                   # part-local, 1-based
    voice: int
    onset: Beats
    grace: bool
    pitch_step: str | None       # 'A'..'G'; None for unpitched
    pitch_alter: float
    octave: int | None
    staff_loc: int | None        # vertical staff position for unpitched
    chord_group: str | None      # shared token for members of one chord
    order_in_voice: int          # document order within (measure, staff, voice)


@dataclass(frozen=True)
class EngravedScore:
    layout: Layout
    note_records: tuple[AdapterNoteRecord, ...]
    prepared: PreparedScore
    # The engraved measure timeline — the app-wide beat authority
    # (ruling 2026-07-22, FINDING-1 fix). build_score_model REQUIRES it;
    # the model's beat accounting is reconciled to these qstamps.
    timeline: MeasureTimeline
    # Non-fatal load anomalies (Phase 10 ruling b): dropped spanners,
    # continuation-attribution gaps. Empty on clean loads.
    warnings: tuple[LoadWarning, ...] = ()


@dataclass
class _LoadState:
    prep: PreparedScore
    mei: _MeiIndex
    onset_by_id: dict[str, Beats]           # notes and rests → qstamp
    measure_start: dict[int, Beats]          # measure number → qstamp
    measure_duration: dict[int, Beats]       # from timemap start deltas
    staff_n_by_id: dict[str, int]
    layer_n_by_id: dict[str, int]
    # system → {global staff n → staff-lines y center}, built after
    # decomposition; grpSym identity reads which staves a symbol spans
    # (geometric — Phase 10; slot bookkeeping broke on native braces,
    # which Verovio SUPPRESSES when an injected group overlaps them)
    staff_centers_by_system: dict[int, dict[int, float]] = \
        field(default_factory=dict)
    system_count: int = 0                    # score-wide, across pages
    system_of_measure: dict[int, int] = field(default_factory=dict)
    warnings: list[LoadWarning] = field(default_factory=list)
    # Strict loads raise on an unknown drawable SVG class; app loads
    # degrade it to a static OTHER element with a warning (Phase 11.4).
    strict: bool = True
    # ties suppressed as engraving artifacts (Phase 10R): neither the
    # source element nor its continuation segments are emitted
    suppressed_spanners: set[str] = field(default_factory=set)
    _glyph_bbox_cache: dict[str, Rect] = field(default_factory=dict)

    def glyph_bbox(self, def_id: str, d: str) -> Rect:
        # def ids are "<codepoint>-<pageid>"; path data is identical across
        # pages, so cache by codepoint
        key = def_id.split("-")[0]
        if key not in self._glyph_bbox_cache:
            self._glyph_bbox_cache[key] = path_bbox(d)
        return self._glyph_bbox_cache[key]
