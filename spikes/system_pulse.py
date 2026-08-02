"""How much the page actually breathes on a real recording.

Two questions before this goes in front of a person. How big does the
pulse get frame to frame at a given Amount, and how fast does it change
— a page that jitters would be worse than one that does nothing. And
does a breathing system still sit clear of its neighbours?

So this walks testscore.wav at 30 fps, prints the size the page takes
at each of a few Amounts, and writes two PNGs of the busiest page — one
at rest and one at the loudest frame — for a side-by-side look. It also
measures the closest approach between two systems at each Amount, which
is the one thing nothing in the code checks.

    python spikes/system_pulse.py

Writes spikes/out/pulse_rest.png and spikes/out/pulse_peak.png.

Measured 2026-08-02 on testscore (page 2, five systems, 73.9 units
between the closest two at rest):

    amount   smallest  largest   biggest jump   closest gap
      0.02     1.0002   1.0200         0.0095          47.8
      0.05     1.0004   1.0500         0.0237           8.7
      0.10     1.0009   1.1000         0.0475         -56.6
      0.20     1.0017   1.2000         0.0949        -187.1

So the motion is smooth — the biggest frame-to-frame step at 0.05 is
2.4 % of the page, which reads as breathing rather than shaking — but
the top of the range is NOT safe on a tight page: at 0.10 two systems
already run into each other. 0.05 is about where a busy page stops
having room.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEventLoop, QRectF, Qt, QTimer         # noqa: E402
from PySide6.QtGui import QImage, QPainter                        # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

from scoreanim.core.animation import (StyleRules,                 # noqa: E402
                                      build_trigger_schedule,
                                      intensity_at, peak_reference,
                                      pulse_scale, read_pulse)
from scoreanim.core.engraving.types import EngravingParams        # noqa: E402
from scoreanim.core.engraving.verovio import (                    # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.project.stage_config import (                 # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.join import join_notes                  # noqa: E402
from scoreanim.core.score.model import build_score_model          # noqa: E402
from scoreanim.core.timing import TempoMap, parse_tempo_file      # noqa: E402
from scoreanim.render.animate import AnimationApplier             # noqa: E402
from scoreanim.render.scene import ScoreScenes                    # noqa: E402
from scoreanim.ui.peaks_worker import PeakExtractor               # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"
AUDIO = ROOT / "testdata" / "testscore.wav"
SIDECAR = ROOT / "testdata" / "testscore.tempo"
OUT = ROOT / "spikes" / "out"

FPS = 30
AMOUNTS = (0.02, 0.05, 0.1, 0.2)
PIXELS_WIDE = 1200


def decode(app: QApplication):
    """Run the app's own decoder to completion on the event loop."""
    extractor = PeakExtractor()
    loop = QEventLoop()
    extractor.finished.connect(loop.quit)
    extractor.failed.connect(lambda msg: (print("decode failed:", msg),
                                          loop.quit()))
    QTimer.singleShot(0, lambda: extractor.start(AUDIO))
    loop.exec()
    return extractor.cache


def render_page(scenes: ScoreScenes, page: int, path: Path) -> None:
    scene = scenes.scene_for_page(page)
    rect: QRectF = scene.sceneRect()
    height = round(PIXELS_WIDE * rect.height() / rect.width())
    image = QImage(PIXELS_WIDE, height, QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    scene.render(painter, QRectF(image.rect()), rect)
    painter.end()
    image.save(str(path))


def busiest_page(scenes: ScoreScenes) -> int:
    """The page carrying the most systems — where two of them come
    closest, so where an overlap would show first."""
    counts: dict[int, int] = {}
    for page, _ in scenes.system_groups:
        counts[page] = counts.get(page, 0) + 1
    return max(counts, key=lambda p: counts[p])


def gaps(scenes: ScoreScenes, page: int) -> list[float]:
    """The vertical space between one system's ink and the next's, on
    one page, as they are drawn right now."""
    bands = sorted((g.sceneBoundingRect()
                    for key, g in scenes.system_groups.items()
                    if key[0] == page),
                   key=lambda r: r.top())
    return [b.top() - a.bottom() for a, b in zip(bands, bands[1:])]


def main() -> None:
    app = QApplication.instance() or QApplication([])
    peaks = decode(app)
    if peaks is None:
        print("no peaks — is testdata/testscore.wav present?")
        return
    reference = peak_reference(peaks)

    engraved = VerovioEngravingProvider().load_detailed(SCORE,
                                                        EngravingParams())
    model = build_score_model(engraved.prepared, engraved.timeline)
    mapping = join_notes(model, engraved.note_records).mapping
    schedule = build_trigger_schedule(engraved.layout, mapping, model.measures)
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    setup = parse_tempo_file(SIDECAR.read_text(), model.measures)
    tempo_map = TempoMap(list(setup.events))
    offset = setup.offset_seconds

    end = peaks.duration_seconds
    frames = [n / FPS for n in range(int(end * FPS))]

    print(f"recording {end:.1f}s, {len(frames)} frames at {FPS} fps")
    print(f"{'amount':>7} {'smallest':>9} {'largest':>8} "
          f"{'biggest jump':>13} {'closest gap':>12}")

    scenes = ScoreScenes(engraved.layout, stage)
    page = busiest_page(scenes)
    rest_gap = min(gaps(scenes, page))
    render_page(scenes, page, OUT / "pulse_rest.png")

    for amount in AMOUNTS:
        style = StyleRules(pulse={"amount": amount})
        applier = AnimationApplier(scenes.items, schedule, tempo_map, style,
                                   (), scenes.system_groups.values())
        applier.set_audio(peaks, offset)
        pulse = read_pulse(style.pulse)
        sizes = [pulse_scale(intensity_at(peaks, t, reference), pulse)
                 for t in frames]
        jump = max((abs(b - a) for a, b in zip(sizes, sizes[1:])), default=0.0)
        # put the page at its biggest and measure what is left between
        # two systems there
        loudest = frames[sizes.index(max(sizes))]
        applier.refresh(loudest - offset)
        closest = min(gaps(scenes, page))
        print(f"{amount:>7.2f} {min(sizes):>9.4f} {max(sizes):>8.4f} "
              f"{jump:>13.4f} {closest:>12.1f}")
        if amount == 0.05:
            render_page(scenes, page, OUT / "pulse_peak.png")
        applier.set_style(StyleRules())          # back to rest for the next

    print(f"\npage {page} carries the most systems; at rest the closest "
          f"two of them come is {rest_gap:.1f} units")
    print(f"wrote {OUT / 'pulse_rest.png'} and {OUT / 'pulse_peak.png'} "
          f"(the peak one at amount 0.05)")


if __name__ == "__main__":
    main()
