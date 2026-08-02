"""How hard the systems actually jump on a real score.

The follow-volume half was measured in `spikes/system_pulse.py`, and it
turned up the thing nothing in the code checks: at a big enough amount
two systems on a tight page run into each other. The pop half asks the
same question and two of its own. How many noteheads really land on one
beat — which is what "Notes for full" has to be set against — and how
far does a system move between two frames when a bump fires, since a
bump rises instantly and a page that snaps would read worse than one
that breathes.

No recording is involved: this mode is driven by the schedule alone, so
this walks the fixture's own beats at 30 fps.

    python spikes/onset_pop.py

Writes spikes/out/pop_rest.png and spikes/out/pop_peak.png.

Measured 2026-08-02 on testscore (page 2, five systems, 73.9 units
between the closest two at rest):

    heads on one system on one beat, over 88 bumps:
        1 smallest, 7 median, 17 largest
    at notes_for_full 6, 63 of 88 bumps (72 %) are full strength

      pop   largest   biggest jump  closest gap
     0.02    1.0200         0.0200         73.9
     0.05    1.0500         0.0500         40.1
     0.10    1.1000         0.1000          6.2
     0.20    1.2000         0.2000        -61.4

Two things to look at.

**The default of 6 is low for this fixture.** A six-part score puts a
median of SEVEN heads on a beat, so at 6 most beats already hit the
ceiling and every bump is the same size — the feature stops telling a
chord from a melody note. Something around the median-to-largest range
(say 8-16 here) is where the strengths actually spread out. It is a
knob, so this is a default worth a look rather than a bug.

**The jump IS the amount, every time.** That is the shape working as
asked — a bump rises instantly at the beat, so the whole move happens
between two frames. At 0.02 that is a tick; at 0.10 a tenth of the page
arrives in 33 ms.

The gaps close about half as fast as the follow half's did (compare
`spikes/system_pulse.py`), because only the system that fired grows —
its neighbours are still at rest, so each gap closes from one side. The
top of the range still overlaps. The two amounts ADD, so a document with
both at 0.20 could reach 1.4. Nothing detects a collision; the ceiling
is the only guard.
"""
from __future__ import annotations

import os
import statistics
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QRectF, Qt                             # noqa: E402
from PySide6.QtGui import QImage, QPainter                        # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

from scoreanim.core.animation import (StyleRules,                 # noqa: E402
                                      build_bumps,
                                      build_trigger_schedule, read_pulse)
from scoreanim.core.animation.scale_groups import HEAD_KINDS      # noqa: E402
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

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"
SIDECAR = ROOT / "testdata" / "testscore.tempo"
OUT = ROOT / "spikes" / "out"

FPS = 30
AMOUNTS = (0.02, 0.05, 0.1, 0.2)
NOTES_FOR_FULL = 6
SETTLE = 0.25
PIXELS_WIDE = 1200


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
    counts: dict[int, int] = {}
    for page, _ in scenes.system_groups:
        counts[page] = counts.get(page, 0) + 1
    return max(counts, key=lambda p: counts[p])


def gaps(scenes: ScoreScenes, page: int) -> list[float]:
    bands = sorted((g.sceneBoundingRect()
                    for key, g in scenes.system_groups.items()
                    if key[0] == page),
                   key=lambda r: r.top())
    return [b.top() - a.bottom() for a, b in zip(bands, bands[1:])]


def main() -> None:
    QApplication.instance() or QApplication([])

    engraved = VerovioEngravingProvider().load_detailed(SCORE,
                                                        EngravingParams())
    model = build_score_model(engraved.prepared, engraved.timeline)
    mapping = join_notes(model, engraved.note_records).mapping
    schedule = build_trigger_schedule(engraved.layout, mapping, model.measures)
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    setup = parse_tempo_file(SIDECAR.read_text(), model.measures)
    tempo_map = TempoMap(list(setup.events))

    scenes = ScoreScenes(engraved.layout, stage)
    page = busiest_page(scenes)
    rest_gap = min(gaps(scenes, page))
    render_page(scenes, page, OUT / "pop_rest.png")

    # -- how many heads land on one beat ------------------------------------
    rows = [[(None if scenes.items[eid].identity is None
              else scenes.items[eid].identity.kind, scenes.items[eid].system)
             for eid in trig.element_ids if eid in scenes.items]
            for trig in schedule.triggers]
    # per (beat, system), which is what one strength is measured over
    landing: list[int] = []
    for row in rows:
        counts: dict[int, int] = {}
        for kind, system in row:
            if system is not None and kind in HEAD_KINDS:
                counts[system] = counts.get(system, 0) + 1
        landing.extend(counts.values())
    full = sum(1 for n in landing if n >= NOTES_FOR_FULL)
    print(f"heads on one system on one beat, over {len(landing)} bumps: "
          f"{min(landing)} smallest, {int(statistics.median(landing))} "
          f"median, {max(landing)} largest")
    print(f"at notes_for_full {NOTES_FOR_FULL}, {full} of {len(landing)} "
          f"bumps ({100 * full / len(landing):.0f} %) are full strength\n")

    seconds = [tempo_map.seconds_at(trig.beats) for trig in schedule.triggers]
    end = max(seconds) + SETTLE
    frames = [n / FPS for n in range(int(end * FPS) + 1)]

    print(f"{'pop':>5} {'largest':>9} {'biggest jump':>14} "
          f"{'closest gap':>12}")
    for amount in AMOUNTS:
        stored = {"pop_amount": amount, "notes_for_full": NOTES_FOR_FULL,
                  "settle": SETTLE}
        style = StyleRules(pulse=stored)
        applier = AnimationApplier(scenes.items, schedule, tempo_map, style,
                                   (), scenes.system_groups.values())
        bumps = build_bumps(seconds, rows, read_pulse(stored))

        # the busiest system, walked frame by frame: how big does it get,
        # and how much of that arrives between two frames
        largest = biggest_jump = 0.0
        peak_t = 0.0
        for system in bumps:
            applier.refresh(-1.0)
            sizes = []
            for t in frames:
                applier.apply_at(t)
                sizes.append(scenes.system_groups[(
                    [k for k in scenes.system_groups if k[1] == system][0]
                )].system_scale)
            if max(sizes) > largest:
                largest = max(sizes)
                peak_t = frames[sizes.index(max(sizes))]
            biggest_jump = max(biggest_jump,
                               max((abs(b - a)
                                    for a, b in zip(sizes, sizes[1:])),
                                   default=0.0))

        applier.refresh(peak_t)
        closest = min(gaps(scenes, page))
        print(f"{amount:>5.2f} {largest:>9.4f} {biggest_jump:>14.4f} "
              f"{closest:>12.1f}")
        if amount == 0.05:
            render_page(scenes, page, OUT / "pop_peak.png")
        applier.set_style(StyleRules())          # back to rest for the next

    print(f"\npage {page} carries the most systems; at rest the closest "
          f"two of them come is {rest_gap:.1f} units")
    print(f"wrote {OUT / 'pop_rest.png'} and {OUT / 'pop_peak.png'} "
          f"(the peak one at pop 0.05)")


if __name__ == "__main__":
    main()
