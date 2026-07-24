"""Element-level duration resolution — the note-value settle seam (M4.2).

Turns the adapter's per-note/rest engraved durations
(``EngravedScore.note_durations``, timemap off − on — rule 12's one
axis) into a per-animated-element duration map consumed as
``TriggerSchedule.duration_by_element``. POLICY LIVES HERE, never in
the evaluator (rule 6, brief F6):

- A notehead keeps its OWN engraved entry — a tied notehead its own
  segment, a grace its fractional length (F7: graces flick).
- Attachments (stems, flags, dots, beams, accidentals, articulations,
  tremolo strokes, ledger dashes) inherit the MAX duration of their
  (part, staff, voice, quantized-onset) notehead group — the
  schedule's rule-3 key via the shared quantize_beats. The key is the
  policy: only voice-nested ink can hit a notehead group, so
  measure-attached objects (dynamics, texts, chord symbols — voice
  None) miss the table and are omitted.
- A synthesized SLASH splits its measure span evenly (span ÷ slash
  count); a BAR_REPEAT takes its whole measure span. Spans come from
  MeasureInfo.quarter_length — engraved, with the trailing event-less
  bar's notated floor already applied upstream (rule 12's one
  exception).
- Rests are OMITTED (F6): a rest's trigger is retrospective (fires
  when its silence resolves — schedule rule 4), so stretching its
  settle by its notated length would animate past the ink's own span.
  Sig kinds (bar-level glyphs, possibly FINDING-4-displaced) and
  onset-less elements are omitted too. Omitted ⇒ timescale 1.0 in the
  applier.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

from scoreanim.core.animation.schedule import (_MEASURE_RE, SIG_KINDS,
                                               is_animated, quantize_beats)
from scoreanim.core.engraving.types import Layout
from scoreanim.core.score.identity import Beats, ElementId, ElementKind
from scoreanim.core.score.model import MeasureInfo, ScoreNote

# Retrospective or bar-level ink that never stretches (F6).
_OMITTED_KINDS = frozenset({ElementKind.REST, ElementKind.MREST}) | SIG_KINDS


def resolve_durations(layout: Layout,
                      mapping: Mapping[ElementId, ScoreNote],
                      note_durations: Mapping[ElementId, Beats],
                      measures: Sequence[MeasureInfo] = ()
                      ) -> Mapping[ElementId, Beats]:
    ident_by_id = {el.identity.element_id: el.identity
                   for el in layout.elements}

    # -- notehead groups: rule-3 key → longest member's duration -----------
    group_max: dict[tuple, Beats] = {}
    for eid in mapping:
        ident = ident_by_id.get(eid)
        dur = note_durations.get(eid)
        if ident is None or ident.onset is None or dur is None:
            continue
        key = (ident.part, ident.staff, ident.voice,
               quantize_beats(ident.onset))
        if dur > group_max.get(key, 0.0):
            group_max[key] = dur

    # -- synthesized regions: slash counts + engraved measure spans --------
    slash_count: dict[tuple, int] = defaultdict(int)
    for el in layout.elements:
        ident = el.identity
        if ident.kind is ElementKind.SLASH:
            m = _MEASURE_RE.search(str(ident.element_id))
            if m:
                slash_count[(ident.part, int(m.group(1)))] += 1
    span_by_ordinal = {n: m.quarter_length
                       for n, m in enumerate(measures, start=1)}

    out: dict[ElementId, Beats] = {}
    for el in layout.elements:
        ident = el.identity
        if not is_animated(ident) or ident.kind in _OMITTED_KINDS:
            continue
        eid = ident.element_id
        if ident.kind is ElementKind.NOTEHEAD:
            if eid in note_durations:
                out[eid] = note_durations[eid]
            continue
        if ident.kind in (ElementKind.SLASH, ElementKind.BAR_REPEAT):
            m = _MEASURE_RE.search(str(eid))
            span = span_by_ordinal.get(int(m.group(1))) if m else None
            if span is None:
                continue                 # no measures supplied (synthetic)
            if ident.kind is ElementKind.SLASH:
                out[eid] = span / slash_count[(ident.part, int(m.group(1)))]
            else:
                out[eid] = span
            continue
        key = (ident.part, ident.staff, ident.voice,
               quantize_beats(ident.onset))
        dur = group_max.get(key)
        if dur is not None:
            out[eid] = dur
    return out
