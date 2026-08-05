"""Where a scale effect pivots — one point per notehead (rule 6 seam).

Each notehead swells about its OWN centre, so it grows in the place it
was engraved. That is the whole point: in a chord, a shared pivot pulls
the outer heads sideways as they grow, which reads as the chord sliding
rather than as each note popping (Marcus, 2026-08-01, revising the
2026-07-31 "whole note turns around one point" ruling).

The ink that hangs off a note follows the head it belongs to:

- a stem pivots on the head at its FOOT — the end away from the beam —
  so its foot stays planted on that head while it grows;
- a flag and tremolo strokes ride the stem, so they take the stem's own
  pivot and move with it;
- an accidental, a dot, an articulation pivot on the nearest head, which
  in a chord is the one they were drawn for.

Two kinds never scale:

- BEAMS. A beam appears with its note, at its engraved size, and never
  swells (Marcus, 2026-08-01). A beam belongs to several notes at once,
  so any pivot for it is a compromise, and a beam that grows drags the
  eye off the notes.
- LEDGER LINES. They are ruled at staff size and they stay that size
  (Marcus, 2026-07-31). They still fade in with the note — opacity
  reaches every animated element; only scale is fussy about which ink it
  may touch.

POLICY LIVES HERE, never in the render layer or the evaluator — the
same split `durations.py` makes, through the same key:
``(part, staff, voice, quantized onset)``, the schedule's rule-3 group.
Every attachment already carries its owner note's onset, so nothing new
is stored and the adapter is untouched.

Ink with no notehead in its group is treated two ways:

- Ink that stands on its own (a slash, a lone accidental) keeps its own
  centre — it IS the object being scaled.
- Note-owned ink (stem, flag, tremolo strokes) gets no pivot at all and
  does not scale. Scaling a stem about its own middle reads as jitter,
  not as a note arriving.

A stem may grow past its beam, which this module does not stop: the
ceiling that stops it is `stem_caps.py`.
"""
from __future__ import annotations

from scoreanim.core.animation.schedule import is_animated, quantize_beats
from scoreanim.core.engraving.types import Layout, Point, RenderedElement
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind)

# Kinds a SCALE track may transform. Everything else an effect reaches
# rides opacity alone: scaffold never moves, and neither do dynamics,
# texts or lyrics, which belong to a bar rather than to a note.
SCALABLE_KINDS = frozenset({
    ElementKind.NOTEHEAD, ElementKind.SLASH, ElementKind.ACCIDENTAL,
    ElementKind.ARTICULATION, ElementKind.OTHER, ElementKind.STEM,
    ElementKind.FLAG, ElementKind.TREMOLO,
})

# Ink that exists only to serve a note, so it scales only when there is
# a notehead to scale about (a cross-staff beam may find none). BEAM is
# here too: it is note-owned, it is simply not scalable any more.
NOTE_OWNED_KINDS = frozenset({
    ElementKind.STEM, ElementKind.FLAG, ElementKind.BEAM,
    ElementKind.TREMOLO,
})

# The ink a note scales about: its own head. A slash is its own head —
# it is what a slash region draws instead of one.
HEAD_KINDS = frozenset({ElementKind.NOTEHEAD, ElementKind.SLASH})

# Ink that rides the stem, so it turns around whatever the stem does.
_STEM_RIDERS = frozenset({ElementKind.FLAG, ElementKind.TREMOLO})


def group_key(identity: ElementIdentity) -> tuple:
    """The schedule's rule-3 group: one voice's ink at one onset."""
    return (identity.part, identity.staff, identity.voice,
            quantize_beats(identity.onset))


def heads_by_group(layout: Layout) -> dict[tuple, list[RenderedElement]]:
    """Every animated notehead, gathered under its group key."""
    heads: dict[tuple, list[RenderedElement]] = {}
    for el in layout.elements:
        ident = el.identity
        if ident.kind in HEAD_KINDS and is_animated(ident):
            heads.setdefault(group_key(ident), []).append(el)
    return heads


def stem_is_up(stem: RenderedElement,
               heads: list[RenderedElement]) -> bool:
    """True when the stem rises above its heads (so its foot is the
    bottom of its box). Read from the drawn geometry — the adapter does
    not record stem direction, and it does not need to."""
    mid = sum(h.bbox.center.y for h in heads) / len(heads)
    return stem.bbox.center.y < mid


def stem_foot(stem: RenderedElement, heads: list[RenderedElement]) -> float:
    """The y of the stem end that sits on a notehead."""
    return stem.bbox.y2 if stem_is_up(stem, heads) else stem.bbox.y


def nearest_head(point: Point,
                 heads: list[RenderedElement]) -> RenderedElement:
    """The head this ink was drawn for: the closest one in its own
    group. Public because the glow makes the same join — an
    accidental, a lyric and a tie all take their halo from the head
    beside them (core/animation/glow_scope.py)."""
    def distance(head: RenderedElement) -> float:
        centre = head.bbox.center
        return (centre.x - point.x) ** 2 + (centre.y - point.y) ** 2
    return min(heads, key=distance)


def _foot_head(stem: RenderedElement,
               heads: list[RenderedElement]) -> RenderedElement:
    """The head a stem stands on: the one nearest its foot."""
    return nearest_head(Point(stem.bbox.center.x, stem_foot(stem, heads)),
                         heads)


def scale_pivots(layout: Layout) -> dict[ElementId, Point]:
    """Every element a SCALE track may transform, mapped to the point it
    pivots on. An element absent from the map never scales."""
    heads = heads_by_group(layout)

    # A group's stem first: its flag and its tremolo strokes copy it, so
    # they travel with the stem end they are drawn on.
    stem_pivot: dict[tuple, Point] = {}
    for el in layout.elements:
        ident = el.identity
        if ident.kind is not ElementKind.STEM or not is_animated(ident):
            continue
        key = group_key(ident)
        group_heads = heads.get(key)
        if group_heads:
            stem_pivot[key] = _foot_head(el, group_heads).bbox.center

    pivots: dict[ElementId, Point] = {}
    for el in layout.elements:
        ident = el.identity
        if ident.kind not in SCALABLE_KINDS or not is_animated(ident):
            continue
        key = group_key(ident)
        group_heads = heads.get(key)

        if ident.kind in HEAD_KINDS:
            pivots[ident.element_id] = el.bbox.center
        elif not group_heads:
            # Nothing to scale about. Ink that stands on its own is the
            # object being scaled, so it keeps its own centre.
            if ident.kind not in NOTE_OWNED_KINDS:
                pivots[ident.element_id] = el.anchor
        elif ident.kind is ElementKind.STEM:
            pivots[ident.element_id] = _foot_head(el, group_heads).bbox.center
        elif ident.kind in _STEM_RIDERS:
            pivots[ident.element_id] = stem_pivot.get(
                key, nearest_head(el.bbox.center, group_heads).bbox.center)
        else:
            pivots[ident.element_id] = nearest_head(
                el.bbox.center, group_heads).bbox.center
    return pivots
