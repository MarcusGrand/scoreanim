"""The "style" half of a project file: StyleRules ⇄ its JSON shape.

Split out of serialize.py (which owns the document envelope and the
version history). The shape rules live here with the code: sparse maps
round-trip RAW so keys this build does not consume survive a save/load
cycle, and the two legacy folds (v1 part_colors, v11 glow strength)
happen on read, once.
"""
from __future__ import annotations

from typing import Any

from scoreanim.core.animation.glow import fold_strength
from scoreanim.core.animation.reveal import RevealMode
from scoreanim.core.animation.style import ElementStyle, StyleRules
from scoreanim.core.score.identity import ElementId, PartId


def style_out(rules: StyleRules) -> dict[str, Any]:
    """The full "style" value for to_dict."""
    return {
        "reveal_mode": rules.reveal_mode.name.lower(),
        "floor_opacity": rules.floor_opacity,
        "parts": {str(p): _style_out(s)
                  for p, s in sorted(rules.parts.items())},
        "elements": {str(e): _style_out(s)
                     for e, s in sorted(rules.elements.items())},
        # v7: default_effect omitted when None; effect_params
        # round-trips RAW (a preset/key this build doesn't consume
        # is written back verbatim) and is omitted when empty
        **({"default_effect": rules.default_effect}
           if rules.default_effect is not None else {}),
        **({"effect_params": {
                name: dict(entry) for name, entry
                in sorted(rules.effect_params.items())}}
           if rules.effect_params else {}),
        # v11: the volume response, written the same way — raw and
        # omitted when empty
        **({"volume": dict(sorted(rules.volume.items()))}
           if rules.volume else {}),
        # v11: the system pulse, its twin
        **({"pulse": dict(sorted(rules.pulse.items()))}
           if rules.pulse else {}),
        # v11: the page's two colours, the third entry of the same
        # shape — raw, and omitted when nothing is stored, which is
        # what keeps an untouched document byte-identical
        **({"colors": dict(sorted(rules.colors.items()))}
           if rules.colors else {}),
    }


def style_rules_in(style: dict[str, Any]) -> StyleRules:
    parts = {PartId(p): _style_in(s)
             for p, s in style.get("parts", {}).items()}
    # v1 legacy: {"part_colors": {pid: "#rrggbb"}} folds into part color
    # rules (explicit "parts" entries win if both are present)
    for p, c in style.get("part_colors", {}).items():
        parts.setdefault(PartId(p), ElementStyle(color=c))
    params = {str(name): dict(entry) for name, entry
              in style.get("effect_params", {}).items()}
    # v11 legacy: the glow's Strength was a second knob on the axis its
    # envelope already owns, so it folds into the two levels it
    # multiplied and the key goes. Once, here — see
    # core/animation/glow.py for why not at consumption.
    if "glow" in params:
        params["glow"] = fold_strength(params["glow"])
    return StyleRules(
        reveal_mode=_reveal_mode_in(style.get("reveal_mode")),
        # .get, never `or`: a saved floor of 0.0 is falsy and must load
        floor_opacity=style.get("floor_opacity", 0.3),
        parts=parts,
        elements={ElementId(e): _style_in(s)
                  for e, s in style.get("elements", {}).items()},
        # v7 keys; absent in v<=6 files → None / {} (unchanged look)
        default_effect=style.get("default_effect"),
        effect_params=params,
        # v11 keys; absent in v<=10 files → {} → both off, which is the
        # look those files have always had
        volume=dict(style.get("volume", {})),
        pulse=dict(style.get("pulse", {})),
        # absent → {} → white paper and black ink, the look every file
        # written before this existed has always had
        colors=dict(style.get("colors", {})),
    )


def _reveal_mode_in(value: Any) -> RevealMode:
    if value is None:
        return RevealMode.STEPPED
    try:
        return RevealMode[str(value).upper()]
    except KeyError as exc:
        raise ValueError(f"unknown reveal mode {value!r}") from exc


def _style_out(style: ElementStyle) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if style.color is not None:
        out["color"] = style.color
    if style.effect is not None:
        out["effect"] = style.effect
    return out


def _style_in(data: dict[str, Any]) -> ElementStyle:
    return ElementStyle(color=data.get("color"), effect=data.get("effect"))
