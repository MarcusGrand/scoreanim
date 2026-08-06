"""Does Verovio's `scale` above 100 grow the notation on a constant
page? (2026-08-06, for the user score-scale feature.)

Measures, per scale: the page geometry, a notehead's drawn size, the
staff-line span, and how far the systems overflow the page — the
overflow is what the never-clip repagination then has to absorb.

Run: python spikes/score_scale.py
"""
from pathlib import Path

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.engraving.verovio.provider import prepare
from scoreanim.core.engraving.systems import system_bands
from scoreanim.core.score.identity import ElementKind

SCORE = Path(__file__).resolve().parent.parent / "testdata" \
    / "testscore.musicxml"


def measure(scale: int | None) -> None:
    provider = VerovioEngravingProvider()
    prep = prepare(SCORE, (), (), ())
    engraved, _ = provider._engrave_prepared(
        SCORE, prep, EngravingParams(), hide_empty_staves=False,
        strict=True, scale=scale)
    layout = engraved.layout
    geo = layout.pages[0]
    heads = [e for e in layout.elements
             if e.identity.kind is ElementKind.NOTEHEAD and e.page == 1]
    head_w = sum(e.bbox.w for e in heads) / len(heads)
    bands = system_bands(layout)
    bottom = max(b.rect.y + b.rect.h for b in bands)
    n_pages = len(layout.pages)
    overflow = [f"p{b.page} s{b.system}" for b in bands
                if b.rect.y + b.rect.h > geo.height]
    print(f"scale {scale or 'default'}: page {geo.width:.0f}x"
          f"{geo.height:.0f}, pages {n_pages}, mean head w "
          f"{head_w:.1f}, lowest band bottom {bottom:.0f}"
          f"{' OVERFLOWS: ' + ', '.join(overflow) if overflow else ''}")


for s in (None, 70, 100, 130, 160):
    measure(s)
