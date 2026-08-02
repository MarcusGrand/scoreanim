"""Look at what a pop actually does to a chord and to a beamed group.

Renders one crop of the fixture twice through the real Qt pipeline: at
rest, and at the peak of a pop on every note at once. Written for the
2026-08-01 change (each notehead pops about its own centre, beams do not
pop, a stem stops at its beam) — the "before" pictures in
spikes/out/pop_pivot_*.png were taken with the old shared-pivot policy.

Run: python spikes/pop_pivot.py [<measure-ish crop index>]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoreanim.core.animation import (PRESETS, StyleRules,  # noqa: E402
                                      build_trigger_schedule, element_state)
from scoreanim.core.engraving.svg_geom import path_outline  # noqa: E402
from scoreanim.core.engraving.types import EngravingParams  # noqa: E402
from scoreanim.core.engraving.verovio import (  # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.core.score.join import join_notes  # noqa: E402
from scoreanim.core.score.model import build_score_model  # noqa: E402
from scoreanim.render.properties import PROPERTY_APPLIERS  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402

SCORE = ROOT / "testdata" / "testscore.musicxml"
OUT = ROOT / "spikes" / "out"
ZOOM = 3.0


def _crop(scenes, items, name: str, rect: QRectF) -> None:
    image = QImage(int(rect.width() * ZOOM), int(rect.height() * ZOOM),
                   QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    scenes.scenes[0].render(painter, QRectF(image.rect()), rect)
    painter.end()
    OUT.mkdir(parents=True, exist_ok=True)
    image.save(str(OUT / f"pop_pivot_{name}.png"))
    print("wrote", OUT / f"pop_pivot_{name}.png")


def main() -> None:
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from scoreanim.render.fonts import register_bravura
    register_bravura()

    engraved = VerovioEngravingProvider().load_detailed(SCORE,
                                                        EngravingParams())
    model = build_score_model(engraved.prepared, engraved.timeline)
    mapping = join_notes(model, engraved.note_records).mapping
    schedule = build_trigger_schedule(engraved.layout, mapping, model.measures)
    scenes = ScoreScenes(engraved.layout,
                         default_stage_config(
                             engraved.prepared,
                             page_content_top(engraved.layout)))

    # The crop: the widest beam on page 1, plus room above and below —
    # beamed chords are exactly the case this change is about.
    heads = [el for el in engraved.layout.elements
             if el.identity.kind is ElementKind.NOTEHEAD]

    def under(beam) -> int:
        """Notes under a beam, and only TILTED beams count: a tilt is
        what broke the first cut of the stem ceiling."""
        rings = [r for p in beam.glyph.paths
                 for r in path_outline(p.d, p.transform)]
        level = len({round(y, 2) for r in rings for _, y in r}) <= 2
        return 0 if level else sum(
            1 for h in heads
            if beam.bbox.x <= h.bbox.center.x <= beam.bbox.x2
            and abs(h.bbox.center.y - beam.bbox.center.y) < 300)

    beam = max((el for el in engraved.layout.elements
                if el.identity.kind is ElementKind.BEAM and el.page == 1),
               key=under)
    pad = 130.0
    rect = QRectF(beam.bbox.x - pad, beam.bbox.y - 2 * pad,
                  beam.bbox.w + 2 * pad, beam.bbox.h + 4 * pad)
    print("crop on", beam.identity.element_id)

    _crop(scenes, scenes.items, "rest", rect)

    # Every scheduled element at the peak of a pop, all at once.
    pop = PRESETS["pop"]
    StyleRules()                                   # (defaults, for the record)
    for eid in schedule.beats_by_element:
        item = scenes.items.get(eid)
        if item is None:
            continue
        for prop, value in element_state(0.0, pop, 0.0, 1.0).items():
            applier = PROPERTY_APPLIERS.get(prop)
            if applier is not None:
                applier(item, value)
    _crop(scenes, scenes.items, "peak", rect)


if __name__ == "__main__":
    main()
