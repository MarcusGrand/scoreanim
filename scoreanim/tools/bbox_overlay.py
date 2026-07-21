"""Debug tool: redraw one page purely from decomposed RenderedElements
(never from Verovio's SVG — if the output matches the original render,
decomposition is lossless) with translucent bbox overlays per element.

Run: python -m scoreanim.tools.bbox_overlay <score.musicxml> <page> <out.svg>
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from scoreanim.core.engraving.types import Affine, EngravingParams, Layout
from scoreanim.core.engraving.verovio import VerovioEngravingProvider

_KIND_COLOR = {
    "NOTEHEAD": "#e6194b", "STEM": "#3cb44b", "BEAM": "#ffe119",
    "SLUR": "#4363d8", "TIE": "#f58231", "ACCIDENTAL": "#911eb4",
    "REST": "#46f0f0", "MREST": "#008080", "DYNAMIC": "#f032e6",
    "TEXT": "#9a6324", "STAFF_LINES": "#bcbcbc", "BARLINE": "#808000",
    "CLEF": "#000075", "KEY_SIG": "#808080", "METER_SIG": "#aaffc3",
    "SLASH": "#e6194b",
}


def _matrix(t: Affine) -> str:
    return f"matrix({t.a} {t.b} {t.c} {t.d} {t.e} {t.f})"


def render_page_svg(layout: Layout, page: int, with_bboxes: bool = True) -> str:
    geo = layout.pages[page - 1]
    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {geo.width} {geo.height}">',
        f'<rect width="{geo.width}" height="{geo.height}" fill="white"/>',
    ]
    elements = [e for e in layout.elements if e.page == page]
    for el in elements:
        for p in el.glyph.paths:
            attrs = [f'd={quoteattr(p.d)}', f'transform="{_matrix(p.transform)}"']
            if p.fill:
                attrs.append(f'fill={quoteattr(p.fill)}')
            if p.stroke:
                attrs.append(f'stroke={quoteattr(p.stroke)}')
            if p.stroke_width is not None:
                attrs.append(f'stroke-width="{p.stroke_width}"')
            out.append(f"<path {' '.join(attrs)}/>")
        for t in el.glyph.texts:
            spans = []
            for r in t.runs:
                attrs = [f'font-size="{r.font_size}px"']
                if r.font_family:
                    attrs.append(f'font-family={quoteattr(r.font_family)}')
                if r.font_style:
                    attrs.append(f'font-style={quoteattr(r.font_style)}')
                if r.font_weight:
                    attrs.append(f'font-weight={quoteattr(r.font_weight)}')
                if r.fill:
                    attrs.append(f'fill={quoteattr(r.fill)}')
                spans.append(f'<tspan {" ".join(attrs)}>'
                             f'{escape(r.content)}</tspan>')
            out.append(
                f'<text x="{t.x}" y="{t.y}" text-anchor="{t.anchor}" '
                f'transform="{_matrix(t.transform)}" '
                f'font-family="Times, serif" xml:space="preserve">'
                f'{"".join(spans)}</text>')
    if with_bboxes:
        out.append('<g class="bbox-overlay">')
        for el in elements:
            color = _KIND_COLOR.get(el.identity.kind.name, "#333333")
            b = el.bbox
            out.append(
                f'<rect x="{b.x}" y="{b.y}" width="{b.w}" height="{b.h}" '
                f'fill="none" stroke="{color}" stroke-width="1.5" '
                f'opacity="0.65"><title>{escape(str(el.identity.element_id))}'
                f'</title></rect>')
        out.append('</g>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    score, page, out_path = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    layout = VerovioEngravingProvider().load(score, EngravingParams())
    out_path.write_text(render_page_svg(layout, page))
    n = sum(1 for e in layout.elements if e.page == page)
    print(f"wrote {out_path} ({n} elements)")


if __name__ == "__main__":
    main()
