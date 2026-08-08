"""May this element's fire time be overruled by hand?

A trigger override (`ProjectDoc.trigger_overrides`) moves WHEN one
element animates: an absolute beat on the performance axis, applied by
`build_trigger_schedule` after its four rules have run. This module is
the policy for which elements may carry one.

**RETIMEABLE_KINDS is derived, never typed out**: everything that
animates by opacity, minus the reveal anchors.

  anchor kinds (notehead, rest, whole-bar rest, slash, bar repeat)
      their triggers are what the per-(system, part) reveal edge is
      built from (reveal.py builds its anchors off
      `schedule.beats_by_element`, ANCHOR_KINDS only). Moving one
      would drag the clip wavefront with it — a separate piece of
      work, deliberately not this one. Keeping them out is also what
      makes "reveal tracks are unchanged by an override" a property of
      the builder, pinned by test.
  scaffold and clip-revealed spanners (staff lines, barlines, slurs,
  ties, hairpins, ...)
      already outside ANIMATED_KINDS — they have no opacity trigger to
      move.

Everything else — dynamics, texts, chord symbols, lyrics,
articulations, accidentals, stems, flags, beams, clefs, key and meter
signatures, tremolos, ledger lines, OTHER — is retimeable, and a NEW
`ElementKind` is retimeable by default (the denylist habit: it joins
`ANIMATED_KINDS` for free and is not an anchor).

An override on anything else, or on an id the layout does not have, is
inert: ignored by the builder, reported here so the loader can warn
(rule 5's staleness trade — warned at load, never repaired). This
module never prints; core stays pure.
"""
from __future__ import annotations

from typing import Mapping

from scoreanim.core.animation.schedule import (ANCHOR_KINDS, ANIMATED_KINDS,
                                               is_animated)
from scoreanim.core.engraving.types import Layout
from scoreanim.core.score.identity import Beats, ElementId, ElementIdentity

RETIMEABLE_KINDS = frozenset(ANIMATED_KINDS - ANCHOR_KINDS)


def is_retimeable(identity: ElementIdentity) -> bool:
    """The builder's exact predicate: opacity-animated (so it has an
    onset and a trigger) and not a reveal anchor."""
    return is_animated(identity) and identity.kind not in ANCHOR_KINDS


def inert_trigger_overrides(layout: Layout,
                            overrides: Mapping[ElementId, Beats]
                            ) -> tuple[tuple[ElementId, str], ...]:
    """The stored overrides that will do nothing, with a reason each:
    ``"no such element"`` (the id is not in this layout — the score
    changed under it) or ``"cannot be re-timed"`` (the element exists
    but is an anchor, scaffold, or onset-less). Sorted by id so the
    loader's warnings are deterministic."""
    if not overrides:
        return ()
    by_id = {el.identity.element_id: el.identity for el in layout.elements}
    inert = []
    for eid in overrides:
        ident = by_id.get(eid)
        if ident is None:
            inert.append((eid, "no such element"))
        elif not is_retimeable(ident):
            inert.append((eid, "cannot be re-timed"))
    return tuple(sorted(inert))
