"""What the glow actually looks like, and what it costs.

RETIRED SUBJECT 2026-08-02: this spike measured the live GlowEffect
drop shadow, which pre-rendered sprites replaced the same day
(render/glow_sprite.py). Kept for the radius calibration it recorded;
the sprite's _BLUR_MATCH factor was chosen to preserve that look.

RE-RUN 2026-08-05, and it needed two repairs first — both of them
things that had quietly stopped being true, and both worth knowing:

- it measured at the trigger, where the DEFAULT glow has been dark
  since the envelope landed (attack 10 %). Every number it printed was
  0. STYLE now asks for the instant-on shape outright.
- it read the element's `sceneBoundingRect` as "the ink". An item's
  bounds include its children and the halo IS a child now, so that rect
  was the padded sprite: the notehead measured 117 units across instead
  of 21, and "how far the light reaches outside the ink" came out as 0
  every time. `_ink_in_scene` reads the ink itself.

Three questions before this goes in front of a person.

1. Is the halo the same size wherever it is drawn? Qt blurs at DEVICE
   resolution, so a radius left raw would shrink as you zoom in and the
   stage and an export would not agree. GlowEffect converts from the
   painter's own transform instead; this measures the halo's reach in
   scene units at several zooms and through the export renderer.
2. Is the default radius the right size — does it read as a halo about
   a notehead high, or as a fog?
3. What does it cost? A lit element renders through an offscreen pixmap,
   so the count of simultaneously-lit items and the frame time matter.

    python spikes/glow.py

Writes spikes/out/glow_rest.png and spikes/out/glow_lit.png (a dark
page, which is what a glow is judged on), plus glow_r18/24/36.png —
the three radii the default was chosen between, to look at.

Measured 2026-08-02 on testscore, on a notehead 21.3 x 18.1 units, at
the default radius of 24.

The halo is the same size wherever it is drawn — which is the whole
point of GlowEffect converting the radius itself:

    device px per unit    reach (units)    peak change (of 255)
                  0.25              8.0                      61
                  0.50              8.0                      64
                  1.00              8.0                      66
                  2.00              8.0                      67

A raw QGraphicsDropShadowEffect would have HALVED the reach at each
step instead.

HISTORICAL, and the reason the radius changed on 2026-08-05. A blur
spreads the same light over more page as it widens, so the halo used to
reach further and dim as it went — Radius was two knobs at once:

    radius    reach (units)    peak change      <- BEFORE normalization
        12              5.0             87
        18              7.0             74
        24              8.0             66
        36              8.0             49
        60             11.0             28

Rendered 18, 24 and 36 on a dark page and looked: 18 read as a bright
rim ON the ink rather than a halo around it, 36 as fog. 24 is the halo,
and it is the default — and it is now also the radius every other one
is normalized against (render/glow_build.py).

Measured again 2026-08-05, with the sprite scaled so its brightest
point matches what the same ink reaches at radius 24:

    radius    reach (units)    peak change      <- AFTER normalization
        12              4.0             47
        18              6.0             58
        24              8.0             62
        36             13.0             62
        60             22.0             62

The radius now buys reach and nothing else, and it buys much more of it
than the old table showed — that column was under-reading, being the
same measurement the second repair above fixed.

Two footnotes on the peak column, since it is not flat all the way
down. Read off the SPRITE itself the peak alpha is flat at every
radius, 163/163/164/164/164 of 255 for 12/18/24/36/60 — that is the
normalization, exactly. What the page shows is lower at 12 and 18 for
two ordinary reasons: a tight halo keeps most of its bright core BEHIND
the ink that covers it, and a sharp peak loses a little to the page's
own sampling (the same effect the zoom table's 0.25 row shows, 52
against 62 for one unchanged sprite). At 4 device px per unit the two
climb to 51 and 60.

The cost is contained. 74 of 1691 items are lit at once at the busiest
moment, and rendering a whole page at 1400 px goes 96 → 112 ms with
those 74 halos on it (2026-08-05; it was 92 → 133 under the live
effect), only while notes are sounding. Normalizing costs a second blur
per distinct sprite at any radius other than 24, which is build-time
only and nothing per frame: one sprite for a notehead takes 1.8 ms at
radius 24, 2.9 at 18 and 18.0 at 60 — and most of that last number is
the bigger image, not the extra blur.
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
                                      ElementStyle, StyleRules,
                                      build_trigger_schedule)
from scoreanim.core.engraving.types import EngravingParams        # noqa: E402
from scoreanim.core.engraving.verovio import (                    # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.project.stage_config import (                 # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import ElementKind             # noqa: E402
from scoreanim.core.score.join import join_notes                  # noqa: E402
from scoreanim.core.score.model import build_score_model          # noqa: E402
from scoreanim.core.timing import TempoMap, parse_tempo_file      # noqa: E402
from scoreanim.render import glow_build                           # noqa: E402
from scoreanim.render.animate import AnimationApplier             # noqa: E402
from scoreanim.render.scene import ScoreScenes, apply_style_colors  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"
SIDECAR = ROOT / "testdata" / "testscore.tempo"
OUT = ROOT / "spikes" / "out"

FPS = 30
PIXELS_WIDE = 1400
# glow alone, on a dark page, with a fixed window so the lit moment is
# easy to find
# The instant-on shape, stated outright: since the envelope landed
# (2026-08-04) the DEFAULT glow spends its first 10 % rising, so a
# measurement taken at the trigger reads a dark note. Lit at once and
# one fall over the whole window, which is what the numbers below assume.
STYLE = StyleRules(default_effect="glow",
                   colors={"mode": DARK},
                   effect_params={"glow": {"duration": 0.4,
                                           "note_value": False,
                                           "attack": 0.0,
                                           "release": 1.0}})


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


def _shot(scenes: ScoreScenes, page: int, box: QRectF,
          scale: float) -> QImage:
    image = QImage(max(1, round(box.width() * scale)),
                   max(1, round(box.height() * scale)),
                   QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    scenes.scene_for_page(page).render(painter, QRectF(image.rect()), box)
    painter.end()
    return image


def halo(scenes: ScoreScenes, applier, page: int, item,
         scale: float, lit, dark, threshold: int = 8) -> tuple[float, int]:
    """One element's halo, measured on the real page: how far it reaches
    outside that element's own ink in SCENE units, and how strongly it
    changes the brightest pixel it touches.

    Measured as the DIFFERENCE between the page with the element
    glowing and the same page with it dark. The page is full of other
    ink, so "the first pixel that is painted" would just find the
    neighbour; the first pixel that MOVED is the halo and nothing else.
    The whole box is scanned rather than one row, because a notehead
    has a stem and an accidental beside it and any single row runs into
    them."""
    ink = _ink_in_scene(item)
    pad = 3 * GLOW_RADIUS
    box = QRectF(ink.left() - pad, ink.top() - pad,
                 ink.width() + 2 * pad, ink.height() + 2 * pad)
    applier.set_style(dark)
    before = _shot(scenes, page, box, scale)
    applier.set_style(lit)
    after = _shot(scenes, page, box, scale)

    reach, peak = 0.0, 0
    for py in range(before.height()):
        for px in range(before.width()):
            moved = _difference(before.pixelColor(px, py),
                                after.pixelColor(px, py))
            if moved <= threshold:
                continue
            peak = max(peak, moved)
            x = box.left() + px / scale
            y = box.top() + py / scale
            out = max(ink.left() - x, x - ink.right(),
                      ink.top() - y, y - ink.bottom())
            reach = max(reach, out)
    return reach, peak


def _ink_in_scene(item) -> QRectF:
    """The element's INK, in scene units. Not `sceneBoundingRect`: an
    item's bounds include its children, and since 2026-08-02 the halo IS
    a child — so that rect is the padded sprite and "how far the light
    reaches outside the ink" would come out as 0 every time."""
    return item.mapRectToScene(glow_build.ink_rect(item))


