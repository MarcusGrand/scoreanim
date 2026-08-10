"""SVG <text> decomposition: one <text> node → one TextPrimitive.

Split out of decompose.py (2026-08-10) so the page walk stays under the
module ceiling. Pure helpers: the accumulator comes in duck-typed (it
needs .svg_class, .texts and .add_bbox), so this module never imports
the walker back.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from scoreanim.core.engraving.types import (Affine, Rect, TextPrimitive,
                                            TextRun)
from scoreanim.core.engraving.verovio.kinds import (_BOLD_TEXT_CLASSES,
                                                    _ITALIC_TEXT_CLASSES,
                                                    _SVG_NS)


def _add_text(acc, el: ET.Element, ctm: Affine, page: int) -> None:
    """One <text> → one TextPrimitive of styled runs. Verovio puts the
    anchor point and text-anchor either on <text> itself (labels,
    tempo) or on a positioned rend tspan inside it (pgHead lines);
    styling (size/family/style/weight/fill) sits on nested tspans and
    inherits downward."""
    # position + anchor: <text> first, else the single positioned tspan
    positioned = [t for t in el.iter(f"{_SVG_NS}tspan") if t.get("x")]
    if el.get("x") is not None or not positioned:
        pos_el = el
    elif len(positioned) == 1:
        pos_el = positioned[0]
    else:
        raise ValueError(f"page {page}: <text> with "
                         f"{len(positioned)} positioned tspans — "
                         f"needs splitting support")
    x = float(pos_el.get("x", "0"))
    y = float(pos_el.get("y", "0"))
    anchor = pos_el.get("text-anchor") or el.get("text-anchor") or "start"
    if anchor not in ("start", "middle", "end"):
        # fail BEFORE the primitive is appended (the bbox lookup below
        # would otherwise die on a bare KeyError mid-accumulation) and
        # with page context — TextPrimitive.anchor is a 3-value contract
        raise ValueError(f"page {page}: <text> with unsupported "
                         f"text-anchor {anchor!r}")

    cls_weight = "bold" if acc.svg_class in _BOLD_TEXT_CLASSES else None
    cls_style = "italic" if acc.svg_class in _ITALIC_TEXT_CLASSES else None
    runs = _text_runs(el, _RunAttrs(font_size=0.0, font_family=None,
                                    font_style=cls_style,
                                    font_weight=cls_weight,
                                    fill=None))
    runs = [r for r in runs if r.content.strip() and r.font_size > 0]
    if not runs:
        return
    prim = TextPrimitive(runs=tuple(runs), x=x, y=y,
                         anchor=anchor, transform=ctm)
    acc.texts.append(prim)
    acc.add_bbox(_text_prim_bbox(prim))


def _text_runs(node: ET.Element, inherited: "_RunAttrs") -> list[TextRun]:
    """Depth-first over tspans, tracking inherited styling; leaf text
    segments become runs. Inter-tspan whitespace (XML pretty-printing
    tails) is not content and is skipped."""
    attrs = inherited.updated(node)
    runs: list[TextRun] = []
    if node.text and node.text.strip():
        runs.append(TextRun(content=node.text,
                            font_size=attrs.font_size,
                            font_family=attrs.font_family,
                            font_style=attrs.font_style,
                            font_weight=attrs.font_weight,
                            fill=attrs.fill))
    for child in node:
        if child.tag == f"{_SVG_NS}tspan":
            runs.extend(_text_runs(child, attrs))
    return runs


def _text_prim_bbox(prim: TextPrimitive) -> Rect:
    """Crude metric estimate for one text primitive: 0.5 em average
    advance, 0.8/0.2 em ascent/descent — a placeholder until real font
    metrics (Phase 2). Recomputable from the primitive alone so the
    reclaim pass (attribution) can rebuild a text-bearing host's bbox
    after removing stolen spanner ink."""
    width = sum(0.5 * r.font_size * len(r.content) for r in prim.runs)
    height = max(r.font_size for r in prim.runs)
    x0 = {"start": prim.x, "middle": prim.x - width / 2,
          "end": prim.x - width}[prim.anchor]
    local = Rect(x0, prim.y - 0.8 * height, width, height)
    return prim.transform.apply_rect(local)


@dataclass(frozen=True)
class _RunAttrs:
    """Styling inherited down the tspan tree."""
    font_size: float
    font_family: str | None
    font_style: str | None
    font_weight: str | None
    fill: str | None

    def updated(self, node: ET.Element) -> "_RunAttrs":
        size = self.font_size
        v = node.get("font-size")
        if v is not None and float(v.removesuffix("px")) > 0:
            size = float(v.removesuffix("px"))
        return _RunAttrs(
            font_size=size,
            font_family=node.get("font-family") or self.font_family,
            font_style=node.get("font-style") or self.font_style,
            font_weight=node.get("font-weight") or self.font_weight,
            fill=node.get("fill") or self.fill,
        )
