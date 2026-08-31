"""Public records and the per-load shared state.

AdapterNoteRecord / EngravedScore are the adapter's public data surface
(the ScoreModel join and every tool read them). _LoadState is the
per-load state every pipeline stage reads — and some write — placed next
to the records it feeds; each stage module's docstring lists exactly
which fields it reads and writes. Plain data; no Verovio types (rule 4).
"""

from __future__ import annotations

from collections.abc import Mapping
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
    # Per-element engraved durations in beats (M4.1): timemap off − on
    # for every note AND rest element, on the same performance axis as
    # every onset (rule 12 — no next-onset inference, no new authority).
    # A tied notehead's entry is its OWN segment length, not the chain
    # end. Absent id → no entry.
    note_durations: Mapping[ElementId, Beats] = field(default_factory=dict)
    # Measure ordinal → 1-based score-wide system index (M5). The adapter
    # has always built this (_LoadState.system_of_measure, from the SVG's
    # measure-group nesting) and used it for the repagination planner and
    # the courtesy-sig retime, then thrown it away. M5 needs the fact in
    # the app: the break toggle asks "does this measure already start a
    # system?" and the view re-anchors to the system holding the edited
    # measure. Element-free, so it is immune to the cross-system :seg
    # ordinal hazard; derived every load, never stored (rule 5).
    system_of_measure: Mapping[int, int] = field(default_factory=dict)
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
    # notes and rests → timemap off qstamp (M4.1) — the on-side's exact
    # symmetric partner; identity's element construction turns the pair
    # into per-element durations. Defaulted so synthetic test states
    # (which never resolve durations) construct unchanged.
    off_by_id: dict[str, Beats] = field(default_factory=dict)
    # system → {global staff n → staff-lines y center}, built after
    # decomposition; grpSym identity reads which staves a symbol spans
    # (geometric — Phase 10; slot bookkeeping broke on native braces,
    # which Verovio SUPPRESSES when an injected group overlaps them)
    staff_centers_by_system: dict[int, dict[int, float]] = \
        field(default_factory=dict)
    # region-fill note id → (page, system, bbox): where Verovio laid out
    # the invisible note standing in for a slash (2026-08-31). The fill
    # notes never become elements, so this geometry is all that leaves
    # them; synthesis reads it to place the slash Verovio drew nothing
    # for. Written by the decomposer.
    fill_geometry: dict[str, tuple[int, int | None, Rect]] = \
        field(default_factory=dict)
    system_count: int = 0                    # score-wide, across pages
    system_of_measure: dict[int, int] = field(default_factory=dict)
    # FINDING-4 (2026-07-23): kind → part id → measure ordinals whose
    # MusicXML <attributes> carry that signature (key/time/clef) — the
    # change measures an end-of-system courtesy sig can announce. Parsed
    # from the canonical MusicXML at state construction (provider).
    sig_changes: dict = field(default_factory=dict)
    # Last measure ordinal of each system, from system_of_measure (the
    # element-free measure-group nesting map — immune to the :seg
    # ordinal hazard); filled after decomposition, before _build_elements.
    last_of_system: set[int] = field(default_factory=set)
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
