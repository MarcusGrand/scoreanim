"""Does Verovio's `staffLineWidth` change only the staff lines?
(2026-08-07, for the thickness knob.)

Through the real pipeline (EngravingParams.staff_line_width): rendered
staff-line thickness (antialiased coverage over thin runs), notehead
width, stem thickness, page geometry.

Run: PYTHONPATH=. QT_QPA_PLATFORM=offscreen python spikes/staff_line_width.py
"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.project.stage_config import (default_stage_config,
                                                 page_content_top)
from scoreanim.core.score.identity import ElementKind
from scoreanim.render.scene import ScoreScenes

SCORE = Path(__file__).resolve().parent.parent / "testdata" \
    / "testscore.musicxml"


def staff_line_coverage(layout, stage, page: int = 1, zoom: int = 32,
                        max_run_units: float = 3.0) -> float:
    """Median drawn thickness of a staff line, in page units: render
    thin vertical slices of the first staff and sum antialiased ink
    coverage over each thin dark run (fat runs are beams/stems and are
    skipped)."""
    app = QApplication.instance() or QApplication([])   # noqa: F841
    scene = ScoreScenes(layout, stage).scene_for_page(page)
    staff = next(e for e in layout.elements
                 if e.identity.kind is ElementKind.STAFF_LINES
                 and e.page == page)
    b = staff.bbox
    samples: list[float] = []
    for frac in (0.15, 0.25, 0.45, 0.55, 0.65, 0.85):
        src = QRectF(b.x + b.w * frac, b.y - 5, 2, b.h + 10)
        img = QImage(int(src.width() * zoom), int(src.height() * zoom),
                     QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.white)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(p, QRectF(0, 0, img.width(), img.height()), src)
        p.end()
        x = img.width() // 2
        run, y0 = 0, 0
        for y in range(img.height()):
            if img.pixelColor(x, y).value() < 200:
                if run == 0:
                    y0 = y
                run += 1
            else:
                if 0 < run < max_run_units * zoom:
                    samples.append(sum(
                        (255 - img.pixelColor(x, yy).value()) / 255
                        for yy in range(max(0, y0 - 3),
                                        min(img.height(), y + 3))) / zoom)
                run = 0
    samples.sort()
    return samples[len(samples) // 2]


def measure(factor: float) -> None:
    eng = VerovioEngravingProvider().load_detailed(
        SCORE, EngravingParams(staff_line_width=factor))
    stage = default_stage_config(eng.prepared,
                                 page_content_top(eng.layout))
    layout = eng.layout

    def mean(kind, dim):
        els = [e for e in layout.elements if e.identity.kind is kind]
        return sum(getattr(e.bbox, dim) for e in els) / len(els)

    line = staff_line_coverage(layout, stage)
    print(f"staff_line_width {factor}: line {line:.3f} units, "
          f"head w {mean(ElementKind.NOTEHEAD, 'w'):.2f}, "
          f"stem w {mean(ElementKind.STEM, 'w'):.3f}, "
          f"page {layout.pages[0].width:.0f}x{layout.pages[0].height:.0f} "
          f"({len(layout.pages)} pages)")


for factor in (0.7, 1.0, 1.5, 2.0):
    measure(factor)
