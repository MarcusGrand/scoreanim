"""The outer glow as a pre-rendered sprite: blur once, composite forever.

The halo's SHAPE never changes while it animates — only its brightness.
The live drop-shadow effect this module replaces re-rendered the ink and
re-blurred it on every repaint, at device resolution, so playback lagged
on stop, scrub and zoom. Now a glowing element gets a pixmap child item
behind its ink: the element's ink painted in the glow colour, padded by
the radius, blurred ONCE when the element first lights and laid down
over itself as many times as the density asks for. Per frame the
applier touches only the sprite's opacity — one cheap write, and at 0
Qt skips painting the item entirely.

This module is about whose halo it is and when: the slot on an element,
the cache, and the styling push. How the pixmap is actually drawn is
`render/glow_build.py`.

Sprites are cached by shape: identical ink at the same radius, colour
and density shares one pixmap, so a page of quarter noteheads costs a
handful of blurs, not one per note. The cache key normalizes each
child's position against the element's own ink rect, which is also
where the sprite is placed — so sharing is exact by construction. A
score that never glows builds nothing at all.

Two deliberate differences from the live effect, both small:
- The dying glow fades by brightness only. The old effect also pulled
  its reach in 30% as it died; a fixed sprite cannot, and the fade
  reads the same.
- A mid-pop element's halo now scales WITH the ink — the sprite is a
  child, so pop and the system pulse reach it for free. The old effect
  held the halo at constant scene size through a pop.

The reveal clip DOES cut the sprite, as of 2026-08-06. It stopped being
moot the moment ties began to glow: a tie is clip-revealed, so without
the cut a held note's light would stand a whole bar ahead of the ink the
playhead has actually uncovered. The edge arrives through
`ElementItem.set_reveal_edge`, which pushes it to the halo beside the
ink; it is kept here as well as on the sprite, because the sprite is
built late and rebuilt on a restyle.

Where a chord's head and stem halos overlap, the patch still burns
brighter — each element carries its own sprite, same as it carried its
own effect.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QGraphicsItem

from scoreanim.core.animation import GlowStyle, read_glow
from scoreanim.render.glow_build import (OVERSAMPLE, GlowSpriteItem,
                                         build_sprite, clear_path_keys,
                                         ink_rect, padded_rect, shape_key)

if TYPE_CHECKING:                       # items.py imports GlowSlot
    from scoreanim.render.items import ElementItem

__all__ = ["OVERSAMPLE", "GlowSlot", "GlowSpriteItem", "build_count",
           "push_glow_style", "reset_cache", "sprite_for"]

# One pixmap per distinct (shape, radius, colour, density). Module-level,
# so the live scenes and an export's own scenes share the same builds.
_cache: dict[tuple, QPixmap] = {}
_last_style: GlowStyle | None = None

# Bumped on every real render+blur. Tests read deltas off it to prove
# the cache shares and playback never rebuilds.
build_count = 0


def reset_cache() -> None:
    """Drop every cached pixmap and zero the build counter."""
    global build_count
    _cache.clear()
    clear_path_keys()
    build_count = 0


class GlowSlot:
    """One element's halo: the sprite, and when it exists.

    The sprite is built on the first nonzero strength and never before,
    so ink that never glows costs nothing. Once built it is kept — put
    out by opacity 0, which Qt skips painting entirely — so stop, scrub
    and refresh are opacity writes only, never a rebuild."""

    def __init__(self, owner: QGraphicsItem,
                 color: QColor | None = None) -> None:
        self._owner = owner
        self._color = QColor(color) if color is not None else QColor()
        self._radius = 0.0
        self._passes = 1.0
        self._strength = 0.0
        self._sprite: GlowSpriteItem | None = None
        # The clip-reveal edge, kept here rather than only on the sprite
        # because the sprite is built late and rebuilt on a restyle — a
        # tie whose halo lit mid-reveal must not come back unclipped.
        self._reveal_edge: float | None = None

    @property
    def strength(self) -> float:
        return self._strength

    def set_reveal_edge(self, scene_x: float) -> bool:
        """Cut this halo at the scene x its element's ink is cut at. Only
        clip-revealed ink is ever given one — a tie, which glows."""
        self._reveal_edge = scene_x
        if self._sprite is None:
            return False
        return self._sprite.set_clip_right(scene_x)

    def invalidate_transform_cache(self) -> None:
        """The element moved or a parent scaled, so the sprite's cached
        inverse transform is stale (the RevealPathItem contract)."""
        if self._sprite is not None:
            self._sprite.invalidate_transform_cache()

    def set_style(self, color: QColor, radius: float,
                  passes: float = 1.0) -> None:
        color = QColor(color)
        if (color == self._color and radius == self._radius
                and passes == self._passes):
            return
        self._color = color
        self._radius = radius
        self._passes = passes
        if self._sprite is None:
            return                      # next first light builds fresh
        self._drop_sprite()
        if self._strength > 0.0:        # a LIT halo restyles in place
            self._show(self._strength)

    def set_strength(self, value: float) -> None:
        if value == self._strength:
            return
        self._strength = value
        if value <= 0.0:
            if self._sprite is not None:
                self._sprite.setOpacity(0.0)
            return
        self._show(value)

    def _show(self, value: float) -> None:
        if self._sprite is None:
            built = sprite_for(self._owner, self._color, self._radius,
                               self._passes)
            if built is None:           # no ink to glow, or radius 0
                return
            pixmap, top_left = built
            sprite = GlowSpriteItem(pixmap)
            sprite.setZValue(-1.0)      # behind the ink, which sits at 0
            sprite.setScale(1.0 / OVERSAMPLE)
            sprite.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)
            sprite.setPos(top_left)
            # boundingRect is childrenBoundingRect, so the halo grows
            # it; tell the scene index before that happens.
            self._owner.prepareGeometryChange()
            sprite.setParentItem(self._owner)
            self._sprite = sprite
            if self._reveal_edge is not None:
                # parented at last: only now does it have a scene
                # transform to map the edge through
                sprite.set_clip_right(self._reveal_edge)
        self._sprite.setOpacity(min(1.0, max(0.0, value)))

    def _drop_sprite(self) -> None:
        sprite = self._sprite
        if sprite is None:
            return
        self._sprite = None
        self._owner.prepareGeometryChange()
        scene = sprite.scene()
        sprite.setParentItem(None)
        if scene is not None:           # unparenting leaves it top-level
            scene.removeItem(sprite)


def sprite_for(owner: QGraphicsItem, color: QColor, radius: float,
               passes: float = 1.0) -> tuple[QPixmap, QPointF] | None:
    """The halo pixmap for this element's ink, and where its top-left
    sits in the element's own coordinates. Cached: identical ink at the
    same radius, colour and pass count comes back as the same pixmap."""
    rect = ink_rect(owner)
    if rect is None or rect.isEmpty() or radius <= 0.0:
        return None
    padded = padded_rect(rect, radius)
    key = (shape_key(owner, rect.topLeft()), round(radius, 2), color.rgba(),
           round(passes, 3))
    pixmap = _cache.get(key)
    if pixmap is None:
        global build_count
        build_count += 1
        pixmap = build_sprite(owner, padded, color, radius, passes)
        _cache[key] = pixmap
    return pixmap, padded.topLeft()


def push_glow_style(items: Iterable["ElementItem"],
                    effect_params) -> GlowStyle:
    """Hand every item the halo's colour and radius, once, when the
    document changes. Never per frame: the applier writes only the
    strength while the clock runs.

    Returns what it pushed, which is what makes it testable without a
    scene."""
    global _last_style
    style = read_glow(effect_params.get("glow") if effect_params else None)
    if style != _last_style:
        # Colour and radius are in the cache key, so this is memory
        # hygiene, not correctness: the old style's pixmaps are dead.
        reset_cache()
        _last_style = style
    color = QColor(style.color)
    for item in items:
        item.set_glow_style(color, style.radius, style.passes)
    return style
