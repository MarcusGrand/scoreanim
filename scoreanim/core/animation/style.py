"""StyleRules: musical identity → base visual properties (ARCHITECTURE §3).

Rule-based and sparse: per-part rules plus higher-priority per-element
overrides, merged field-wise (an element color override does not erase
the part's effect assignment). The doc stores effect NAMES — intent, not
envelopes (rule 5); names resolve against the preset registry at
animation time and fail soft to the default (core/animation/presets.py).

This is ONE system: the Phase 2 Parts tint folded into ``parts`` color
rules (legacy ``part_colors`` migrates at load, core/project/serialize).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from scoreanim.core.animation.reveal import RevealMode
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)

# Ink that takes the part color (ruling D, 2026-07-12): what plays,
# tints — MINUS rests, whole-bar rests, and dynamic letters, which
# animate (dim/reveal) but stay black, like clefs, signatures, texts,
# barlines, and staff lines. Deliberately a separate policy set from
# ANIMATED_KINDS/REVEALED_KINDS: the animated set and the tinted set
# diverge.
TINTED_KINDS = frozenset({
    ElementKind.NOTEHEAD, ElementKind.SLASH, ElementKind.STEM,
    ElementKind.FLAG, ElementKind.BEAM, ElementKind.ACCIDENTAL,
    ElementKind.ARTICULATION, ElementKind.LEDGER_LINES,
    ElementKind.SLUR, ElementKind.TIE, ElementKind.HAIRPIN,
})


def takes_part_color(identity: ElementIdentity | None) -> bool:
    """OTHER-with-onset covers augmentation dots (note-owned ink the
    adapter classifies as OTHER but stamps with an onset)."""
    if identity is None:
        return False
    if identity.kind in TINTED_KINDS:
        return True
    return (identity.kind is ElementKind.OTHER
            and identity.onset is not None)


@dataclass(frozen=True)
class ElementStyle:
    """One rule's payload; None fields defer to the next rule down."""
    color: str | None = None     # "#rrggbb"
    effect: str | None = None    # preset name

    @property
    def is_empty(self) -> bool:
        return self.color is None and self.effect is None


@dataclass(frozen=True)
class StyleRules:
    reveal_mode: RevealMode = RevealMode.STEPPED
    parts: Mapping[PartId, ElementStyle] = field(default_factory=dict)
    elements: Mapping[ElementId, ElementStyle] = field(default_factory=dict)

    def resolve(self, identity: ElementIdentity | None) -> ElementStyle:
        """Element override > part rule > defaults, per field."""
        if identity is None:
            return ElementStyle()
        part = self.parts.get(identity.part) if identity.part else None
        elem = self.elements.get(identity.element_id)
        return ElementStyle(
            color=(elem.color if elem is not None and elem.color is not None
                   else part.color if part is not None else None),
            effect=(elem.effect if elem is not None
                    and elem.effect is not None
                    else part.effect if part is not None else None),
        )
