"""How solid the glow gets, and what the extra passes cost.

The halo was soft and only soft: a blur fades from the ink outwards, so
even at full strength the light around a notehead is thin. Density lays
the same blurred halo down over itself n times, so the alpha at a point
goes 1 - (1 - a)ⁿ. Three questions before it goes in front of a person.

1. What does the knob actually buy — how solid does the light get, and
   does it reach further?
2. Where does the top of the range want to be? Past some pass count
   nothing more happens, because the blur's own reach is the ceiling.
3. What do the extra passes cost? They are build-time only (the sprite
   is cached), so the question is the FIRST pass, not the frame.

    python spikes/glow_density.py

Writes spikes/out/glow_d0.png, _d50.png, _d100.png and _d100_r60.png —
the same busy page, on a dark page, to look at.

Measured 2026-08-02 on testscore, at the default radius of 24, on a
notehead. Alpha of the halo (of 255) at each distance out from that
notehead's ink, and how far out the light is visible at all:

    density   passes    +1u   +4u   +8u   +12u   +16u   reach (u)
         0 %      1.0     37    21     8      1      0         7.5
        25 %      2.4     79    47    19      2      0        10.0
        50 %      5.7    150    98    41      6      0        11.5
        75 %     13.5    225   175    89     13      0        12.0
       100 %     32.0    252   238   162     32      0        12.0

So the knob fills the halo IN rather than spreading it out. At 100 %
the light is a solid block of colour out to 4 units and still two
thirds of full at 8, where the plain blur is down to 8 of 255 — and it
looks like a sticker of colour cut to the note's shape, which is what
was asked for. The reach stops moving at 12 units and cannot go past
that: the blur is the ceiling. So RADIUS is still the knob that says
how far, and the two together are how you get a big solid halo
(_d100_r60.png).

32 passes is the top of the range because past it the change is all in
the tail: 32 → 128 moves the alpha at +1u not at all and at +8u by 77
of 255, on light that is already solid where anyone is looking.

The cost is build-time only. Lighting every element of testscore at
once — every page, 456 distinct sprites after the cache shares — takes
780 ms at 0 % and 993 ms at 100 %, so 32 passes cost half a
millisecond a sprite. A replay builds nothing either way, 3 ms.
Nothing moves per frame; the applier still writes one opacity.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QRectF, Qt                             # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter                # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

from scoreanim.core.animation import (DARK, GLOW_RADIUS,          # noqa: E402
                                      StyleRules,
                                      build_trigger_schedule, read_glow)
from scoreanim.core.engraving.types import EngravingParams        # noqa: E402
from scoreanim.core.engraving.verovio import (                    # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.project.stage_config import (                 # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import ElementKind             # noqa: E402
from scoreanim.core.score.join import join_notes                  # noqa: E402
from scoreanim.core.score.model import build_score_model          # noqa: E402
from scoreanim.core.timing import TempoMap, parse_tempo_file      # noqa: E402
from scoreanim.render import glow_build, glow_sprite               # noqa: E402
from scoreanim.render.animate import AnimationApplier             # noqa: E402
from scoreanim.render.scene import ScoreScenes, apply_style_colors  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"
SIDECAR = ROOT / "testdata" / "testscore.tempo"
OUT = ROOT / "spikes" / "out"

PIXELS_WIDE = 1400
# glow alone, on a dark page, with a fixed window so the lit moment is
# easy to find
STYLE = StyleRules(default_effect="glow",
                   colors={"mode": DARK},
                   effect_params={"glow": {"duration": 0.4,
                                           "note_value": False}})
# Where the halo is read, in scene units out from the ink's edge.
OUT_UNITS = (1.0, 4.0, 8.0, 12.0, 16.0)


def styled(density: float) -> StyleRules:
    return replace(STYLE, effect_params={
        "glow": {**STYLE.effect_params["glow"], "density": density}})


def render_page(scenes: ScoreScenes, page: int, path: Path) -> None:
    scene = scenes.scene_for_page(page)
    rect: QRectF = scene.sceneRect()
    height = round(PIXELS_WIDE * rect.height() / rect.width())
    image = QImage(PIXELS_WIDE, height, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    scene.render(painter, QRectF(image.rect()), rect)
    painter.end()
    image.save(str(path))


def profile(item) -> tuple[list[int], float]:
    """One lit element's halo, read off its own sprite: the alpha at
    each of OUT_UNITS to the LEFT of the ink, and how far out the light
    is still visible at all. Scene units throughout — the sprite is
    built at OVERSAMPLE pixels to one."""
    sprite = item._glow._sprite
    image = sprite.pixmap().toImage()
    ink = glow_build.ink_rect(item)       # the sprite is a child too
    # the sprite is placed at the padded rect's top-left, in the item's
    # own coordinates, so the ink's left edge sits this far into it
    left = (ink.left() - sprite.pos().x()) * glow_build.OVERSAMPLE
    row = image.height() // 2
    alphas = [image.pixelColor(max(0, round(left - u * glow_build.OVERSAMPLE)),
                               row).alpha()
              for u in OUT_UNITS]
    reach = 0.0                             # scanned from the outside in
    for px in range(round(left) + 1):
        if image.pixelColor(px, row).alpha() > 8:
            reach = (left - px) / glow_build.OVERSAMPLE
            break
    return alphas, reach


def main() -> None:
    QApplication.instance() or QApplication([])
    OUT.mkdir(exist_ok=True)

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
    apply_style_colors(scenes, STYLE)
    applier = AnimationApplier(scenes.items, schedule, tempo_map, STYLE, (),
                               scenes.system_groups.values())

    busiest = max(schedule.triggers, key=lambda tr: len(tr.element_ids))
    lit_t = tempo_map.seconds_at(busiest.beats)
    head_id = next(eid for eid in busiest.element_ids
                   if eid in scenes.items
                   and scenes.items[eid].identity.kind is ElementKind.NOTEHEAD)
    head = scenes.items[head_id]
    page = next(el.page for el in engraved.layout.elements
                if el.identity.element_id == head_id)

    # -- 1 and 2. what the knob buys, and where its top wants to be -------
    ink = head.sceneBoundingRect()
    print(f"radius {GLOW_RADIUS:.0f} scene units, on a notehead "
          f"{ink.width():.1f} x {ink.height():.1f} units")
    print(f"{'density':>8} {'passes':>8} "
          + " ".join(f"{'+' + str(int(u)) + 'u':>6}" for u in OUT_UNITS)
          + f" {'reach (u)':>10}")
    for density in (0.0, 0.25, 0.5, 0.75, 1.0):
        applier.set_style(styled(density))
        applier.refresh(lit_t)
        alphas, reach = profile(head)
        print(f"{density * 100:>7.0f}% {read_glow({'density': density}).passes:>8.1f} "
              + " ".join(f"{a:>6}" for a in alphas) + f" {reach:>10.1f}")

    # past the top of the range: does anything still happen?
    print("\npast the range's top, straight through the slot:")
    for passes in (32.0, 64.0, 128.0):
        head.set_glow_style(QColor(read_glow(None).color), GLOW_RADIUS, passes)
        head.set_glow(1.0)
        alphas, reach = profile(head)
        print(f"{passes:>7.0f} passes " + " ".join(f"{a:>6}" for a in alphas)
              + f" {reach:>10.1f}")

    # -- 3. what the extra passes cost ------------------------------------
    print()
    for density in (0.0, 1.0):
        glow_sprite.reset_cache()
        applier.set_style(styled(density))
        started = time.perf_counter()
        applier.refresh(lit_t)
        for item in scenes.items.values():      # light the whole page once
            item.set_glow(1.0)
        first = time.perf_counter() - started
        built = glow_sprite.build_count
        started = time.perf_counter()
        applier.refresh(lit_t)
        again = time.perf_counter() - started
        print(f"density {density * 100:>3.0f}%: first pass {1000 * first:.0f} ms "
              f"over {built} sprites, a replay {1000 * again:.0f} ms and "
              f"{glow_sprite.build_count - built} builds")

    # -- pages to look at --------------------------------------------------
    for density in (0.0, 0.5, 1.0):
        applier.set_style(styled(density))
        applier.refresh(lit_t)
        render_page(scenes, page, OUT / f"glow_d{int(density * 100)}.png")
    # the two knobs together: density says how solid, radius still says
    # how far, so a big solid halo is both of them up
    applier.set_style(replace(styled(1.0), effect_params={
        "glow": {**STYLE.effect_params["glow"], "density": 1.0,
                 "radius": 60.0}}))
    applier.refresh(lit_t)
    render_page(scenes, page, OUT / "glow_d100_r60.png")
    print(f"wrote {OUT / 'glow_d0.png'}, _d50.png, _d100.png and "
          "_d100_r60.png")


if __name__ == "__main__":
    main()
