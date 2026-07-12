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
from scoreanim.core.score.identity import ElementId, ElementIdentity, PartId


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