def _difference(a: QColor, b: QColor) -> int:
    """Colour, not alpha: on a dark page the paper is opaque, so the
    halo changes what a pixel IS, never whether it is painted."""
    return max(abs(a.red() - b.red()), abs(a.green() - b.green()),
               abs(a.blue() - b.blue()), abs(a.alpha() - b.alpha()))


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

    # the beat with the most ink on it, which is where a page full of
    # halos looks busiest and costs most
    busiest = max(schedule.triggers, key=lambda tr: len(tr.element_ids))
    lit_t = tempo_map.seconds_at(busiest.beats)
    page = scenes.items[busiest.element_ids[0]].identity is not None and \
        next(el.page for el in engraved.layout.elements
             if el.identity.element_id == busiest.element_ids[0])

    # -- 1. is the halo the same size wherever it is drawn? ---------------
    applier.refresh(lit_t)
    head_id = next(eid for eid in busiest.element_ids
                   if eid in scenes.items
                   and scenes.items[eid].identity.kind is ElementKind.NOTEHEAD)
    head = scenes.items[head_id]
    # ONE element glowing, so the difference shot below is that one
    # element's halo and nothing else's
    lone = replace(STYLE, default_effect="appear",
                   elements={head_id: ElementStyle(effect="glow")})
    dark = replace(STYLE, default_effect="appear", elements={})
    ink = _ink_in_scene(head)
    print(f"default radius {GLOW_RADIUS:.0f} scene units, "
          f"strength {head.glow_strength:.2f}, on a notehead "
          f"{ink.width():.1f} x {ink.height():.1f} units")
    print(f"{'device px per unit':>19} {'reach (units)':>14} "
          f"{'peak change':>12}")
    for scale in (0.25, 0.5, 1.0, 2.0):
        reach, peak = halo(scenes, applier, page, head, scale, lone, dark)
        print(f"{scale:>19.2f} {reach:>14.1f} {peak:>12}")

    # -- 2. how big should it be? -----------------------------------------
    print(f"\n{'radius':>7} {'reach (units)':>14} {'peak change':>12}")
    for radius in (12, 18, 24, 36, 60):
        lit = replace(lone, effect_params={
            "glow": {**STYLE.effect_params["glow"], "radius": radius}})
        reach, peak = halo(scenes, applier, page, head, 1.0, lit, dark)
        print(f"{radius:>7} {reach:>14.1f} {peak:>12}")
    applier.set_style(STYLE)

    # -- 3. what does it cost? --------------------------------------------
    end = max(tempo_map.seconds_at(tr.beats) for tr in schedule.triggers) + 1.0
    frames = [n / FPS for n in range(int(end * FPS))]
    worst_lit, worst_t = 0, 0.0
    started = time.perf_counter()
    for t in frames:
        applier.apply_at(t)
        lit = sum(1 for item in scenes.items.values()
                  if item.glow_strength > 0.0)
        if lit > worst_lit:
            worst_lit, worst_t = lit, t
    stepping = time.perf_counter() - started
    print(f"\n{len(frames)} frames stepped in {stepping:.2f}s "
          f"({1000 * stepping / len(frames):.2f} ms per frame, evaluation "
          f"only)")
    print(f"most items lit at once: {worst_lit} of {len(scenes.items)}, "
          f"at t={worst_t:.2f}s")

    applier.refresh(worst_t)
    started = time.perf_counter()
    render_page(scenes, page, OUT / "glow_lit.png")
    lit_render = time.perf_counter() - started

    # the three radii the default was chosen between, to look at
    for radius in (18, 24, 36):
        applier.set_style(replace(STYLE, effect_params={
            "glow": {**STYLE.effect_params["glow"], "radius": radius}}))
        applier.refresh(worst_t)
        render_page(scenes, page, OUT / f"glow_r{radius}.png")
    applier.set_style(STYLE)

    applier.refresh(-5.0)
    started = time.perf_counter()
    render_page(scenes, page, OUT / "glow_rest.png")
    rest_render = time.perf_counter() - started
    print(f"rendering page {page} at {PIXELS_WIDE}px wide: "
          f"{1000 * lit_render:.0f} ms lit, {1000 * rest_render:.0f} ms "
          f"at rest")
    print(f"wrote {OUT / 'glow_lit.png'} and {OUT / 'glow_rest.png'}")


if __name__ == "__main__":
    main()
