"""The glow on real scene items, offscreen: a halo lit only inside its
window, the styling reaching the items once rather than every frame,
sprites cached by shape and never rebuilt while the clock runs, and a
stale halo put out when the effect changes away.

The envelopes themselves are core, and live in tests/test_glow.py.
"""
from __future__ import annotations

import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QBrush, QColor, QImage, QPainter,  # noqa: E402
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QApplication, QGraphicsPathItem,  # noqa: E402
                               QGraphicsRectItem, QGraphicsScene)

from scoreanim.core.animation import (GLOW_COLOR, GLOW_RADIUS,  # noqa: E402
                                      ElementStyle, StyleRules,
                                      build_trigger_schedule)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import ElementKind, PartId  # noqa: E402
from scoreanim.core.timing import TempoEvent, TempoMap  # noqa: E402
from scoreanim.render import glow_sprite  # noqa: E402
from scoreanim.render.animate import AnimationApplier  # noqa: E402
from scoreanim.render.glow_sprite import (OVERSAMPLE,  # noqa: E402
                                          GlowSlot, push_glow_style)
from scoreanim.render.items import ElementItem  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402

TEMPO = TempoMap([TempoEvent(0.0, 120.0)])
# glow alone, on every element, with a fixed window rather than the
# note-value stretch — so the expectations below are plain arithmetic
GLOW_RULES = StyleRules(default_effect="glow",
                        effect_params={"glow": {"duration": 0.4,
                                                "note_value": False}})


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def schedule(engraved, join_mapping, score_model):
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures)


@pytest.fixture()
def scenes(qapp, engraved) -> ScoreScenes:
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    return ScoreScenes(engraved.layout, stage)


def _a_head(scenes, schedule):
    return next(eid for eid in schedule.beats_by_element
                if scenes.items[eid].identity.kind is ElementKind.NOTEHEAD)


def _parts(scenes, trigger) -> set:
    return {scenes.items[eid].identity.part for eid in trigger.element_ids
            if eid in scenes.items
            and scenes.items[eid].identity.part is not None}


# -- the applier lights the halo, and only inside the window --------------

def test_the_halo_lights_only_inside_the_window(scenes, schedule) -> None:
    applier = AnimationApplier(scenes.items, schedule, TEMPO, GLOW_RULES)
    head = _a_head(scenes, schedule)
    item = scenes.items[head]
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])

    applier.apply_at(trig_s - 0.5)               # before: dark
    assert item.glow_strength == pytest.approx(0.0)
    applier.apply_at(trig_s)                     # at the onset: full
    assert item.glow_strength == pytest.approx(1.0)
    applier.apply_at(trig_s + 0.2)               # halfway out
    assert 0.0 < item.glow_strength < 1.0
    applier.apply_at(trig_s + 0.4)               # the window's end
    assert item.glow_strength == pytest.approx(0.0)
    applier.apply_at(trig_s + 5.0)               # and it stays out
    assert item.glow_strength == pytest.approx(0.0)
    # scrubbing back is stateless, like every other property
    applier.apply_at(trig_s + 0.1)
    lit = item.glow_strength
    applier.refresh(trig_s + 0.1)
    assert item.glow_strength == pytest.approx(lit)


