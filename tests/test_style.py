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


# --- M4.4: document default effect in the resolution chain ------------------

def test_default_effect_fills_where_element_and_part_are_silent() -> None:
    rules = StyleRules(default_effect="pop")
    assert rules.resolve(_ident()).effect == "pop"
    assert rules.resolve(_ident(part="P2")).effect == "pop"
    assert rules.resolve(_ident(part=None)).effect == "pop"
    # default beats "appear": the resolved name reaches effect_for as-is
    assert effect_for(rules.resolve(_ident()).effect) is PRESETS["pop"]


def test_part_rule_beats_the_document_default() -> None:
    rules = StyleRules(default_effect="pop",
                       parts={PartId("P1"): ElementStyle(effect="appear")})
    assert rules.resolve(_ident()).effect == "appear"
    assert rules.resolve(_ident(part="P2")).effect == "pop"
    # a part rule carrying only COLOR stays silent on effect → default
    rules = StyleRules(default_effect="pop",
                       parts={PartId("P1"): ElementStyle(color="#cc2222")})
    assert rules.resolve(_ident()) == ElementStyle(color="#cc2222",
                                                   effect="pop")


def test_element_override_beats_default_and_part() -> None:
    rules = StyleRules(
        default_effect="pop",
        parts={PartId("P1"): ElementStyle(effect="pop")},
        elements={ElementId("P1:m1:s1:v1:note:0"):
                  ElementStyle(effect="appear")})
    assert rules.resolve(_ident()).effect == "appear"


def test_none_default_preserves_todays_behavior() -> None:
    assert StyleRules().resolve(_ident()).effect is None
    assert StyleRules(default_effect=None).resolve(_ident()) == \
        StyleRules().resolve(_ident())
    # None still resolves to "appear" downstream (fail-soft unchanged)
    assert effect_for(None) is PRESETS[DEFAULT_EFFECT]


def test_color_scope_untouched_by_default_effect() -> None:
    """TINTED_KINDS is a separate policy set: the document default
    effect never introduces a color — clefs still pop black."""
    from scoreanim.core.animation import takes_part_color
    rules = StyleRules(default_effect="pop")
    clef = ElementIdentity(ElementId("P1:m1:s1:v0:clef:0"),
                           ElementKind.CLEF, PartId("P1"), "Part",
                           1, None, 0.0)
    assert rules.resolve(clef).effect == "pop"
    assert rules.resolve(clef).color is None
    assert not takes_part_color(clef)
