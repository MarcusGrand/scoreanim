"""The glow on real scene items, offscreen: a halo lit only inside its
window, the styling reaching the items once rather than every frame, and
a stale halo put out when the effect changes away.

The envelopes themselves are core, and live in tests/test_glow.py.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import (QApplication, QGraphicsItem,  # noqa: E402
                               QGraphicsRectItem, QGraphicsScene)

from scoreanim.core.animation import (GLOW_COLOR, GLOW_RADIUS,  # noqa: E402
                                      ElementStyle, StyleRules,
                                      build_trigger_schedule)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import ElementKind, PartId  # noqa: E402
from scoreanim.core.timing import TempoEvent, TempoMap  # noqa: E402
from scoreanim.render.animate import AnimationApplier  # noqa: E402
from scoreanim.render.glow_effect import (GlowEffect,  # noqa: E402
                                          GlowSlot, push_glow_style)
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


def test_an_element_that_never_glows_grows_no_effect(scenes,
                                                     schedule) -> None:
    """The lazy build is what makes glow free for everything else: with
    pop as the effect, nothing on the page carries a graphics effect."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO,
                               StyleRules(default_effect="pop"))
    head = _a_head(scenes, schedule)
    applier.refresh(TEMPO.seconds_at(schedule.beats_by_element[head]))
    assert all(item.graphicsEffect() is None
               for item in scenes.items.values())


def test_only_the_lit_elements_carry_an_effect(scenes, schedule) -> None:
    """And even under glow, an element outside its window costs nothing
    — it either never grew an effect or has it switched off."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, GLOW_RULES)
    head = _a_head(scenes, schedule)
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    applier.refresh(trig_s)
    assert scenes.items[head].graphicsEffect() is not None
    assert scenes.items[head].graphicsEffect().isEnabled()
    # every dark element is either effect-free or disabled
    for eid, item in scenes.items.items():
        if item.glow_strength <= 0.0:
            effect = item.graphicsEffect()
            assert effect is None or not effect.isEnabled(), eid


# -- the styling half reaches the items once ------------------------------

def test_colour_and_radius_reach_the_item_at_set_style_time(scenes,
                                                            schedule) -> None:
    """The whole point of splitting the effect in two: the halo's look
    is pushed when the document changes, and a frame only ever writes
    the strength."""
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


def test_the_document_colour_and_radius_are_what_arrive() -> None:
    slot = GlowSlot(QGraphicsRectItem())
    push_glow_style([_Spy(slot)], {"glow": {"color": "#00ff00",
                                            "radius": 12.0}})
    slot.set_strength(1.0)                # build the effect to read it
    effect = slot._effect
    assert effect.color().red() == 0 and effect.color().green() == 255
    # the reach follows the strength a little, so compare at full glow
    assert effect.scene_radius == pytest.approx(12.0)


def test_an_unreadable_entry_still_gives_a_visible_halo() -> None:
    """read_glow's fail-soft, seen from the render side."""
    slot = GlowSlot(QGraphicsRectItem())
    style = push_glow_style([_Spy(slot)], {"glow": {"color": "banana",
                                                    "radius": "wide"}})
    assert style.color == GLOW_COLOR
    assert style.radius == pytest.approx(GLOW_RADIUS)


# -- the stale-state reset ------------------------------------------------

def test_changing_the_effect_away_puts_the_halo_out(scenes,
                                                    schedule) -> None:
    """The scale and offset precedent: nothing writes GLOW for an
    element whose effects no longer have it, so set_style has to."""
    applier = AnimationApplier(scenes.items, schedule, TEMPO, GLOW_RULES)
    head = _a_head(scenes, schedule)
    item = scenes.items[head]
    trig_s = TEMPO.seconds_at(schedule.beats_by_element[head])
    applier.apply_at(trig_s)
    assert item.glow_strength == pytest.approx(1.0)
    assert item.graphicsEffect().isEnabled()

    applier.set_style(StyleRules(default_effect="pop"))
    assert item.glow_strength == pytest.approx(0.0)
    assert not item.graphicsEffect().isEnabled()


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
    """The device-pixel trap, pinned. Qt blurs at device resolution, so
    a raw blurRadius shrinks as you zoom in and the stage and an export
    would not agree; GlowEffect converts from the painter's own
    transform instead. Measured in scene units, the reach must not
    move."""
    reaches = {scale: _halo_reach(scale, radius=20.0)
               for scale in (0.5, 1.0, 2.0, 4.0)}
    values = list(reaches.values())
    assert all(v is not None for v in values), reaches
    for value in values[1:]:
        assert value == pytest.approx(values[0], abs=0.75), reaches
    # non-vacuity: a bigger radius really does reach further
    assert _halo_reach(1.0, radius=40.0) > values[0] + 2.0


def test_a_dark_halo_is_not_drawn_at_all(qapp) -> None:
    """Strength 0 disables the effect, and Qt then draws the ink
    exactly as it would with no effect on the item at all — measured
    against that baseline, not against zero, because the ink's own
    antialiased edge reaches about a unit either way."""
    bare = _halo_reach(1.0, radius=None)
    assert bare is not None and bare < 2.0
    assert _halo_reach(1.0, radius=20.0, strength=0.0) == pytest.approx(
        bare, abs=0.25)


# -- helpers --------------------------------------------------------------

class _Parent(QGraphicsItem):
    """A non-painting parent, the shape ElementItem has."""

    def boundingRect(self):  # noqa: N802
        return self.childrenBoundingRect()

    def paint(self, *args) -> None:  # noqa: N802
        pass


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


def _halo_reach(view_scale: float, radius: float | None,
                strength: float = 1.0) -> float | None:
    """How far anything is painted left of a 20x20 scene-unit block, in
    SCENE units, when the scene is rendered at `view_scale`. A radius of
    None puts no effect on the item at all — the baseline. None back
    means nothing was painted outside the block."""
    scene = QGraphicsScene(0, 0, 200, 200)
    parent = _Parent()
    block = QGraphicsRectItem(90, 90, 20, 20)
    block.setBrush(QColor("black"))
    block.setPen(QColor("black"))
    block.setParentItem(parent)
    scene.addItem(parent)
    if radius is not None:
        effect = GlowEffect()
        effect.set_style(QColor(255, 0, 0), radius)
        effect.set_strength(strength)
        parent.setGraphicsEffect(effect)

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
