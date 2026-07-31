"""Style commands: part/element rules, document default effect, effect
params, reveal mode, floor opacity."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from scoreanim.core.animation.reveal import RevealMode
from scoreanim.core.animation.style import ElementStyle
from scoreanim.core.project.commands.base import (_HEX_COLOR, Command,
                                                  CommandError)
from scoreanim.core.project.document import ProjectDoc
from scoreanim.core.score.identity import ElementId, PartId


def _merge_rule(rules: dict, key, color=..., effect=...) -> dict:
    """Field-wise update of one ElementStyle entry; empty entries are
    dropped so the doc stays sparse. ``...`` = leave the field alone."""
    current = rules.get(key, ElementStyle())
    updated = ElementStyle(
        color=current.color if color is ... else color,
        effect=current.effect if effect is ... else effect,
    )
    if updated.is_empty:
        rules.pop(key, None)
    else:
        rules[key] = updated
    return rules


@dataclass(frozen=True)
class SetPartColor(Command):
    part: PartId
    color: str | None            # "#rrggbb" | None = back to default

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if self.color is not None and not _HEX_COLOR.match(self.color):
            raise CommandError(f"bad color {self.color!r} (want #rrggbb)")
        parts = _merge_rule(dict(doc.style.parts), self.part,
                            color=self.color)
        return replace(doc, style=replace(doc.style, parts=parts))

    def describe(self) -> str:
        return "set part color"


@dataclass(frozen=True)
class SetPartEffect(Command):
    part: PartId
    effect: str | None           # preset name | None = default effect

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if self.effect is not None and not self.effect.strip():
            raise CommandError("empty effect name")
        parts = _merge_rule(dict(doc.style.parts), self.part,
                            effect=self.effect)
        return replace(doc, style=replace(doc.style, parts=parts))

    def describe(self) -> str:
        return "set part effect"


@dataclass(frozen=True)
class SetElementStyle(Command):
    """Per-element override rule — higher priority than the part rule.
    The model, command, and serialization were the Phase 5.3 deliverable;
    the editing UI arrived with M3.3 (BACKLOG 9), once M2 made it
    possible to point at an element.

    `segments` is the `:seg` fan-out (ruling 2026-07-27). A spanner
    broken across systems is several elements sharing one identity but
    for the id, and colouring one system's piece of a hairpin is never
    what anybody meant. They are written together because it is ONE user
    gesture, and rule 8 counts gestures, not documents touched — the
    'fat apply' idiom ApplyScoreSetup and AddTempoOverlay already use,
    there being no generic macro command. Empty for a flat element,
    which is the overwhelmingly common case."""
    element_id: ElementId
    style: ElementStyle | None   # None removes the override
    segments: tuple[ElementId, ...] = ()

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if (self.style is not None and self.style.color is not None
                and not _HEX_COLOR.match(self.style.color)):
            raise CommandError(f"bad color {self.style.color!r} "
                               f"(want #rrggbb)")
        elements = dict(doc.style.elements)
        for eid in (self.element_id, *self.segments):
            if self.style is None or self.style.is_empty:
                elements.pop(eid, None)
            else:
                elements[eid] = self.style
        return replace(doc, style=replace(doc.style, elements=elements))

    def describe(self) -> str:
        return "set element style"


@dataclass(frozen=True)
class SetDefaultEffect(Command):
    """Document-wide default effect (M4, schema v7): the name every
    element resolves to when its element override and part rule are
    both silent. None clears it (back to "appear" via the fail-soft).
    The name is intent — an unknown name is legal here and fails soft
    at resolution (the effect-name precedent)."""
    effect: str | None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if self.effect is not None and not self.effect.strip():
            raise CommandError("empty effect name")
        return replace(doc, style=replace(doc.style,
                                          default_effect=self.effect))

    def describe(self) -> str:
        return "set default effect"


@dataclass(frozen=True)
class SetEffectParam(Command):
    """One knob of one preset (M4, schema v7): sparse
    {preset: {key: value}} — value None deletes the key and an emptied
    param dict drops (the _merge_rule sparse idiom). Validation is
    type/finiteness ONLY; ranges are clamped at consumption
    (presets.build_presets), so a future preset reuses this command
    unchanged."""
    preset: str
    key: str
    value: float | int | bool | None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not self.preset.strip():
            raise CommandError("empty preset name")
        if not self.key.strip():
            raise CommandError("empty parameter key")
        if self.value is not None:
            if not isinstance(self.value, (bool, int, float)):
                raise CommandError(f"bad parameter value {self.value!r}")
            if (not isinstance(self.value, bool)
                    and not math.isfinite(self.value)):
                raise CommandError(f"parameter value {self.value!r} "
                                   f"is not finite")
        params = {name: dict(entry)
                  for name, entry in doc.style.effect_params.items()}
        entry = params.get(self.preset, {})
        if self.value is None:
            entry.pop(self.key, None)
        else:
            entry[self.key] = self.value
        if entry:
            params[self.preset] = entry
        else:
            params.pop(self.preset, None)
        return replace(doc, style=replace(doc.style, effect_params=params))

    def describe(self) -> str:
        return "set effect parameter"


@dataclass(frozen=True)
class ResetEffectSettings(Command):
    """Restore the pre-M4 effect defaults in ONE undo step (Marcus,
    2026-07-25): default_effect cleared (back to "appear" via the
    fail-soft) and the named presets' params dropped entirely — the
    built-in defaults reassert at consumption. Every preset the panel
    has knobs for is cleared together, so one Reset really does reset
    what the panel shows. Other presets' params (possibly from a newer
    build) survive untouched, the raw-round-trip guarantee."""
    presets: tuple[str, ...] = ("pop", "fade")

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        params = {name: dict(entry)
                  for name, entry in doc.style.effect_params.items()
                  if name not in self.presets}
        return replace(doc, style=replace(doc.style, default_effect=None,
                                          effect_params=params))

    def describe(self) -> str:
        return "reset effect settings"


@dataclass(frozen=True)
class SetRevealMode(Command):
    mode: RevealMode

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not isinstance(self.mode, RevealMode):
            raise CommandError(f"bad reveal mode {self.mode!r}")
        return replace(doc, style=replace(doc.style, reveal_mode=self.mode))

    def describe(self) -> str:
        return "set reveal mode"


@dataclass(frozen=True)
class SetFloorOpacity(Command):
    """Ghost-score floor (Phase 7.2). 0 is a value, not an error:
    unrevealed animated ink invisible on the always-visible scaffold."""
    value: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not (isinstance(self.value, (int, float))
                and math.isfinite(self.value)
                and 0.0 <= self.value <= 1.0):
            raise CommandError(f"floor opacity {self.value!r} "
                               f"not in [0, 1]")
        return replace(doc, style=replace(doc.style,
                                          floor_opacity=float(self.value)))

    def describe(self) -> str:
        return "set floor opacity"
