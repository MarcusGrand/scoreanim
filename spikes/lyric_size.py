"""Does Verovio's `lyricSize` change only the lyrics? (2026-08-06,
for the lyrics-size option.)

Through the real pipeline (EngravingParams.lyric_size): mean syllable
bbox height, mean notehead width (must not move), page geometry, and
the lowest band bottom — bigger lyrics can push systems past the page,
which never-clip then absorbs.

Run: PYTHONPATH=. python spikes/lyric_size.py
"""
from pathlib import Path

from scoreanim.core.engraving.systems import system_bands
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind

SCORE = Path(__file__).resolve().parent.parent / "testdata" \
    / "complex2.musicxml"


def measure(factor: float) -> None:
    engraved = VerovioEngravingProvider().load_detailed(
        SCORE, EngravingParams(lyric_size=factor), strict=False)
    layout = engraved.layout
    geo = layout.pages[0]

    def mean(kind, dim):
        els = [e for e in layout.elements if e.identity.kind is kind]
        return sum(getattr(e.bbox, dim) for e in els) / len(els)

    bands = system_bands(layout)
    bottom = max(b.rect.y + b.rect.h for b in bands)
    warned = sorted({w.code for w in engraved.warnings})
    print(f"lyric_size {factor}: page {geo.width:.0f}x{geo.height:.0f} "
          f"({len(layout.pages)} pages), lyric h {mean(ElementKind.LYRIC, 'h'):.1f}, "
          f"head w {mean(ElementKind.NOTEHEAD, 'w'):.1f}, "
          f"lowest band {bottom:.0f}, warnings {warned}")


for factor in (0.7, 1.0, 1.3, 1.6):
    measure(factor)
