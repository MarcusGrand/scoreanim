"""Neutral engraving/layout types. No provider types leak past these
(CLAUDE.md rule 4): downstream code sees Layout / RenderedElement /
RenderPrimitive only.

Coordinate space: "page units" = 1/10 mm, y down, origin at the page's
top-left — the same space as PageGeometry, derived from the score's own
<defaults> (the user owns page layout, rule 7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from scoreanim.core.score.identity import Beats, ElementIdentity


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
        """Axis-aligned bbox of the transformed rectangle, mapped by its
        four corners: exact for axis-aligned and 90-degree-multiple
        rotations (Verovio's vertical text — Phase 11), conservative for
        arbitrary rotation/skew. Reduces to the old two-corner result
        when the transform is axis-aligned."""
        pts = [self.apply(r.x, r.y), self.apply(r.x2, r.y),
               self.apply(r.x, r.y2), self.apply(r.x2, r.y2)]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


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
    # Score-wide system index (1-based, document order), stamped from the
    # engraved SVG's system nesting. Engraving-derived layout data (like
    # page), not musical identity — reveal_x (Phase 5) is per system.
    # None for elements outside any system (e.g. page-header texts).
    system: int | None = None
    # TEXT sub-class from the engraved SVG ("tempo"/"dir"/"reh"/"label"/
    # "labelAbbr"/"pgHead"/"pgFoot"/"mNum"); None for non-TEXT elements.
    # Presentation metadata like page/system — ElementIdentity and the
    # minted ids are UNTOUCHED (Phase 9 ruling 2026-07-12: a finer kind
    # would re-roll the kind tag inside every text ElementId). The
    # tempo-mark overlay (Phase 9.2) filters on text_class == "tempo".
    text_class: str | None = None


@dataclass(frozen=True)
class PageGeometry:
    number: int                  # 1-based
    width: float                 # page units (1/10 mm)
    height: float


@dataclass(frozen=True)
class Layout:
    pages: tuple[PageGeometry, ...]
    elements: tuple[RenderedElement, ...]


@dataclass(frozen=True)
class MeasureTimeline:
    """The engraved measure timeline — THE beat authority for the whole
    app (ruling 2026-07-22, FINDING-1 fix): Verovio timemap qstamps on
    the PERFORMANCE axis. The timemap is playback-expanded, so a
    repeated span occupies the beats of all its passes: repeated
    measures keep their FIRST-pass positions (the expansion's clone
    measures are not part of the notation) and the next new measure
    starts after the full expansion — which is what syncs with a
    recording that takes the repeat.

    ``starts``/``durations`` are keyed by the 1-based document-order
    measure ordinal (ARCHITECTURE §3 item 12); a duration runs to the
    next first-pass downbeat. ``score_end`` is the last timemap qstamp;
    for a trailing event-less measure (e.g. a final bar-repeat bar) it
    can fall short of that bar's musical end — build_score_model floors
    the final bar with its notated length (the one place the nominal
    length survives).
    """
    starts: Mapping[int, Beats]
    durations: Mapping[int, Beats]
    score_end: Beats


# Concert pitch is a fixed engraving rule (CLAUDE.md rule 9), not a user
# option — deliberately a module constant, not an EngravingParams field.
TRANSPOSE_TO_SOUNDING_PITCH: bool = True


@dataclass(frozen=True)
class LoadWarning:
    """A non-fatal load anomaly, surfaced instead of silently absorbed
    (Phase 10 ruling b). Messages use musical coordinates only —
    provider ids never leak (CLAUDE.md rule 4).

    Codes: "dropped-spanner" (the engraver emitted no ink for a spanner
    in the source), "unattributed-continuation" (a continuation segment
    matched no source and was skipped), "segment-count-mismatch"
    (continuation segments vs crossing sources disagreed in a system),
    "implausible-tie" (a tie force-matched to a distant note was
    suppressed — Phase 10R), "hide-unavailable" (empty-staff hiding
    skipped: it would hide a slash-region staff, rule 10),
    "repaginated" (encoded page breaks replaced — systems overflowed;
    page-scoped ids shift), "scaled-to-fit" (a system taller than its
    page could not be paginated away, so the engraving was scaled down
    uniformly so nothing is clipped — Phase 12.5, never-clip completion),
    "system-overflow" (defensive: a system still overflows after
    scale-to-fit), "unknown-class" (a drawable SVG class the decomposer
    does not know was rendered as a static element instead of failing the
    load — app path only, Phase 11.4; strict loads still raise).
    """
    code: str
    message: str


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