def test_an_element_that_never_glows_builds_no_sprite(scenes,
                                                      schedule) -> None:
    """The lazy build is what makes glow free for everything else: with
    pop as the effect, no element on the page grows a halo sprite and
    nothing is ever rendered or blurred."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO,
                               StyleRules(default_effect="pop"))
    glow_sprite.reset_cache()
    head = _a_head(scenes, schedule)
    applier.refresh(TEMPO.seconds_at(schedule.beats_by_element[head]))
    assert glow_sprite.build_count == 0
    assert all(item._glow._sprite is None for item in scenes.items.values())


def test_only_the_lit_elements_carry_a_sprite(scenes, schedule) -> None:
    """And even under glow, an element outside its window costs nothing
    — it either never grew a sprite or has it at opacity 0, which Qt
    skips painting entirely."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, GLOW_RULES)
    head = _a_head(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    applier.refresh(trig_s)
    lit = scenes.items[head]._glow._sprite
    assert lit is not None and lit.opacity() > 0.0
    # every dark element is either sprite-free or extinguished
    for eid, item in scenes.items.items():
        if item.glow_strength <= 0.0:
            sprite = item._glow._sprite
            assert sprite is None or sprite.opacity() == 0.0, eid


def test_playback_never_rebuilds_after_the_first_pass(scenes,
                                                      schedule) -> None:
    """The whole point of the sprite: once a passage has lit, stop,
    scrub and replay are opacity writes only — the build count stands
    still while the brightness moves."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, GLOW_RULES)
    head = _a_head(scenes, schedule)
    item = scenes.items[head]
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])

    for i in range(30):                   # first pass across the window
        applier.apply_at(trig_s - 0.1 + i * 0.02)
    built = glow_sprite.build_count
    assert built > 0

    applier.apply_at(trig_s - 1.0)        # scrub back before the beat
    applier.refresh(trig_s + 0.1)         # a stop-style full refresh
    opacities = set()
    for i in range(30):                   # and play it again
        applier.apply_at(trig_s - 0.1 + i * 0.02)
        opacities.add(item._glow._sprite.opacity())
    assert glow_sprite.build_count == built
    assert len(opacities) >= 2            # the halo really moved


# -- the styling half reaches the items once ------------------------------

def test_colour_and_radius_reach_the_item_at_set_style_time(scenes,
                                                            schedule) -> None:
    """The whole point of splitting the halo in two: its look is pushed
    when the document changes, and a frame only ever writes the
    strength."""
    calls = {"style": 0, "strength": 0}
    for item in scenes.items.values():
        slot = item._glow
        slot.set_style = _counting(slot.set_style, calls, "style")
        slot.set_strength = _counting(slot.set_strength, calls, "strength")

    applier = AnimationApplier(scenes.items, schedule, TEMPO, GLOW_RULES)
    pushed = calls["style"]
    assert pushed > 0                     # it happened at construction
    head = _a_head(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    for i in range(30):                   # scrub across the window
        applier.apply_at(trig_s + i * 0.02)
    assert calls["style"] == pushed       # not once more, all frame long
    assert calls["strength"] > 0          # while the strength did move


def test_the_document_colour_and_radius_are_what_arrive(qapp) -> None:
    glow_sprite.reset_cache()
    item = _element(0, 0, 20, 10)
    push_glow_style([item], {"glow": {"color": "#00ff00", "radius": 12.0}})
    item.set_glow(1.0)
    sprite = item._glow._sprite
    assert sprite is not None
    # the radius arrived: the pad is two radii a side, at OVERSAMPLE
    # pixels a scene unit
    assert sprite.pixmap().width() == math.ceil((20 + 4 * 12.0) * OVERSAMPLE)
    # and so did the colour
    image = sprite.pixmap().toImage()
    color = image.pixelColor(image.width() // 2, image.height() // 2)
    assert color.green() > 200
    assert color.green() > color.red() and color.green() > color.blue()


def test_an_unreadable_entry_still_gives_a_visible_halo() -> None:
    """read_glow's fail-soft, seen from the render side."""
    slot = GlowSlot(QGraphicsRectItem())
    style = push_glow_style([_Spy(slot)], {"glow": {"color": "banana",
                                                    "radius": "wide"}})
    assert style.color == GLOW_COLOR
    assert style.radius == pytest.approx(GLOW_RADIUS)


def test_restyling_rebuilds_the_sprite_with_the_new_colour(qapp) -> None:
    """A colour or radius edit invalidates the sprite; a LIT halo
    rebuilds on the spot rather than waiting for its next onset."""
    glow_sprite.reset_cache()
    item = _element(0, 0, 20, 10)
    item.set_glow_style(QColor("#ff0000"), 16.0)
    item.set_glow(1.0)
    before = item._glow._sprite.pixmap().cacheKey()

    item.set_glow_style(QColor("#0000ff"), 16.0)
    sprite = item._glow._sprite
    assert sprite is not None and sprite.opacity() == pytest.approx(1.0)
    assert sprite.pixmap().cacheKey() != before
    image = sprite.pixmap().toImage()
    color = image.pixelColor(image.width() // 2, image.height() // 2)
    assert color.blue() > color.red() and color.blue() > color.green()


# -- the sprites are shared and sit behind the ink ------------------------

def test_identical_shapes_share_one_sprite(qapp) -> None:
    """A page of quarter noteheads costs a handful of blurs, not one
    per note: same ink, same radius, same colour is one pixmap."""
    glow_sprite.reset_cache()
    a = _element(0, 0, 20, 10)
    b = _element(300, 120, 20, 10)        # same shape, elsewhere
    c = _element(50, 50, 30, 10)          # a different shape
    for item in (a, b, c):
        item.set_glow_style(QColor("#ffcc66"), 24.0)
        item.set_glow(1.0)
    assert glow_sprite.build_count == 2   # a and b shared, c did not
    assert (a._glow._sprite.pixmap().cacheKey()
            == b._glow._sprite.pixmap().cacheKey())


def test_the_sprite_sits_behind_the_ink_and_follows_it(qapp) -> None:
    glow_sprite.reset_cache()
    scene = QGraphicsScene(0, 0, 200, 200)
    item = _element(90, 90, 20, 20)
    scene.addItem(item)
    item.set_glow_style(QColor("#00ff00"), 20.0)
    item.set_glow(1.0)
    sprite = item._glow._sprite
    assert sprite.parentItem() is item
    assert sprite.zValue() == -1.0        # behind the ink, which is at 0

    image = _render(scene, 200)
    center = image.pixelColor(100, 100)   # the ink paints on top
    assert center.green() < 50 and center.alpha() == 255
    halo = image.pixelColor(85, 100)      # just outside the ink
    assert halo.alpha() > 8 and halo.green() > halo.red()

    # a child, so it moves with the element — nudge, slide, pop and the
    # system pulse all reach it through the parent's transform
    was = sprite.scenePos().x()
    item.set_offset(30.0, 0.0)
    assert sprite.scenePos().x() == pytest.approx(was + 30.0)


# -- the stale-state reset ------------------------------------------------

def test_changing_the_effect_away_puts_the_halo_out(scenes,
                                                    schedule) -> None:
    """The scale and offset precedent: nothing writes GLOW for an
    element whose effects no longer have it, so set_style has to. The
    sprite stays — a stale halo is extinguished by opacity, never
    rebuilt away."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, GLOW_RULES)
    head = _a_head(scenes, schedule)
    item = scenes.items[head]
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    applier.apply_at(trig_s)
    assert item.glow_strength == pytest.approx(1.0)
    assert item._glow._sprite.opacity() == pytest.approx(1.0)

    applier.set_style(StyleRules(default_effect="pop"))
    assert item.glow_strength == pytest.approx(0.0)
    assert item._glow._sprite is not None
    assert item._glow._sprite.opacity() == pytest.approx(0.0)


def test_a_part_losing_glow_leaves_the_rest_lit(scenes, schedule) -> None:
    """A rule change that only touches one part must not put out the
    halos of the parts that still glow."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, GLOW_RULES)
    # the busiest beat, so several parts are lit at once
    trigger = max(schedule.triggers, key=lambda tr: len(_parts(scenes, tr)))
    assert len(_parts(scenes, trigger)) >= 2
    head = next(eid for eid in trigger.element_ids
                if eid in scenes.items
                and scenes.items[eid].identity.kind is ElementKind.NOTEHEAD)
    applier.refresh(TEMPO.seconds_at(trigger.beats))
    part = scenes.items[head].identity.part
    others = [eid for eid in trigger.element_ids
              if eid in scenes.items
              and scenes.items[eid].identity.part not in (part, None)
              and scenes.items[eid].glow_strength > 0.0]
    assert others, "no other part is lit on this beat"

    applier.set_style(StyleRules(
        default_effect="glow",
        effect_params=GLOW_RULES.effect_params,
        parts={PartId(part): ElementStyle(effect="pop")}))
    assert scenes.items[head].glow_strength == pytest.approx(0.0)
    assert all(scenes.items[eid].glow_strength > 0.0 for eid in others)


# -- the radius is in scene units, at any zoom ----------------------------

def test_the_halo_is_the_same_size_at_every_zoom(qapp) -> None:
    """The device-pixel trap, still pinned. The live effect had to
    convert its radius per draw; the sprite is simply an image in scene
    units, so the reach cannot move — and neither may the build count,
    because a zoom must never re-render a halo. The tolerance is one
    device pixel at the smallest zoom (2 scene units at 0.5), where the
    alpha ramp's crossing quantizes."""
    glow_sprite.reset_cache()
    reaches = {scale: _halo_reach(scale, radius=20.0)
               for scale in (0.5, 1.0, 2.0, 4.0)}
    values = list(reaches.values())
    assert all(v is not None for v in values), reaches
    for value in values[1:]:
        assert value == pytest.approx(values[0], abs=1.25), reaches
    # the reach the live effect was calibrated on: about half the
    # radius (it measured 10.0 here) — _BLUR_MATCH keeps that true
    assert 8.0 <= values[0] <= 12.0, reaches
    assert glow_sprite.build_count == 1   # four zooms, one blur
    # non-vacuity: a bigger radius really does reach further
    assert _halo_reach(1.0, radius=40.0) > values[0] + 2.0


def test_a_dark_halo_is_not_drawn_at_all(qapp) -> None:
    """Strength 0 builds nothing, and the ink renders exactly as it
    would with no glow at all — measured against that baseline, not
    against zero, because the ink's own antialiased edge reaches about
    a unit either way."""
    bare = _halo_reach(1.0, radius=None)
    assert bare is not None and bare < 2.0
    assert _halo_reach(1.0, radius=20.0, strength=0.0) == pytest.approx(
        bare, abs=0.25)


# -- helpers --------------------------------------------------------------

class _Spy:
    """Something with a glow slot but no scene, for push_glow_style."""

    def __init__(self, slot: GlowSlot) -> None:
        self._slot = slot

    def set_glow_style(self, color: QColor, radius: float) -> None:
        self._slot.set_style(color, radius)


def _counting(func, calls: dict, key: str):
    def wrapped(*args, **kwargs):
        calls[key] += 1
        return func(*args, **kwargs)
    return wrapped


def _element(x: float, y: float, w: float, h: float) -> ElementItem:
    """A real ElementItem with one filled rect of ink at (x, y)."""
    item = ElementItem()
    path = QPainterPath()
    path.addRect(0.0, 0.0, w, h)
    child = QGraphicsPathItem(path)
    child.setBrush(QBrush(QColor("black")))
    child.setPen(QPen(Qt.PenStyle.NoPen))
    child.setPos(x, y)
    item.add_path_child(child, True, False)
    return item


def _render(scene: QGraphicsScene, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scene.render(painter, QRectF(0, 0, size, size), QRectF(0, 0, 200, 200))
    painter.end()
    return image


def _halo_reach(view_scale: float, radius: float | None,
                strength: float = 1.0) -> float | None:
    """How far anything is painted left of a 20x20 scene-unit block, in
    SCENE units, when the scene is rendered at `view_scale`. A radius of
    None never styles the glow at all — the baseline. None back means
    nothing was painted outside the block."""
    scene = QGraphicsScene(0, 0, 200, 200)
    item = _element(90, 90, 20, 20)
    scene.addItem(item)
    if radius is not None:
        item.set_glow_style(QColor(255, 0, 0), radius)
        item.set_glow(strength)

    size = int(200 * view_scale)
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scene.render(painter, QRectF(0, 0, size, size), QRectF(0, 0, 200, 200))
    painter.end()

    row = int(100 * view_scale)
    for x in range(size):
        if image.pixelColor(x, row).alpha() > 8:
            return 90.0 - x / view_scale
    return None
