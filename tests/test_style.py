"""StyleRules resolution (Phase 5.3): element override > part rule >
defaults, field-wise; preset names fail soft at resolve time."""
from __future__ import annotations

from scoreanim.core.animation import (DEFAULT_EFFECT, PRESETS, ElementStyle,
                                      StyleRules, effect_for)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)


def _ident(eid: str = "P1:m1:s1:v1:note:0",
           part: str | None = "P1") -> ElementIdentity:
    return ElementIdentity(ElementId(eid), ElementKind.NOTEHEAD,
                           PartId(part) if part else None, "Part", 1, 1, 0.0)


def test_defaults_when_no_rules() -> None:
    assert StyleRules().resolve(_ident()) == ElementStyle()
    assert StyleRules().resolve(None) == ElementStyle()


def test_part_rule_applies_to_its_elements_only() -> None:
    rules = StyleRules(parts={PartId("P1"): ElementStyle(color="#cc2222",
                                                         effect="pop")})
    assert rules.resolve(_ident()) == ElementStyle(color="#cc2222",
                                                   effect="pop")
    assert rules.resolve(_ident(part="P2")) == ElementStyle()
    assert rules.resolve(_ident(part=None)) == ElementStyle()


def test_element_override_wins_fieldwise() -> None:
    """An element color override keeps the part's effect (and vice
    versa) — merge is per field, not per rule."""
    rules = StyleRules(
        parts={PartId("P1"): ElementStyle(color="#cc2222", effect="pop")},
        elements={ElementId("P1:m1:s1:v1:note:0"):
                  ElementStyle(color="#00aa00")},
    )
    assert rules.resolve(_ident()) == ElementStyle(color="#00aa00",
                                                   effect="pop")
    other = _ident("P1:m2:s1:v1:note:0")
    assert rules.resolve(other) == ElementStyle(color="#cc2222",
                                                effect="pop")


def test_effect_names_fail_soft_to_default() -> None:
    default = PRESETS[DEFAULT_EFFECT]
    assert effect_for(None) is default
    assert effect_for("no-such-preset") is default
    assert effect_for(DEFAULT_EFFECT) is default
    # the stored intent is untouched by resolution
    rules = StyleRules(parts={PartId("P1"):
                              ElementStyle(effect="from-the-future")})
    assert rules.resolve(_ident()).effect == "from-the-future"


def test_is_empty() -> None:
    assert ElementStyle().is_empty
    assert not ElementStyle(color="#000000").is_empty
    assert not ElementStyle(effect="appear").is_empty
