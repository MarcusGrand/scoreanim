"""Neutral engraving/layout types. No provider types leak past these
(CLAUDE.md rule 4): downstream code sees Layout / RenderedElement /
RenderPrimitive only.

Coordinate space: "page units" = 1/10 mm, y down, origin at the page's
top-left — the same space as PageGeometry, derived from the score's own
<defaults> (the user owns page layout, rule 7).
"""

from __future__ import annotations

from dataclasses import dataclass

from scoreanim.core.score.identity import ElementIdentity


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def center(self) -> Point:
        return Point(self.x + self.w / 2, self.y + self.h / 2)

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    def union(self, other: "Rect") -> "Rect":
        x1 = min(self.x, other.x)
        y1 = min(self.y, other.y)
        x2 = max(self.x2, other.x2)
        y2 = max(self.y2, other.y2)
        return Rect(x1, y1, x2 - x1, y2 - y1)

    def contains(self, other: "Rect", slack: float = 0.0) -> bool:
        return (self.x - slack <= other.x and self.y - slack <= other.y
                and other.x2 <= self.x2 + slack and other.y2 <= self.y2 + slack)


@dataclass(frozen=True)
class Affine:
    """2D affine transform, SVG matrix order: maps (x, y) to
    (a·x + c·y + e, b·x + d·y + f)."""
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def compose(self, inner: "Affine") -> "Affine":
        """self ∘ inner (apply inner first, then self)."""
        return Affine(
            a=self.a * inner.a + self.c * inner.b,
            b=self.b * inner.a + self.d * inner.b,
            c=self.a * inner.c + self.c * inner.d,
            d=self.b * inner.c + self.d * inner.d,
            e=self.a * inner.e + self.c * inner.f + self.e,
            f=self.b * inner.e + self.d * inner.f + self.f,
        )

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.c * y + self.e,
                self.b * x + self.d * y + self.f)

    @property
    def is_axis_aligned(self) -> bool:
        return self.b == 0.0 and self.c == 0.0

    def apply_rect(self, r: Rect) -> Rect:
        """Exact for axis-aligned transforms (the only kind Verovio emits)."""
        if not self.is_axis_aligned:
            raise ValueError(f"non-axis-aligned transform: {self}")
        x1, y1 = self.apply(r.x, r.y)
        x2, y2 = self.apply(r.x2, r.y2)
        return Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))


@dataclass(frozen=True)
class PathPrimitive:
    """One resolved drawable: SVG path data in its own coordinates plus
    the affine mapping those coordinates to page units. <use> references
    are dereferenced at decomposition time — no defs survive here."""
    d: str
    transform: Affine
    fill: str | None = None
    stroke: str | None = None
    stroke_width: float | None = None


@dataclass(frozen=True)
class TextRun:
    """One styled run inside a TextPrimitive. Runs flow inline after one
    another (SVG tspan semantics); font_size is in the primitive's own
    coordinates. font_family None means the engraver's text face (a
    serif); music-glyph runs carry an explicit family (e.g. Bravura)."""
    content: str
    font_size: float
    font_family: str | None = None
    font_style: str | None = None
    font_weight: str | None = None
    fill: str | None = None


@dataclass(frozen=True)
class TextPrimitive:
    """A positioned block of text runs (title, label, direction…). x/y is
    the SVG anchor point in the primitive's own coordinates; `anchor`
    says how the flowed runs hang on it (start/middle/end); transform
    maps to page units. Its bbox is a font-metric estimate, not exact."""
    runs: tuple[TextRun, ...]
    x: float
    y: float
    anchor: str                  # "start" | "middle" | "end"
    transform: Affine


@dataclass(frozen=True)
class RenderPrimitive:
    """Engine-neutral glyph: everything needed to redraw one element."""
    paths: tuple[PathPrimitive, ...]
    texts: tuple[TextPrimitive, ...] = ()


@dataclass(frozen=True)
class RenderedElement:
    identity: ElementIdentity
    page: int                    # 1-based, matching the score's own pages
    x: float                     # principal position in page units: the glyph
    y: float                     #   origin for single-glyph elements, else bbox center
    bbox: Rect
    anchor: Point                # transform origin (bbox center) for scale/pop
    glyph: RenderPrimitive


@dataclass(frozen=True)
class PageGeometry:
    number: int                  # 1-based
    width: float                 # page units (1/10 mm)
    height: float


@dataclass(frozen=True)
class Layout:
    pages: tuple[PageGeometry, ...]
    elements: tuple[RenderedElement, ...]


# Concert pitch is a fixed engraving rule (CLAUDE.md rule 9), not a user
# option — deliberately a module constant, not an EngravingParams field.
TRANSPOSE_TO_SOUNDING_PITCH: bool = True


@dataclass(frozen=True)
class EngravingParams:
    # Fixed seed so provider-internal ids are stable across loads
    # (CLAUDE.md rule 4); not user-facing.
    xml_id_seed: int = 42
    # ARCHITECTURE.md §3 ruling 4: from Phase 2 on the engraved header is
    # suppressed — title/composer live in stage_config. Not user-facing;
    # False exists so tests can keep pinning pgHead text decomposition
    # (suppression is a rendering option, not a decomposition exemption).
    # Verified: Verovio ids are identical either way, joins unaffected.
    suppress_header: bool = True
