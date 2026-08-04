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

Sprites are cached by shape: identical ink at the same radius, colour
and density shares one pixmap, so a page of quarter noteheads costs a
handful of blurs, not one per note. The cache key normalizes each
child's position against the element's own ink rect, which is also
where the sprite is placed — so sharing is exact by construction. A score that never glows
builds nothing at all.

The sprite is rendered at OVERSAMPLE times the engraved resolution so it
still looks clean zoomed in; a glow is soft by definition, so scaling
the pixmap past that is invisible. It is never re-rendered on zoom. An
export denser than OVERSAMPLE pixels per scene unit would show a
slightly softer halo — accepted for the same reason.

Three deliberate differences from the live effect, all small:
- The dying glow fades by brightness only. The old effect also pulled
  its reach in 30% as it died; a fixed sprite cannot, and the fade
  reads the same.
- A mid-pop element's halo now scales WITH the ink — the sprite is a
  child, so pop and the system pulse reach it for free. The old effect
  held the halo at constant scene size through a pop.
- The reveal clip does not cut the sprite. Moot today: spanners, the
  only clipped ink, never receive triggers and so never glow.

Where a chord's head and stem halos overlap, the patch still burns
brighter — each element carries its own sprite, same as it carried its
own effect.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Iterable, Iterator

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QGraphicsBlurEffect, QGraphicsItem,
                               QGraphicsPathItem, QGraphicsPixmapItem,
                               QGraphicsScene, QGraphicsSimpleTextItem,
                               QStyleOptionGraphicsItem)

from scoreanim.core.animation import GlowStyle, read_glow
from scoreanim.render.reveal_item import RevealPathItem

if TYPE_CHECKING:                       # items.py imports GlowSlot
    from scoreanim.render.items import ElementItem

# Sprite pixels per scene unit. Headroom for zooming in; see the module
# docstring for why it does not need to match the deepest zoom.
OVERSAMPLE = 2.0

# Transparent margin around the ink, in radii — room for the blur to
# spread. The live effect reserved the same 2r (plus one) for Qt's own
# filter margin.
_PAD_RADII = 2.0

# The drop shadow blurred with Qt's exponential blur; the blur effect's
# quality mode is a tighter three-pass box blur that reaches about half
# again as far at the same radius. Measured 2026-08-02 (alpha profiles
# of both at radius 20): scaling the blur-effect radius by 0.6 is the
# closest match, so the document's radius keeps the calibrated look the
# default of 24 was chosen for.
_BLUR_MATCH = 0.6

# One pixmap per distinct (shape, radius, colour, density). Module-level,
# so the live scenes and an export's own scenes share the same builds.
_cache: dict[tuple, QPixmap] = {}
# Path identity memo: id(path) -> (the path, its key). Holding the path
# reference is what pins the id against reuse after a scene dies.
_path_keys: dict[int, tuple[QPainterPath, tuple]] = {}
_last_style: GlowStyle | None = None

# Bumped on every real render+blur. Tests read deltas off it to prove
# the cache shares and playback never rebuilds.
build_count = 0


def reset_cache() -> None:
    """Drop every cached pixmap and zero the build counter."""
    global build_count
    _cache.clear()
    _path_keys.clear()
    build_count = 0


class GlowSpriteItem(QGraphicsPixmapItem):
    """The halo pixmap behind an element's ink.

    Hit-transparent the same way GroupItem is: a blurred halo covers a
    lot of page, and a click on it must fall through to real ink."""

    def shape(self) -> QPainterPath:  # noqa: N802 (Qt naming)
        return QPainterPath()


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

    @property
    def strength(self) -> float:
        return self._strength

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
    rect = _ink_rect(owner)
    if rect is None or rect.isEmpty() or radius <= 0.0:
        return None
    pad = _PAD_RADII * radius
    padded = rect.adjusted(-pad, -pad, pad, pad)
    key = (_shape_key(owner, rect.topLeft()), round(radius, 2), color.rgba(),
           round(passes, 3))
    pixmap = _cache.get(key)
    if pixmap is None:
        global build_count
        build_count += 1
        pixmap = QPixmap.fromImage(
            _thicken(_blur(_silhouette(owner, padded, color),
                           radius * _BLUR_MATCH * OVERSAMPLE), passes))
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


# -- building one sprite ---------------------------------------------------

def _ink_children(owner: QGraphicsItem) -> Iterator[QGraphicsItem]:
    """The children whose ink the halo is the shape of. Skips any
    existing sprite (the halo must not glow itself) and the reveal
    copies — their paint honours the clip, and the full-curve ghost
    under each one already carries the whole geometry."""
    for child in owner.childItems():
        if isinstance(child, (GlowSpriteItem, RevealPathItem)):
            continue
        yield child


