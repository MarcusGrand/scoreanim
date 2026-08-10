"""Tie chains: every held note as one chain of noteheads.

A held note is re-notated at each barline, so the page carries two or
three noteheads and the tie ink between them for a single sounding
thing. This module finds those chains from the joined `ScoreNote.tie`
words, matched by pitch inside one (part, staff, voice) — the same way
MusicXML means them, so a chord holding one note while the others move
ties only that one.

Split out of glow_scope.py (2026-08-10): the glow was the first
consumer ("a tied note is one note", 2026-08-06), and the tied-as-one
render option is the second — same chains, read by the schedule and
the duration resolver. The output is two plain maps keyed by our own
`ElementId`: `leader` (this continuation head belongs to that chain's
first head) and `span` (that first head's note lasts this many beats
once the chain is counted; present only where the chain is genuinely
longer than the head's own engraved value, so an untied note is absent
and costs nothing).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping

from scoreanim.core.engraving.types import Layout
from scoreanim.core.score.identity import Beats, ElementId
from scoreanim.core.score.model import ScoreNote

# The words MusicXML uses for a note that is held from before, and for
# one that is held on after.
_HELD_FROM = ("stop", "continue")
_HELD_ON = ("start", "continue")


def tie_chains(layout: Layout,
               mapping: Mapping[ElementId, ScoreNote],
               durations: Mapping[ElementId, Beats]
               ) -> tuple[dict[ElementId, ElementId], dict[ElementId, Beats]]:
    """Every held note as one chain: which head leads it, and how many
    beats it holds for.

    ``durations`` is the resolved per-element engraved duration map
    (`core/animation/durations.py`), which is where a chain's last note
    gets its length from — the same numbers the note-value stretch
    already runs on, so a chain's span and a single note's span are
    measured the same way."""
    ident_by_id = {el.identity.element_id: el.identity
                   for el in layout.elements}

    by_voice: dict[tuple, list[tuple[Beats, int, ElementId, ScoreNote]]] = \
        defaultdict(list)
    for eid, note in mapping.items():
        ident = ident_by_id.get(eid)
        # A grace note is never tied, and its layout onset is a
        # fractional qstamp just before the beat — leave it out rather
        # than let it sort in among the notes it decorates.
        if ident is None or ident.onset is None or note.grace:
            continue
        by_voice[(ident.part, ident.staff, ident.voice)].append(
            (ident.onset, note.order, eid, note))

    leader: dict[ElementId, ElementId] = {}
    span: dict[ElementId, Beats] = {}
    for rows in by_voice.values():
        rows.sort(key=lambda row: (row[0], row[1]))
        # pitch → the head leading the chain currently open on it
        open_chain: dict[tuple, ElementId] = {}
        for onset, _order, eid, note in rows:
            pitch = (note.pitch_step, note.pitch_alter, note.octave,
                     note.staff_loc)
            head = open_chain.pop(pitch, None) \
                if note.tie in _HELD_FROM else None
            if head is None:
                head = eid               # this note starts its own chain
            else:
                leader[eid] = head
                # The chain now reaches to the end of THIS note. Written
                # every time it grows, so the last link is what stands.
                end = onset + durations.get(eid, 0.0)
                own_end = (ident_by_id[head].onset or 0.0) \
                    + durations.get(head, 0.0)
                if end > own_end:
                    span[head] = end - (ident_by_id[head].onset or 0.0)
            if note.tie in _HELD_ON:
                open_chain[pitch] = head
    return leader, span
