"""How a halo pixmap is drawn: the ink's silhouette, the blur, and the
density pass.

This half knows nothing about which element is glowing or when. It takes
a graphics item, paints its ink flat in the glow colour, blurs it once
and lays it down as many times as the density asks for. The other half —
whose halo it is, when it is built and how it is cached — is
`render/glow_sprite.py`.

The two also split by what changes: everything here is pure drawing that
depends only on the ink and the style, which is exactly what makes a
sprite shareable between elements. `_shape_key` is the other side of
that coin: what makes two elements' ink the same shape, so they can
share one build.

The sprite is rendered at OVERSAMPLE times the engraved resolution so it
still looks clean zoomed in; a glow is soft by definition, so scaling
the pixmap past that is invisible. It is never re-rendered on zoom. An
export denser than OVERSAMPLE pixels per scene unit would show a
slightly softer halo — accepted for the same reason.
"""
from __future__ import annotations

import math
from typing import Iterator

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QGraphicsBlurEffect, QGraphicsItem,
                               QGraphicsPathItem, QGraphicsPixmapItem,
                               QGraphicsScene, QGraphicsSimpleTextItem,
                               QStyleOptionGraphicsItem)

from scoreanim.render.reveal_item import RevealPathItem

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

# Path identity memo: id(path) -> (the path, its key). Holding the path
# reference is what pins the id against reuse after a scene dies.
_path_keys: dict[int, tuple[QPainterPath, tuple]] = {}


class GlowSpriteItem(QGraphicsPixmapItem):
    """The halo pixmap behind an element's ink.

    Hit-transparent the same way GroupItem is: a blurred halo covers a
    lot of page, and a click on it must fall through to real ink."""

    def shape(self) -> QPainterPath:  # noqa: N802 (Qt naming)
        return QPainterPath()


def clear_path_keys() -> None:
    """Forget the path memo. Called with the sprite cache, which is the
    only thing the keys are for."""
    _path_keys.clear()


def padded_rect(rect: QRectF, radius: float) -> QRectF:
    """The ink's rect with room around it for the blur to spread into."""
    pad = _PAD_RADII * radius
    return rect.adjusted(-pad, -pad, pad, pad)


def build_sprite(owner: QGraphicsItem, padded: QRectF, color: QColor,
                 radius: float, passes: float) -> QPixmap:
    """One halo, drawn: the ink in the glow colour, blurred once, and
    laid down `passes` times over itself."""
    return QPixmap.fromImage(
        _thicken(_blur(_silhouette(owner, padded, color),
                       radius * _BLUR_MATCH * OVERSAMPLE), passes))


def ink_children(owner: QGraphicsItem) -> Iterator[QGraphicsItem]:
    """The children whose ink the halo is the shape of. Skips any
    existing sprite (the halo must not glow itself) and the reveal
    copies — their paint honours the clip, and the full-curve ghost
    under each one already carries the whole geometry."""
    for child in owner.childItems():
        if isinstance(child, (GlowSpriteItem, RevealPathItem)):
            continue
        yield child


def ink_rect(owner: QGraphicsItem) -> QRectF | None:
    rect: QRectF | None = None
    for child in ink_children(owner):
        mapped = child.mapRectToParent(child.boundingRect())
        rect = mapped if rect is None else rect.united(mapped)
    return rect


def shape_key(owner: QGraphicsItem, origin: QPointF) -> tuple:
    """What makes two elements' ink the same shape. Positions are keyed
    relative to the element's own ink rect, so two identical noteheads
    anywhere on the page collide on one pixmap — and because each
    sprite is placed at its own element's ink rect, the shared pixmap
    lands exactly right on both."""
    parts = []
    for child in ink_children(owner):
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
    for child in ink_children(owner):
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
