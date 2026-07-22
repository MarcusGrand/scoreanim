"""ScoreModel: music21 parse of the canonical MusicXML → musical facts
(notated pitches, voices, ties, document order per note), with ALL beat
accounting reconciled to the engraved MeasureTimeline (ruling
2026-07-22, FINDING-1 fix): Verovio's timemap qstamps are the single
beat authority for the whole app, so a note's onset is
``timeline.starts[ordinal] + its music21 offset WITHIN the measure``,
and MeasureInfo carries the engraved start/span — never music21's own
inter-measure accumulation, which shears on real Dorico exports
(spikes/beat_domain.py census): the X0 pickup is padded to its nominal
length (+3 beats on complex3), repeats are never expanded (the timemap
IS playback-expanded — performance axis), half-beat bars round down,
and per-part accumulation can even self-diverge (complex3 part 0
drifts +7.75 beats from the other parts by m78). Intra-measure offsets
are trustworthy (pickup notes sit at offset 0 — verified against
paddingLeft on pickup_min and complex3); the shear is inter-measure
only. Joined to layout ElementIds by core/score/join.py.

music21 quirks this code is built around (spikes/NOTES.md, T0 and the
Phase 10 triage spike):
- Part.id gets replaced by the part *name* → parts are keyed by document
  order against PreparedScore.parts.
- A multi-staff part (<staves>N</staves>) splits into N adjacent
  PartStaff objects in the score-part's slot, ids
  '<score-part-id>-Staff<k>' — the only parts whose original id
  survives. Notes are filed into the PartStaff matching their MusicXML
  <staff>, the same source as MEI @staff, so the part-local staff
  number agrees with the adapter's by construction.
- Slash measures parse as hidden full-measure Rests → slash regions come
  from PreparedScore, never from rest inspection.
- Grace notes carry the principal's offset and quarterLength 0.
- Drum notes are Unpitched/PercussionChord with display pitches.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import music21 as m21

from scoreanim.core.engraving.types import MeasureTimeline
from scoreanim.core.score.identity import Beats, PartId
from scoreanim.core.score.musicxml_prep import (PreparedScore, SlashRegion,
                                                prepare)

# MEI numbers staff positions with 0 = bottom line; for a 5-line staff in
# treble/percussion numbering, that position corresponds to diatonic E4
# ("CDEFGAB" index arithmetic: 4*7 + 2 = 30). Verified against the drum
# part: hi-hat B5 → loc 11, kick F4 → loc 1.
_DIATONIC_BOTTOM_LINE = 30


def _diatonic(step: str, octave: int) -> int:
    return octave * 7 + "CDEFGAB".index(step.upper())


@dataclass(frozen=True)
class ScoreNote:
    part: PartId
    measure: int
    staff: int                   # part-local, 1-based
    voice_label: str | None      # music21 Voice id; None when the measure
                                 # has a single implicit voice
    onset: Beats                 # global, quarter notes from score start
    grace: bool
    pitch_step: str | None       # 'A'..'G'; None for unpitched
    pitch_alter: float
    octave: int | None
    staff_loc: int | None        # staff position for unpitched notes
    order: int                   # document order within (measure, voice)
    tie: str | None = None       # 'start' | 'stop' | 'continue' | None —
                                 # animation must not re-trigger tied-to notes


@dataclass(frozen=True)
class MeasureInfo:
    number: int                  # PRINTED number (display only; identity
                                 # is the document-order ordinal)
    start: Beats                 # engraved downbeat qstamp (performance
                                 # axis — MeasureTimeline)
    quarter_length: float        # actual engraved span to the next
                                 # first-pass downbeat — NOT the nominal
                                 # signature length (ruling 2026-07-22)


@dataclass(frozen=True)
class ScoreModel:
    notes: tuple[ScoreNote, ...]
    measures: tuple[MeasureInfo, ...]
    slash_regions: tuple[SlashRegion, ...]
    parts: tuple[PartId, ...]

    def measure(self, number: int) -> MeasureInfo:
        for m in self.measures:
            if m.number == number:
                return m
        raise KeyError(f"no measure {number}")


def build_score_model(source: Path | PreparedScore,
                      timeline: MeasureTimeline) -> ScoreModel:
    """``timeline`` is REQUIRED (ruling 2026-07-22): an unreconciled
    model — one whose beats come from music21's own accumulation — is
    structurally impossible. Every production caller passes
    ``EngravedScore.timeline``."""
    prep = source if isinstance(source, PreparedScore) else prepare(source)
    score = m21.converter.parse(prep.canonical_xml, format="musicxml")
    score.toSoundingPitch(inPlace=True)

    parts = list(score.parts)
    expected = sum(p.staff_count for p in prep.parts)
    if len(parts) != expected:
        raise ValueError(f"music21 sees {len(parts)} parts, "
                         f"prep expects {expected} "
                         f"({len(prep.parts)} score-parts)")

    notes: list[ScoreNote] = []
    consumed = 0
    for info in prep.parts:
        group = parts[consumed:consumed + info.staff_count]
        consumed += info.staff_count
        if info.staff_count > 1:
            # Pin the music21 multi-staff contract (Phase 10 triage
            # spike): positional order must be staff order.
            for k, p in enumerate(group, start=1):
                if (not isinstance(p, m21.stream.PartStaff)
                        or str(p.id) != f"{info.part_id}-Staff{k}"):
                    raise ValueError(
                        f"multi-staff part {info.part_id}: expected "
                        f"PartStaff '{info.part_id}-Staff{k}' at slot "
                        f"{k}, got {type(p).__name__} {p.id!r}")
        for staff_local, part in enumerate(group, start=1):
            # ScoreNote.measure is the 1-based document-order ordinal (the join
            # key), NOT measure.number — Dorico's "X0" pickup parses to music21
            # number 0 while the adapter's MEI ordinal is 1, so the printed
            # number is neither unique nor consistent across the two sides. The
            # k-th <measure> is the same bar in music21, the DOM and the MEI
            # (verified 1:1), so the ordinal aligns the join buckets. The
            # printed number is kept for display in MeasureInfo.number only.
            for m_ordinal, measure in enumerate(
                    part.getElementsByClass(m21.stream.Measure), start=1):
                m_number = m_ordinal
                if m_ordinal not in timeline.starts:
                    raise ValueError(
                        f"measure ordinal {m_ordinal} (part "
                        f"{info.part_id}) has no engraved timeline start "
                        f"— music21 and the MEI disagree on measure count")
                # Onset = engraved downbeat + intra-measure offset. The
                # intra-measure offset is music21's and is reliable; the
                # inter-measure accumulation is the timeline's (the
                # engraved beat authority) — never measure.offset.
                m_offset = timeline.starts[m_ordinal]
                streams: list = list(measure.voices) or [measure]
                for stream in streams:
                    voice_label = (str(stream.id)
                                   if isinstance(stream, m21.stream.Voice)
                                   else None)
                    order = 0
                    for el in stream.notes:
                        # ChordSymbol (from <harmony>) is a Chord subclass
                        # and appears in .notes, but engraves as text, not
                        # noteheads
                        if isinstance(el, m21.harmony.ChordSymbol):
                            continue
                        onset = m_offset + float(el.offset)
                        grace = el.duration.isGrace
                        for sub in _flatten_pitched(el):
                            notes.append(ScoreNote(
                                part=info.part_id, measure=m_number,
                                staff=staff_local, voice_label=voice_label,
                                onset=onset, grace=grace,
                                order=order, **sub))
                            order += 1

    return ScoreModel(
        notes=tuple(notes),
        measures=_measures(parts[0], timeline),
        slash_regions=prep.slash_regions,
        parts=tuple(p.part_id for p in prep.parts),
    )


def _flatten_pitched(el: m21.note.NotRest) -> list[dict]:
    """One dict per notehead: chords expand to members (document order,
    as stored); Unpitched maps its display position to a staff loc."""
    def tie_of(n) -> str | None:
        return n.tie.type if n.tie is not None else None

    def pitched(p: m21.pitch.Pitch, tie: str | None) -> dict:
        return {"pitch_step": p.step, "pitch_alter": float(p.alter or 0.0),
                "octave": p.octave, "staff_loc": None, "tie": tie}

    def unpitched(u: m21.note.Unpitched) -> dict:
        loc = _diatonic(u.displayStep, u.displayOctave) - _DIATONIC_BOTTOM_LINE
        return {"pitch_step": None, "pitch_alter": 0.0, "octave": None,
                "staff_loc": loc, "tie": tie_of(u)}

    if isinstance(el, m21.note.Unpitched):
        return [unpitched(el)]
    if isinstance(el, m21.percussion.PercussionChord):
        return [unpitched(u) for u in el.notes]
    if isinstance(el, m21.chord.Chord):
        return [pitched(n.pitch, tie_of(n)) for n in el.notes]
    return [pitched(el.pitch, tie_of(el))]


def _measures(part: m21.stream.Part,
              timeline: MeasureTimeline) -> tuple[MeasureInfo, ...]:
    """Printed numbers from music21; starts/spans from the engraved
    timeline. One exception (beat_domain.py census): a trailing
    event-less measure (e.g. a final bar-repeat bar) has no timemap
    events, so score_end stops at its downbeat and its engraved span is
    0 — floor the FINAL measure with its notated length so the last bar
    keeps its display time. Mid-score spans always come from
    next-downbeat deltas and never under-run."""
    m21_measures = list(part.getElementsByClass(m21.stream.Measure))
    if len(m21_measures) != len(timeline.starts):
        raise ValueError(
            f"music21 sees {len(m21_measures)} measures, the engraved "
            f"timeline has {len(timeline.starts)} — the 1:1 ordinal "
            f"correspondence is load-bearing")
    infos: list[MeasureInfo] = []
    last = len(m21_measures)
    for ordinal, measure in enumerate(m21_measures, start=1):
        span = timeline.durations[ordinal]
        if ordinal == last:
            span = max(span,
                       float(Fraction(measure.barDuration.quarterLength)))
        infos.append(MeasureInfo(
            number=measure.number,
            start=timeline.starts[ordinal],
            quarter_length=span,
        ))
    return tuple(infos)
