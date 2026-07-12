"""Trigger schedule: when each animated element fires, in beats.

Built once per (score, join) from the Layout identities plus the
ScoreModel join mapping; pure data downstream. The three rules that make
it musically correct on real Dorico exports (spikes/NOTES.md):

1. Tie gating. Tied-to noteheads appear as fresh timemap onsets (all 58
   tie-stops + 6 continues on the fixture), so triggering on
   ``identity.onset`` alone would re-fire them. A notehead whose
   ScoreNote.tie is 'stop'/'continue' inherits the trigger of the
   nearest earlier 'start'/'continue' of the same (part, staff, pitch) —
   propagating to the chain start — so it never re-triggers, and
   scrubbing into the middle of a tie lands in the lit state (the note
   is sounding there). The voice label is deliberately NOT part of the
   chain key: MusicXML voice labels are per-measure and change exactly
   where ties cross barlines (verified: the fixture's m18→19 hi-hat tie
   starts in an implicit single voice, label None, and stops in voice
   '5'). Plain same-pitch notes interleaved from other voices are
   skipped by the backward scan; an intervening 'stop' ends the scan (a
   closed chain never donates its trigger to a later orphan).

2. Grace timing. Grace ScoreNotes carry the principal's onset, but the
   layout identity carries Verovio's fractional qstamp (just before the
   beat) — the musically right trigger, so graces use ``identity.onset``.

3. Attachment grouping. Stems/flags/accidentals/articulations/dots carry
   their owner's onset but no owner id, so they resolve through a group
   table keyed (part, staff, voice, quantized onset) built from the
   noteheads. A group with ANY fresh notehead triggers at the notated
   onset (a chord containing one tied-over note still articulates);
   only an all-tied group inherits the earliest chain-start trigger.
   Beams/ties/slurs resolve through the same table at their start onset;
   a lookup miss (e.g. synthesized slashes) falls back to
   ``identity.onset``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

from scoreanim.core.engraving.types import Layout
from scoreanim.core.score.identity import (Beats, ElementId, ElementIdentity,
                                           ElementKind)
from scoreanim.core.score.model import ScoreNote

_Q = 4096                    # exact for binary subdivisions (join convention)


def quantize_beats(beats: Beats) -> int:
    """Shared beat quantizer: simultaneity is decided at 1/4096-beat
    resolution everywhere (schedule grouping, reveal anchors)."""
    return round(beats * _Q)


# Ink that dims and lights via opacity triggers. SLUR/TIE left this set
# in Phase 5.2: spanners (with HAIRPIN) reveal by clip-grow at reveal_x
# instead (REVEALED_KINDS in core/animation/reveal.py) — their opacity
# stays 1.0 and they carry no trigger. REST/MREST/DYNAMIC joined
# (ruling 2026-07-12, superseding the Phase 3 taxonomy): everything IN
# the staves is dimmed and revealed; a rest fires at its notated onset,
# a dynamic at its attach point (adapter resolves @tstamp/@startid).
# Statics remain: clefs, key/time signatures, barlines, staff lines,
# texts, lyrics, chord symbols.
ANIMATED_KINDS = frozenset({
    ElementKind.NOTEHEAD, ElementKind.SLASH, ElementKind.STEM,
    ElementKind.FLAG, ElementKind.BEAM, ElementKind.ACCIDENTAL,
    ElementKind.ARTICULATION, ElementKind.LEDGER_LINES,
    ElementKind.REST, ElementKind.MREST, ElementKind.DYNAMIC,
})


def is_animated(identity: ElementIdentity) -> bool:
    """Note-owned ink dims and lights; scaffold stays at full opacity.

    OTHER-with-onset covers augmentation dots (and any future note-owned
    fragment the adapter classifies as OTHER but stamps with an onset).
    """
    if identity.kind in ANIMATED_KINDS:
        return identity.onset is not None
    return identity.kind is ElementKind.OTHER and identity.onset is not None


@dataclass(frozen=True)
class Trigger:
    beats: Beats
    page: int                            # page of this beat's FRESH onsets
    element_ids: tuple[ElementId, ...]


@dataclass(frozen=True)
class TriggerSchedule:
    triggers: tuple[Trigger, ...]        # sorted by beats
    beat_values: tuple[float, ...]       # parallel array for bisect
    beats_by_element: Mapping[ElementId, Beats]


def _pitch_key(note: ScoreNote) -> tuple:
    # Same convention as the identity join: (step, octave) without the
    # chromatic alter, staff position for unpitched (see join._pitch_key).
    if note.pitch_step is None:
        return ("loc", note.staff_loc)
    return (note.pitch_step, note.octave)


def build_trigger_schedule(layout: Layout,
                           mapping: Mapping[ElementId, ScoreNote]
                           ) -> TriggerSchedule:
    ident_by_id = {el.identity.element_id: el.identity
                   for el in layout.elements}

    # -- rule 1 + 2: notehead triggers via tie-chain walk ------------------
    chains: dict[tuple, list[tuple[ScoreNote, ElementId]]] = defaultdict(list)
    for eid, note in mapping.items():
        if eid in ident_by_id:
            chains[(note.part, note.staff,
                    _pitch_key(note))].append((note, eid))

    note_trigger: dict[ElementId, Beats] = {}
    for members in chains.values():
        members.sort(key=lambda pair: (pair[0].onset,
                                       pair[0].voice_label or "",
                                       pair[0].order))
        resolved: list[tuple[str | None, Beats]] = []   # (tie, trigger)
        for note, eid in members:
            ident = ident_by_id[eid]
            own = ident.onset if note.grace and ident.onset is not None \
                else note.onset
            trigger = own
            if note.tie in ("stop", "continue"):
                for earlier_tie, earlier_trigger in reversed(resolved):
                    if earlier_tie in ("start", "continue"):
                        trigger = earlier_trigger
                        break
                    if earlier_tie == "stop":
                        break            # closed chain; orphan keeps own onset
            note_trigger[eid] = trigger
            resolved.append((note.tie, trigger))

    # -- rule 3: group table from the noteheads ----------------------------
    group_triggers: dict[tuple, list[tuple[Beats, Beats]]] = defaultdict(list)
    for eid, trigger in note_trigger.items():
        ident = ident_by_id[eid]
        own = ident.onset
        if own is None:                  # defensive; noteheads always carry one
            continue
        key = (ident.part, ident.staff, ident.voice, quantize_beats(own))
        group_triggers[key].append((trigger, own))

    group_trigger: dict[tuple, Beats] = {}
    for key, pairs in group_triggers.items():
        fresh = [own for trigger, own in pairs
                 if quantize_beats(trigger) == quantize_beats(own)]
        group_trigger[key] = fresh[0] if fresh \
            else min(trigger for trigger, _ in pairs)

    # -- assemble all animated elements ------------------------------------
    by_qbeat: dict[int, dict] = {}
    beats_by_element: dict[ElementId, Beats] = {}
    for el in layout.elements:
        ident = el.identity
        if not is_animated(ident):
            continue
        eid = ident.element_id
        own = ident.onset
        assert own is not None           # guaranteed by is_animated
        if eid in note_trigger:
            trigger = note_trigger[eid]
        else:
            key = (ident.part, ident.staff, ident.voice, quantize_beats(own))
            trigger = group_trigger.get(key, own)
        beats_by_element[eid] = trigger
        bucket = by_qbeat.setdefault(quantize_beats(trigger), {
            "beats": trigger, "ids": [], "fresh_pages": set(), "pages": set()})
        bucket["ids"].append(eid)
        bucket["pages"].add(el.page)
        if quantize_beats(trigger) == quantize_beats(own):
            bucket["fresh_pages"].add(el.page)

    triggers = tuple(
        Trigger(beats=b["beats"],
                page=min(b["fresh_pages"] or b["pages"]),
                element_ids=tuple(b["ids"]))
        for _, b in sorted(by_qbeat.items()))
    return TriggerSchedule(
        triggers=triggers,
        beat_values=tuple(t.beats for t in triggers),
        beats_by_element=beats_by_element,
    )
