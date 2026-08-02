"""The outer glow itself: a Qt graphics effect whose radius is in SCENE
units.

A zero-offset drop shadow IS the Photoshop outer-glow look — Qt draws
the item's own silhouette, blurred and tinted, behind the ink — so the
halo follows whatever shape the ink has for free.

**The radius has to be rescaled, and that is the whole reason this
class exists.** `QGraphicsDropShadowEffect` renders its source at
device resolution and blurs it with the world transform reset, so
`blurRadius` is in DEVICE pixels. Measured 2026-08-02: with the radius
left raw at 20, the halo reached 16.0 / 10.0 / 5.0 / 2.5 scene units at
view scales 0.5 / 1 / 2 / 4 — the glow would shrink as you zoom in, and
the stage and an export would not agree. Converting the radius from the
painter's own world transform inside `draw` held it at exactly 10.0
scene units at all four scales, in one draw call each.

Two more measurements from the same run, both relied on below: the
halo's visible reach is about HALF the blur radius, and a disabled
effect is skipped entirely — zero draw calls, no halo, the ink
unchanged. That last one is what makes an element outside its glow
window genuinely free.

Each ElementItem carries its own halo, so where a chord's head, stem
and beam overlap, their halos add and that patch burns brighter. The
same double-darkening the ghost floor has always had; left alone.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Iterable

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsItem

from scoreanim.core.animation import GlowStyle, read_glow

if TYPE_CHECKING:                       # items.py imports GlowEffect
    from scoreanim.render.items import ElementItem

# How much of the halo's reach the strength moves. At full strength the
# radius is what the document asked for; at a dying glow it pulls in a
# little as well as dimming, which is what makes the light look like it
# is going out rather than merely being turned down.
_REACH_FLOOR = 0.7


class GlowEffect(QGraphicsDropShadowEffect):
    """A halo of `radius` SCENE units around whatever it is set on.

    Zero offset, so the shadow sits exactly under the ink rather than
    beside it. Colour and radius are styling and change only when the
    document does; the strength is what the animation drives, every
    frame, and it is the halo's own opacity."""

    def __init__(self) -> None:
        super().__init__()
        self.setOffset(0.0, 0.0)
        self.scene_radius = 0.0
        self._color = QColor()
        self._radius = 0.0
        self._strength = 0.0
        self._device_radius: float | None = None

    def set_style(self, color: QColor, radius: float) -> None:
        """The halo's colour and how far it reaches, in scene units."""
        self._color = QColor(color)
        self._radius = radius
        self._recompose()

    def set_strength(self, value: float) -> None:
        """How brightly it burns: 0 turns the effect off outright, which
        Qt skips entirely rather than drawing an invisible halo."""
        self._strength = value
        self._recompose()

    def _recompose(self) -> None:
        strength = min(1.0, max(0.0, self._strength))
        if strength <= 0.0:
            self.setEnabled(False)
            return
        color = QColor(self._color)
        color.setAlphaF(strength)
        self.setColor(color)
        self._set_scene_radius(
            self._radius * (_REACH_FLOOR + (1.0 - _REACH_FLOOR) * strength))
        self.setEnabled(True)

    def _set_scene_radius(self, radius: float) -> None:
        if radius == self.scene_radius:
            return
        self.scene_radius = radius
        self._device_radius = None      # re-derived on the next draw
        self.updateBoundingRect()       # the halo just changed size

    def boundingRectFor(self, rect: QRectF) -> QRectF:  # noqa: N802
        """How much room the halo needs around the ink, in the ITEM's
        own coordinates — the room the scene reserves, and outside which
        it clips.

        Qt would work this out from `blurRadius`, which is in DEVICE
        pixels and belongs to whatever zoom happened to draw last: an
        item drawn at one scale and then repainted at another would be
        asking for the wrong margin. The radius in scene units is the
        right unit for a rect in scene units, so use that.

        Twice the radius plus one, which is Qt's own margin for this
        filter. One radius is not enough — measured: at 4 device pixels
        per unit the halo came out at 5.5 scene units where every other
        zoom gave 10.0.

        Rendering a whole page shows no difference either way (measured,
        the same 10.0 at every zoom with Qt's own margin), because a
        full render has no partial repaint region to clip against. This
        is for the live stage, where there is one."""
        pad = 2.0 * self.scene_radius + 1.0
        return rect.adjusted(-pad, -pad, pad, pad)

    def draw(self, painter: QPainter) -> None:  # noqa: N802 (Qt naming)
        """Convert the radius to device pixels for this painter, then
        let Qt draw. The transform's own scale is the conversion; it
        already includes a system group's pulse scale and the item's own
        pop, so a glowing note keeps the same halo however big it is at
        the moment."""
        transform = painter.worldTransform()
        scale = math.hypot(transform.m11(), transform.m12()) or 1.0
        device = self.scene_radius * scale
        if self._device_radius is None or abs(device
                                              - self._device_radius) > 1e-6:
            self._device_radius = device
            self.setBlurRadius(device)
        super().draw(painter)


class GlowSlot:
    """An item's one graphics-effect slot, and what fills it.

    A Qt item holds at most ONE QGraphicsEffect. Glow owns that slot;
    nothing else uses one today, and keeping the whole arrangement in
    one small object is what makes that easy to keep true.

    The effect is built on the first nonzero strength and never before,
    so ink that never glows — and every element outside its glow window
    — carries no effect at all."""

    def __init__(self, owner: QGraphicsItem,
                 color: QColor | None = None) -> None:
        self._owner = owner
        self._color = QColor(color) if color is not None else QColor()
        self._radius = 0.0
        self._strength = 0.0
        self._effect: GlowEffect | None = None

    @property
    def strength(self) -> float:
        return self._strength

    def set_style(self, color: QColor, radius: float) -> None:
        self._color = QColor(color)
        self._radius = radius
        if self._effect is not None:
            self._effect.set_style(self._color, radius)

    def set_strength(self, value: float) -> None:
        if value == self._strength:
            return
        self._strength = value
        if self._effect is None:
            if value <= 0.0:
                return                  # never lit: no effect at all
            self._effect = GlowEffect()
            self._effect.set_style(self._color, self._radius)
            self._owner.setGraphicsEffect(self._effect)
        self._effect.set_strength(value)


def push_glow_style(items: Iterable["ElementItem"],
                    effect_params) -> GlowStyle:
    """Hand every item the halo's colour and radius, once, when the
    document changes. Never per frame: the applier writes only the
    strength while the clock runs.

    Returns what it pushed, which is what makes it testable without a
    scene."""
    style = read_glow(effect_params.get("glow") if effect_params else None)
    color = QColor(style.color)
    for item in items:
        item.set_glow_style(color, style.radius)
    return style
