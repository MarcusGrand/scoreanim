"""Identity join: ScoreModel notes ⇄ adapter note records (plan D2).

There are no shared ids between music21 and the engraving provider, so
notes are matched on musical identity — (part, measure, voice, pitch) —
paired in document order, in tiers with an explicit rule per edge case:

- plain notes: keyed by pitch only, paired by document order within the
  voice (pitch is safe because both sides parse the same canonical bytes
  at concert pitch). Onset is NOT in the key: Verovio's timemap delays a
  note that follows an appoggiatura by the grace's duration while music21
  keeps the notated beat (verified on complex1/complex2), so an
  exact-onset key misses every such principal. Document order — which
  both sides carry (ScoreNote.order / AdapterNoteRecord.order_in_voice)
  and follows time within a voice — pairs them correctly instead
  (Phase 12.1);
- chord members / unisons: same key, paired in document order;
- grace notes: their own tier (a grace never pairs with a same-pitch
  principal) — also paired by pitch in document order;
- unpitched (drums): staff position instead of pitch;
- voices: matched by number when both sides agree, by document order
  as a safety net when the label sets differ.

Failure is loud: everything unmatched on either side is reported, and
callers (and tests) treat non-empty reports as errors.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from scoreanim.core.engraving.verovio import AdapterNoteRecord
from scoreanim.core.score.identity import ElementId
from scoreanim.core.score.model import ScoreModel, ScoreNote


@dataclass(frozen=True)
class JoinReport:
    matched: tuple[tuple[ElementId, ScoreNote], ...]
    unmatched_score: tuple[ScoreNote, ...]
    unmatched_layout: tuple[AdapterNoteRecord, ...]

    @property
    def mapping(self) -> dict[ElementId, ScoreNote]:
        return dict(self.matched)

    @property
    def is_complete(self) -> bool:
        return not self.unmatched_score and not self.unmatched_layout


def _pitch_key(step: str | None, octave: int | None,
               loc: int | None) -> tuple:
    """Deliberately excludes the chromatic alter: Verovio's gestural
    accidental (accid.ges) is unreliable exactly where it matters — it is
    missing on open-tie targets and over-propagated across octaves in
    some measures (verified on the fixture, spikes/NOTES.md) — while the
    MusicXML <alter> on the music21 side is authoritative. (step, octave)
    plus document order disambiguates everything real scores produce."""
    if step is None:
        return ("loc", loc)
    return (step, octave)


def _note_key(grace: bool, pitch_key: tuple) -> tuple:
    """Onset is deliberately NOT in the key. Within a (part, measure,
    staff, voice) the two sides are paired in document order
    (`_match_voice` sorts by order / order_in_voice), so a note whose
    Verovio qstamp is shifted off its notated beat — every principal
    after an appoggiatura — still matches (Phase 12.1). Graces keep their
    own tier so a grace never pairs with a same-pitch principal."""
    if grace:
        return ("grace", pitch_key)
    return pitch_key


def _align_voices(score_labels: list[str | None],
                  layout_voices: list[int]) -> dict[str | None, int] | None:
    """Map music21 voice labels to adapter layer numbers within one
    (part, measure, staff). Returns None when counts differ."""
    if len(score_labels) != len(layout_voices):
        return None
    numeric = [int(lb) for lb in score_labels
               if lb is not None and lb.isdigit()]
    if len(numeric) == len(score_labels) and sorted(numeric) == sorted(layout_voices):
        return {lb: int(lb) for lb in score_labels}    # type: ignore[union-attr]
    # order-based safety net (labels disagree numerically)
    return dict(zip(score_labels, layout_voices))


def join_notes(model: ScoreModel,
               records: tuple[AdapterNoteRecord, ...]) -> JoinReport:
    score_groups: dict[tuple, list[ScoreNote]] = defaultdict(list)
    for note in model.notes:
        score_groups[(note.part, note.measure, note.staff)].append(note)
    layout_groups: dict[tuple, list[AdapterNoteRecord]] = defaultdict(list)
    staves_by_part: dict[str, set[int]] = defaultdict(set)
    for rec in records:
        layout_groups[(rec.part, rec.measure, rec.staff)].append(rec)
        staves_by_part[rec.part].add(rec.staff)
    multi_staff_parts = {p for p, s in staves_by_part.items() if len(s) > 1}

    matched: list[tuple[ElementId, ScoreNote]] = []
    unmatched_score: list[ScoreNote] = []
    unmatched_layout: list[AdapterNoteRecord] = []

    for group_key in sorted(set(score_groups) | set(layout_groups),
                            key=lambda k: (str(k[0]), k[1], k[2])):
        s_notes = score_groups.get(group_key, [])
        l_recs = layout_groups.get(group_key, [])

        s_labels = list(dict.fromkeys(n.voice_label for n in s_notes))
        l_voices = sorted({r.voice for r in l_recs})
        voice_map = _align_voices(sorted(s_labels, key=lambda x: (x is None, x)),
                                  l_voices)
        if voice_map is None:
            unmatched_score.extend(s_notes)
            unmatched_layout.extend(l_recs)
            continue

        by_voice_s: dict[int, list[ScoreNote]] = defaultdict(list)
        for n in s_notes:
            by_voice_s[voice_map[n.voice_label]].append(n)
        by_voice_l: dict[int, list[AdapterNoteRecord]] = defaultdict(list)
        for r in l_recs:
            by_voice_l[r.voice].append(r)

        for voice in sorted(set(by_voice_s) | set(by_voice_l)):
            _match_voice(by_voice_s.get(voice, []), by_voice_l.get(voice, []),
                         matched, unmatched_score, unmatched_layout)

    unmatched_score, unmatched_layout = _cross_staff_fallback(
        unmatched_score, unmatched_layout, multi_staff_parts, matched)

    return JoinReport(matched=tuple(matched),
                      unmatched_score=tuple(unmatched_score),
                      unmatched_layout=tuple(unmatched_layout))


def _cross_staff_fallback(
        unmatched_score: list[ScoreNote],
        unmatched_layout: list[AdapterNoteRecord],
        multi_staff_parts: set[str],
        matched: list) -> tuple[list[ScoreNote], list[AdapterNoteRecord]]:
    """A multi-staff part can have a note music21 files on one staff and
    Verovio on another (cross-staff notation); the per-(part, measure,
    staff) buckets split such a pair. Re-match the LEFTOVERS within
    (part, measure) across staves/voices by (pitch, document order).

    Multi-staff parts only, so single-staff joins are untouched
    (byte-identical), and only notes already unmatched by the primary
    pass are reconsidered — a same-pitch cross-staff partner is a strictly
    better outcome than leaving both unmatched (Phase 12.1)."""
    if not multi_staff_parts or not (unmatched_score or unmatched_layout):
        return unmatched_score, unmatched_layout

    s_left: dict[tuple, list[ScoreNote]] = defaultdict(list)
    for n in unmatched_score:
        if n.part in multi_staff_parts:
            s_left[(n.part, n.measure)].append(n)
    l_left: dict[tuple, list[AdapterNoteRecord]] = defaultdict(list)
    for r in unmatched_layout:
        if r.part in multi_staff_parts:
            l_left[(r.part, r.measure)].append(r)

    still_s: list[ScoreNote] = []
    still_l: list[AdapterNoteRecord] = []
    for key in set(s_left) | set(l_left):
        _match_voice(s_left.get(key, []), l_left.get(key, []),
                     matched, still_s, still_l)

    kept_s = [n for n in unmatched_score if n.part not in multi_staff_parts]
    kept_l = [r for r in unmatched_layout if r.part not in multi_staff_parts]
    return kept_s + still_s, kept_l + still_l


def _match_voice(s_notes: list[ScoreNote], l_recs: list[AdapterNoteRecord],
                 matched: list, unmatched_score: list,
                 unmatched_layout: list) -> None:
    """Within one (part, measure, staff, voice): multimap on the note key,
    pair equal keys in document order (breaks unison ties)."""
    s_map: dict[tuple, list[ScoreNote]] = defaultdict(list)
    for n in sorted(s_notes, key=lambda n: n.order):
        s_map[_note_key(n.grace,
                        _pitch_key(n.pitch_step, n.octave, n.staff_loc))].append(n)
    l_map: dict[tuple, list[AdapterNoteRecord]] = defaultdict(list)
    for r in sorted(l_recs, key=lambda r: r.order_in_voice):
        l_map[_note_key(r.grace,
                        _pitch_key(r.pitch_step, r.octave, r.staff_loc))].append(r)

    for key in set(s_map) | set(l_map):
        s_list = s_map.get(key, [])
        l_list = l_map.get(key, [])
        for s, r in zip(s_list, l_list):
            matched.append((r.element_id, s))
        unmatched_score.extend(s_list[len(l_list):])
        unmatched_layout.extend(l_list[len(s_list):])
