"""Which ink glows, whose halo it is, and how long that halo burns.

The glow is not the denylist every other effect runs on (rule 6). A halo
says "this note is sounding", so it belongs to notes and to nothing else
(Marcus, 2026-08-06). A meter, a key signature, a clef, a dynamic, a
rest, a text, a slur: all dark, however brightly the rest of the page
lights. `GLOWING_KINDS` below is that list, and it is the whole of the
policy — the applier reads it and nothing branches on an effect's name.

Two notes' worth of ink is not two glows, though, and this module is
mostly about that:

- **Attached ink shares its note's halo.** An accidental and a lyric
  glow with the notehead they were drawn for, never on a clock of their
  own — the nearest head in their own voice at their own onset, which is
  the same join `scale_groups.py` makes for a pop's pivot.
- **A tied note is ONE note.** A held note is re-notated at each barline,
  so the page carries two or three noteheads and the tie ink between
  them for a single sounding thing. All of it lights together at the
  chain's start and dies together when the last of it stops (Marcus,
  2026-08-06). The chain's FIRST notehead owns the halo; every other
  head, and every tie between them, follows it.

  That is a glow rule only. How the ink APPEARS is untouched: a
  continuation notehead still fills in as the playhead reaches its own
  barline, and the tie ink still grows left-to-right against the reveal
  edge (schedule.py rule 1, the 2026-07-22 grow-with-playhead ruling —
  reversing it drew a 14-beat held note out to the system's end while
  the playhead was mid-system). So a tied note fills in bar by bar and
  glows all at once, which is what Marcus asked for.

Chains are built from the joined `ScoreNote.tie` words, matched by pitch
inside one (part, staff, voice) — the same way MusicXML means them, so a
chord holding one note while the others move ties only that one.

The output is two plain maps, both keyed by our own `ElementId`:
`owner` (this ink glows exactly as that notehead does) and `span` (that
notehead's halo lasts this many beats, tie chain included). An element
missing from both glows on its own clock, exactly as before.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping

from scoreanim.core.animation.scale_groups import (HEAD_KINDS, group_key,
                                                   nearest_head)
from scoreanim.core.engraving.types import Layout, RenderedElement
from scoreanim.core.score.identity import Beats, ElementId, ElementKind
from scoreanim.core.score.model import ScoreNote

# The only ink that ever glows. A halo marks a sounding note, so this is
# noteheads and the ink that IS a notehead (a slash beat, a bar-repeat
# sign), the accidental in front of one, the syllable under one, and the
# tie that joins two of them. Everything else on the page stays dark:
# rests, dynamics, clefs, key and meter signatures, texts, chord
# symbols, slurs, hairpins, and all the scaffold.
#
# Unlike `STATIC_KINDS` next door this IS an allowlist, on purpose. The
# denylist is right for "does this object animate at all", where a new
# kind should join in for free; it is wrong for the glow, where a new
# kind is dark until somebody decides it is a note.
GLOWING_KINDS = frozenset({
    ElementKind.NOTEHEAD, ElementKind.SLASH, ElementKind.BAR_REPEAT,
    ElementKind.ACCIDENTAL, ElementKind.LYRIC, ElementKind.TIE,
})

# Ink that glows only by sharing a notehead's halo. A slash and a
# bar-repeat sign are heads in their own right, so they are not here.
_ATTACHED_KINDS = frozenset({
    ElementKind.ACCIDENTAL, ElementKind.LYRIC, ElementKind.TIE,
})

# The words MusicXML uses for a note that is held from before, and for
# one that is held on after.
_HELD_FROM = ("stop", "continue")
_HELD_ON = ("start", "continue")


@dataclass(frozen=True)
class GlowScope:
    """Who shares whose halo, and how long a shared halo burns.

    ``owner`` maps a piece of ink to the notehead whose glow it takes —
    a continuation notehead to its chain's first head, an accidental or
    lyric or tie to the head it was drawn for. A notehead that owns its
    own halo is absent.

    ``span`` maps such an owning notehead to how many beats its halo
    lasts once the tie chain is counted. Present only where the chain is
    genuinely longer than the notehead's own engraved value, so an
    untied note is absent and costs nothing."""
    owner: Mapping[ElementId, ElementId] = field(default_factory=dict)
    span: Mapping[ElementId, Beats] = field(default_factory=dict)

    def followers(self) -> Mapping[ElementId, tuple[ElementId, ...]]:
        """The same map read the other way: each owning notehead and the
        ink that glows with it. That is the direction the applier walks
        — one leader lights, and everything sharing its halo follows."""
        out: dict[ElementId, list[ElementId]] = defaultdict(list)
        for eid, owner in self.owner.items():
            out[owner].append(eid)
        return {owner: tuple(ids) for owner, ids in out.items()}


def glow_scope(layout: Layout,
               mapping: Mapping[ElementId, ScoreNote],
               durations: Mapping[ElementId, Beats]) -> GlowScope:
    """Work out both maps in one pass over the layout.

    ``durations`` is the resolved per-element engraved duration map
    (`core/animation/durations.py`), which is where a chain's last note
    gets its length from — the same numbers the note-value stretch
    already runs on, so a chain's span and a single note's span are
    measured the same way."""
    heads_by_key: dict[tuple, list[RenderedElement]] = defaultdict(list)
    for el in layout.elements:
        ident = el.identity
        if ident.kind in HEAD_KINDS and ident.onset is not None:
            heads_by_key[group_key(ident)].append(el)

    leader, span = _tie_chains(layout, mapping, durations)

    owner: dict[ElementId, ElementId] = dict(leader)
    for el in layout.elements:
        ident = el.identity
        if ident.kind not in _ATTACHED_KINDS or ident.onset is None:
            continue
        group = heads_by_key.get(group_key(ident))
        if not group:
            continue                     # no head to share with: its own
        head = nearest_head(el.bbox.center, group).identity.element_id
        # Transitive on purpose: an accidental on a continuation head
        # follows that head's chain leader, not the head itself.
        owner[ident.element_id] = leader.get(head, head)
    return GlowScope(owner=owner, span=span)


def _tie_chains(layout: Layout,
                mapping: Mapping[ElementId, ScoreNote],
                durations: Mapping[ElementId, Beats]
                ) -> tuple[dict[ElementId, ElementId], dict[ElementId, Beats]]:
    """Every held note as one chain: which head leads it, and how many
    beats it holds for."""
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
