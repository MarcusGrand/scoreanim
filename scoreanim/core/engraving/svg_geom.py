"""SVG geometry math for the Verovio adapter (plan D3).

Pure functions: transform-attribute parsing (translate/scale/rotate/
matrix), path-data parsing into neutral segments, and exact path
bounding boxes via cubic/quadratic bézier extrema. Verovio DOES rotate —
vertical text carries rotate(-90 …) (complex2, Phase 11) — so rotation
goes into the affine matrix and bboxes are corner-mapped (exact for
90-degree multiples, conservative otherwise).

`path_segments` is the single parser for SVG path data: relative
coordinates, H/V shorthands, and S/T reflections are resolved to absolute
explicit segments, so consumers (path_bbox here, QPainterPath construction
in render/) never deal with path-data syntax.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from scoreanim.core.engraving.types import Affine, Rect

_TRANSFORM_RE = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")
_NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def parse_transform(value: str | None) -> Affine:
    """Parse an SVG transform attribute into one composed Affine."""
    result = Affine()
    if not value:
        return result
    matches = list(_TRANSFORM_RE.finditer(value))
    if not matches and value.strip():
        raise ValueError(f"unparseable transform: {value!r}")
    for m in matches:
        name = m.group(1)
        args = [float(x) for x in _NUMBER_RE.findall(m.group(2))]
        if name == "translate":
            tx = args[0]
            ty = args[1] if len(args) > 1 else 0.0
            step = Affine(e=tx, f=ty)
        elif name == "scale":
            sx = args[0]
            sy = args[1] if len(args) > 1 else sx
            step = Affine(a=sx, d=sy)
        elif name == "rotate" and args:
            # rotate(a) about the origin, or rotate(a, cx, cy) about a
            # point. Verovio emits rotate(-90 cx cy) for vertical text
            # (complex2, Phase 11); the rotation lands in the matrix and
            # apply_rect maps it by corners.
            rad = math.radians(args[0])
            cos, sin = math.cos(rad), math.sin(rad)
            step = Affine(a=cos, b=sin, c=-sin, d=cos)
            if len(args) >= 3:
                cx, cy = args[1], args[2]
                step = Affine(e=cx, f=cy).compose(step).compose(
                    Affine(e=-cx, f=-cy))
        elif name == "matrix" and len(args) == 6:
            step = Affine(*args)
        else:
            raise ValueError(f"unsupported transform {name!r} in {value!r}")
        result = result.compose(step)
    return result


def _quad_extrema(p0: float, p1: float, p2: float) -> list[float]:
    """Interior t values where a quadratic bézier coordinate is extremal."""
    denom = p0 - 2 * p1 + p2
    if denom == 0:
        return []
    t = (p0 - p1) / denom
    return [t] if 0 < t < 1 else []


def _cubic_extrema(p0: float, p1: float, p2: float, p3: float) -> list[float]:
    """Interior t values where a cubic bézier coordinate is extremal."""
    a = 3 * (-p0 + 3 * p1 - 3 * p2 + p3)
    b = 6 * (p0 - 2 * p1 + p2)
    c = 3 * (p1 - p0)
    ts: list[float] = []
    if a == 0:
        if b != 0:
            t = -c / b
            if 0 < t < 1:
                ts.append(t)
        return ts
    disc = b * b - 4 * a * c
    if disc < 0:
        return ts
    sq = math.sqrt(disc)
    for t in ((-b + sq) / (2 * a), (-b - sq) / (2 * a)):
        if 0 < t < 1:
            ts.append(t)
    return ts


def _cubic_at(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    u = 1 - t
    return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3


def _quad_at(p0: float, p1: float, p2: float, t: float) -> float:
    u = 1 - t
    return u * u * p0 + 2 * u * t * p1 + t * t * p2


class _Extent:
    def __init__(self) -> None:
        self.min_x = math.inf
        self.min_y = math.inf
        self.max_x = -math.inf
        self.max_y = -math.inf

    def add(self, x: float, y: float) -> None:
        self.min_x = min(self.min_x, x)
        self.min_y = min(self.min_y, y)
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)

    def rect(self) -> Rect:
        if self.min_x is math.inf:
            raise ValueError("empty path")
        return Rect(self.min_x, self.min_y,
                    self.max_x - self.min_x, self.max_y - self.min_y)


_PATH_TOKEN_RE = re.compile(
    r"([MmLlHhVvCcSsQqTtAaZz])|" + _NUMBER_RE.pattern)


@dataclass(frozen=True)
class MoveTo:
    x: float
    y: float


@dataclass(frozen=True)
class LineTo:
    x: float
    y: float


@dataclass(frozen=True)
class CubicTo:
    x1: float
    y1: float
    x2: float
    y2: float
    x: float
    y: float


@dataclass(frozen=True)
class QuadTo:
    x1: float
    y1: float
    x: float
    y: float


@dataclass(frozen=True)
class ClosePath:
    pass


PathSegment = MoveTo | LineTo | CubicTo | QuadTo | ClosePath


def path_segments(d: str) -> tuple[PathSegment, ...]:
    """Parse SVG path data into absolute, explicit segments. Supports
    M/L/H/V/C/S/Q/T/Z, absolute and relative; relative coordinates, H/V
    shorthands, and S/T control-point reflections are all resolved, so the
    result contains only MoveTo/LineTo/CubicTo/QuadTo/ClosePath. Arcs (A)
    are rejected loudly — Verovio does not emit them."""
    tokens: list[str] = [m.group(0) for m in _PATH_TOKEN_RE.finditer(d)]
    segments: list[PathSegment] = []
    i = 0
    cx = cy = 0.0                 # current point
    sx = sy = 0.0                 # subpath start
    prev_cubic_ctrl: tuple[float, float] | None = None
    prev_quad_ctrl: tuple[float, float] | None = None
    cmd = ""

    def num() -> float:
        nonlocal i
        val = float(tokens[i])
        i += 1
        return val

    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
        elif not cmd:
            raise ValueError(f"path data starts with a number: {d[:40]!r}")
        # implicit repeats: M repeats as L (m as l), others repeat as themselves
        elif cmd == "M":
            cmd = "L"
        elif cmd == "m":
            cmd = "l"

        rel = cmd.islower()
        op = cmd.upper()
        new_cubic = new_quad = None

        if op == "Z":
            cx, cy = sx, sy
            segments.append(ClosePath())
        elif op == "M":
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            cx, cy = sx, sy = x, y
            segments.append(MoveTo(x, y))
        elif op == "L":
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            cx, cy = x, y
            segments.append(LineTo(x, y))
        elif op == "H":
            x = num()
            cx = cx + x if rel else x
            segments.append(LineTo(cx, cy))
        elif op == "V":
            y = num()
            cy = cy + y if rel else y
            segments.append(LineTo(cx, cy))
        elif op in ("C", "S"):
            if op == "C":
                x1, y1 = num(), num()
                if rel:
                    x1, y1 = cx + x1, cy + y1
            else:  # S: first control = reflection of previous cubic control
                if prev_cubic_ctrl is not None:
                    x1, y1 = 2 * cx - prev_cubic_ctrl[0], 2 * cy - prev_cubic_ctrl[1]
                else:
                    x1, y1 = cx, cy
            x2, y2 = num(), num()
            x, y = num(), num()
            if rel:
                x2, y2, x, y = cx + x2, cy + y2, cx + x, cy + y
            segments.append(CubicTo(x1, y1, x2, y2, x, y))
            new_cubic = (x2, y2)
            cx, cy = x, y
        elif op in ("Q", "T"):
            if op == "Q":
                x1, y1 = num(), num()
                if rel:
                    x1, y1 = cx + x1, cy + y1
            else:  # T: control = reflection of previous quad control
                if prev_quad_ctrl is not None:
                    x1, y1 = 2 * cx - prev_quad_ctrl[0], 2 * cy - prev_quad_ctrl[1]
                else:
                    x1, y1 = cx, cy
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            segments.append(QuadTo(x1, y1, x, y))
            new_quad = (x1, y1)
            cx, cy = x, y
        elif op == "A":
            raise ValueError("SVG arc commands are unsupported "
                             "(Verovio never emits them)")
        else:
            raise ValueError(f"unknown path command {cmd!r}")

        prev_cubic_ctrl = new_cubic
        prev_quad_ctrl = new_quad

    return tuple(segments)


def path_bbox(d: str) -> Rect:
    """Exact bounding box of an SVG path's geometry (anchor points plus
    bézier extrema)."""
    ext = _Extent()
    cx = cy = 0.0                 # current point
    sx = sy = 0.0                 # subpath start
    for seg in path_segments(d):
        if isinstance(seg, MoveTo):
            cx, cy = sx, sy = seg.x, seg.y
            ext.add(cx, cy)
        elif isinstance(seg, LineTo):
            cx, cy = seg.x, seg.y
            ext.add(cx, cy)
        elif isinstance(seg, CubicTo):
            ext.add(seg.x, seg.y)
            for t in _cubic_extrema(cx, seg.x1, seg.x2, seg.x):
                ext.add(_cubic_at(cx, seg.x1, seg.x2, seg.x, t),
                        _cubic_at(cy, seg.y1, seg.y2, seg.y, t))
            for t in _cubic_extrema(cy, seg.y1, seg.y2, seg.y):
                ext.add(_cubic_at(cx, seg.x1, seg.x2, seg.x, t),
                        _cubic_at(cy, seg.y1, seg.y2, seg.y, t))
            cx, cy = seg.x, seg.y
        elif isinstance(seg, QuadTo):
            ext.add(seg.x, seg.y)
            for t in _quad_extrema(cx, seg.x1, seg.x):
                ext.add(_quad_at(cx, seg.x1, seg.x, t),
                        _quad_at(cy, seg.y1, seg.y, t))
            for t in _quad_extrema(cy, seg.y1, seg.y):
                ext.add(_quad_at(cx, seg.x1, seg.x, t),
                        _quad_at(cy, seg.y1, seg.y, t))
            cx, cy = seg.x, seg.y
        else:                     # ClosePath
            cx, cy = sx, sy
    return ext.rect()


_ELLIPSE_KAPPA = 0.5522847498307936


def ellipse_path(cx: float, cy: float, rx: float, ry: float) -> str:
    """An ellipse as four cubic béziers (so downstream needs no arc
    support). Standard kappa approximation."""
    kx, ky = rx * _ELLIPSE_KAPPA, ry * _ELLIPSE_KAPPA
    return (f"M{cx + rx} {cy} "
            f"C{cx + rx} {cy + ky} {cx + kx} {cy + ry} {cx} {cy + ry} "
            f"C{cx - kx} {cy + ry} {cx - rx} {cy + ky} {cx - rx} {cy} "
            f"C{cx - rx} {cy - ky} {cx - kx} {cy - ry} {cx} {cy - ry} "
            f"C{cx + kx} {cy - ry} {cx + rx} {cy - ky} {cx + rx} {cy} Z")


def polygon_path(points: str, close: bool = True) -> str:
    coords = [float(x) for x in _NUMBER_RE.findall(points)]
    pairs = list(zip(coords[0::2], coords[1::2]))
    if not pairs:
        raise ValueError(f"empty polygon points: {points!r}")
    body = "M" + " L".join(f"{x} {y}" for x, y in pairs)
    return body + (" Z" if close else "")


def rect_path(x: float, y: float, w: float, h: float) -> str:
    return f"M{x} {y} L{x + w} {y} L{x + w} {y + h} L{x} {y + h} Z"


def line_path(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"M{x1} {y1} L{x2} {y2}"
