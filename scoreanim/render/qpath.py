"""Core geometry → Qt geometry. The only place path data meets Qt; all
parsing happens in core (svg_geom.path_segments) — this is a dumb mapping.

SVG's default fill rule is nonzero winding; QPainterPath defaults to
odd-even. Every path gets WindingFill or glyph counters (half-note heads,
'O's in text-as-path) render inverted.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainterPath, QTransform

from scoreanim.core.engraving.svg_geom import (ClosePath, CubicTo, LineTo,
                                               MoveTo, QuadTo, path_segments)
from scoreanim.core.engraving.types import Affine


def to_qtransform(t: Affine) -> QTransform:
    # QTransform(m11, m12, m21, m22, dx, dy) — same order as SVG/Affine.
    return QTransform(t.a, t.b, t.c, t.d, t.e, t.f)


def to_qpainter_path(d: str) -> QPainterPath:
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    for seg in path_segments(d):
        if isinstance(seg, MoveTo):
            path.moveTo(seg.x, seg.y)
        elif isinstance(seg, LineTo):
            path.lineTo(seg.x, seg.y)
        elif isinstance(seg, CubicTo):
            path.cubicTo(seg.x1, seg.y1, seg.x2, seg.y2, seg.x, seg.y)
        elif isinstance(seg, QuadTo):
            path.quadTo(seg.x1, seg.y1, seg.x, seg.y)
        else:                    # ClosePath
            path.closeSubpath()
    return path
