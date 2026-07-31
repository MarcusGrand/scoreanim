"""Where a scale effect pivots — one point per note (rule 6 seam).

A note is drawn as several elements: a notehead, its stem, a flag or a
beam, ledger dashes, an accidental, dots, articulations. A scale that
pivoted each of those on its own centre would pull the note apart —
the head grows in place while the stem grows around its own middle and
loses touch with it. So the whole note scales about ONE point: the
centre of its noteheads. A note then grows and shrinks as one object,
which is what makes a drop look like it is coming toward the viewer and
a pop look like one note moving.

POLICY LIVES HERE, never in the render layer or the evaluator — the
same split `durations.py` makes, through the same key:
``(part, staff, voice, quantized onset)``, the schedule's rule-3 group.
Every attachment already carries its owner note's onset, and a beam's
onset is the FIRST onset of its notes, so a beamed group's beam lands
in the first note's group. That is deliberate and visible: the beam
drops with the first note of its group, and the notes after it drop
with their own stems onto it (Marcus, 2026-07-31).

Ink with no notehead in its group is treated two ways:

- Ink that stands on its own (a slash, a lone accidental) keeps its own
  centre — it IS the object being scaled.
- Note-owned ink (stem, flag, beam, ledger dashes, tremolo strokes)
  gets no pivot at all and does not scale. Scaling a beam about its own
  middle reads as jitter, not as a note arriving.
"""
from __future__ import annotations

from scoreanim.core.animation.schedule import is_animated, quantize_beats
from scoreanim.core.engraving.types import Layout, Point, Rect
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind)

# Kinds a SCALE track may transform. Everything else an effect reaches
# rides opacity alone: scaffold never moves, and neither do dynamics,
# texts or lyrics, which belong to a bar rather than to a note.
SCALABLE_KINDS = frozenset({
    ElementKind.NOTEHEAD, ElementKind.SLASH, ElementKind.ACCIDENTAL,
    ElementKind.ARTICULATION, ElementKind.OTHER, ElementKind.STEM,
    ElementKind.FLAG, ElementKind.BEAM, ElementKind.LEDGER_LINES,
    ElementKind.TREMOLO,
})

# Ink that exists only to serve a note, so it scales only when there is
# a notehead to scale about (a cross-staff beamSpan may find none).
NOTE_OWNED_KINDS = frozenset({
    ElementKind.STEM, ElementKind.FLAG, ElementKind.BEAM,
    ElementKind.LEDGER_LINES, ElementKind.TREMOLO,
})

# The ink a group scales about: the note's own head. A slash is its own
# head — it is what a slash region draws instead of one.
_HEAD_KINDS = frozenset({ElementKind.NOTEHEAD, ElementKind.SLASH})


def _group_key(identity: ElementIdentity) -> tuple:
    """The schedule's rule-3 group: one voice's ink at one onset."""
    return (identity.part, identity.staff, identity.voice,
            quantize_beats(identity.onset))


def scale_pivots(layout: Layout) -> dict[ElementId, Point]:
    """Every element a SCALE track may transform, mapped to the point it
    pivots on. An element absent from the map never scales."""
    heads: dict[tuple, Rect] = {}
    for el in layout.elements:
        ident = el.identity
        if ident.kind not in _HEAD_KINDS or not is_animated(ident):
            continue
        key = _group_key(ident)
        known = heads.get(key)
        heads[key] = el.bbox if known is None else known.union(el.bbox)

    pivots: dict[ElementId, Point] = {}
    for el in layout.elements:
        ident = el.identity
        if ident.kind not in SCALABLE_KINDS or not is_animated(ident):
            continue
        head_box = heads.get(_group_key(ident))
        if head_box is not None:
            pivots[ident.element_id] = head_box.center
        elif ident.kind not in NOTE_OWNED_KINDS:
            pivots[ident.element_id] = el.anchor
    return pivots
