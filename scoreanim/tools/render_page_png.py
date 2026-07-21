"""Render every page of a score through the REAL Qt scene pipeline
(render/scene.py) to PNG files — the Phase 2 fidelity artifact, for
side-by-side comparison with the Phase 0/1 SVG renders.

Run: python -m scoreanim.tools.render_page_png <score.musicxml> <outdir>
     [--tint PART]                # e.g. --tint P3, demo part recoloring
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.engraving.types import EngravingParams  # noqa: E402
from scoreanim.core.engraving.verovio import (  # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import PartId  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402

TINT = QColor("#cc2222")
PIXELS_WIDE = 1600


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score", type=Path)
    parser.add_argument("outdir", type=Path)
    parser.add_argument("--tint", metavar="PART", default=None,
                        help="part id to recolor, e.g. P3")
    ns = parser.parse_args()
    score, outdir, tint = ns.score, ns.outdir, ns.tint
    outdir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])  # noqa: F841
    from scoreanim.render.fonts import register_bravura
    print("bravura font:", "ok" if register_bravura() else "unavailable (tofu)")

    t0 = time.perf_counter()
    engraved = VerovioEngravingProvider().load_detailed(score,
                                                        EngravingParams())
    t1 = time.perf_counter()
    scenes = ScoreScenes(engraved.layout,
                         default_stage_config(engraved.prepared,
                                              page_content_top(engraved.layout)))
    t2 = time.perf_counter()
    print(f"engrave+decompose {t1 - t0:.2f}s, scene build {t2 - t1:.2f}s")

    if tint:
        scenes.set_part_color(PartId(tint), TINT)
        print(f"tinted part {tint}")

    for page in range(1, scenes.page_count + 1):
        scene = scenes.scene_for_page(page)
        rect = scene.sceneRect()
        image = QImage(PIXELS_WIDE,
                       round(PIXELS_WIDE * rect.height() / rect.width()),
                       QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        scene.render(painter)
        painter.end()
        out = outdir / f"page-{page}.png"
        image.save(str(out))
        n = sum(1 for i in scene.items() if i.parentItem() is None) - 1
        print(f"wrote {out} ({n} elements)")


if __name__ == "__main__":
    main()