def _ink_rect(owner: QGraphicsItem) -> QRectF | None:
    rect: QRectF | None = None
    for child in _ink_children(owner):
        mapped = child.mapRectToParent(child.boundingRect())
        rect = mapped if rect is None else rect.united(mapped)
    return rect


def _path_key(path: QPainterPath) -> tuple:
    entry = _path_keys.get(id(path))
    if entry is not None and entry[0] is path:
        return entry[1]
    key = tuple((path.elementAt(i).type,
                 round(path.elementAt(i).x, 2),
                 round(path.elementAt(i).y, 2))
                for i in range(path.elementCount()))
    _path_keys[id(path)] = (path, key)
    return key


def _shape_key(owner: QGraphicsItem, origin: QPointF) -> tuple:
    """What makes two elements' ink the same shape. Positions are keyed
    relative to the element's own ink rect, so two identical noteheads
    anywhere on the page collide on one pixmap — and because each
    sprite is placed at its own element's ink rect, the shared pixmap
    lands exactly right on both."""
    parts = []
    for child in _ink_children(owner):
        transform, invertible = child.itemTransform(owner)
        if not invertible:
            continue
        base = (round(transform.m11(), 4), round(transform.m12(), 4),
                round(transform.m21(), 4), round(transform.m22(), 4),
                round(transform.dx() - origin.x(), 2),
                round(transform.dy() - origin.y(), 2))
        if isinstance(child, QGraphicsPathItem):
            pen = child.pen()
            parts.append((
                "path", _path_key(child.path()), base,
                round(pen.widthF(), 3)
                if pen.style() != Qt.PenStyle.NoPen else None,
                child.brush().style() != Qt.BrushStyle.NoBrush))
        elif isinstance(child, QGraphicsSimpleTextItem):
            parts.append(("text", child.text(), child.font().key(), base))
        else:                           # nothing else exists today
            bounds = child.boundingRect()
            parts.append(("other", type(child).__name__, base,
                          round(bounds.width(), 2),
                          round(bounds.height(), 2)))
    return tuple(parts)


def _silhouette(owner: QGraphicsItem, padded: QRectF,
                color: QColor) -> QImage:
    """The element's ink painted flat in the glow colour, at OVERSAMPLE
    pixels per scene unit, inside the padded rect. Each child paints
    itself with the brush and pen the scene builder gave it, then one
    SourceIn pass replaces every colour with the glow's — so a tinted
    or selected element builds the same sprite as a black one."""
    image = QImage(max(1, math.ceil(padded.width() * OVERSAMPLE)),
                   max(1, math.ceil(padded.height() * OVERSAMPLE)),
                   QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.scale(OVERSAMPLE, OVERSAMPLE)
    painter.translate(-padded.left(), -padded.top())
    option = QStyleOptionGraphicsItem()
    for child in _ink_children(owner):
        transform, invertible = child.itemTransform(owner)
        if not invertible:
            continue
        painter.save()
        painter.setTransform(transform, combine=True)
        child.paint(painter, option, None)
        painter.restore()
    painter.resetTransform()
    painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(image.rect(), color)
    painter.end()
    return image


def _blur(image: QImage, device_radius: float) -> QImage:
    """Blur the silhouette once, through Qt's own blur effect in a
    throwaway scene. QualityHint picks the three-pass near-Gaussian —
    right for a build-once sprite. The spread stays inside the padding
    the silhouette already carries."""
    scene = QGraphicsScene()
    # Python-constructed and held in a local until render returns (the
    # shiboken teardown gotcha, see render/scene.py's page rects).
    item = QGraphicsPixmapItem(QPixmap.fromImage(image))
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(device_radius)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    out = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    painter = QPainter(out)
    rect = QRectF(0, 0, out.width(), out.height())
    scene.render(painter, rect, rect)
    painter.end()
    return out


def _thicken(image: QImage, passes: float) -> QImage:
    """Lay the same halo down `passes` times over itself, which is what
    makes the light solid instead of soft.

    Ordinary painting, so the alpha at a point goes 1 - (1 - a)ⁿ: it
    climbs fast where the blur is already strong and slowly out in the
    tail, so the halo fills in from the ink outwards and keeps a
    gradient at its edge. The colour never moves — every pass is the
    same colour, so the result is that colour at a higher alpha, not a
    brighter one (adding the passes instead would wash a warm gold out
    towards white).

    A part-pass is that pass drawn at part opacity, so the knob is
    smooth all the way up. One pass is the plain blur and returns it
    untouched — which is what keeps a document that never raises the
    density rendering exactly as it did."""
    if passes <= 1.0:
        return image
    out = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    painter = QPainter(out)
    whole = int(passes)
    for _ in range(whole):
        painter.drawImage(0, 0, image)
    part = passes - whole
    if part > 0.0:
        painter.setOpacity(part)
        painter.drawImage(0, 0, image)
    painter.end()
    return out
