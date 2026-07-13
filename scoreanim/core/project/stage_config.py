"""Stage-level text elements (ARCHITECTURE.md §3 ruling 4, PHASES 2.3).

From Phase 2 on the engraved header is suppressed; title/composer/lyricist
live in stage_config as stage-level text, styled and positioned in-app and
(from Phase 3 on) animatable like any element. Defaults are seeded from the
score's credit texts; the stage never re-engraves when they change.

Part of the project document (user intent). No mutations exist yet — the
first editing command (rule 8) arrives with the styling UI, not in Phase 2.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace

from scoreanim.core.engraving.types import Layout, RenderedElement
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_prep import CreditText, PreparedScore

# 1 pt = 25.4/72 mm = 25.4/72*10 page units (page units are 1/10 mm).
PT_TO_PAGE_UNITS: float = 25.4 / 72 * 10

_ANCHOR_BY_JUSTIFY = {"left": "start", "center": "middle", "right": "end"}

# Credit default-x/default-y are deliberately IGNORED for the defaults:
# measured on the fixture (2026-07-10), Dorico's credit coordinates match
# neither its own PDF title block (title 22% down the page) nor the page
# center (593.75 tenths vs a 1397.65-tenth page). Defaults instead use a
# conventional title-block layout: x from justify, y stacked from the top
# by font size — centered lines first, then left/right columns — scaled
# down uniformly if the encoded layout leaves less room above the music
# (Verovio reclaims header space; it does not reserve a Dorico-style
# title frame).
_X_FRAC = {"start": 0.07, "middle": 0.5, "end": 0.93}
_LINE_ADVANCE = 1.35                 # baseline-to-baseline, in font sizes
_DESCENT = 0.25                      # descent allowance, in font sizes
_BAND_FILL = 0.9                     # fraction of the free band the block may use
_TOP_MARGIN = 15.0                   # gap above the block, page units (1.5 mm)
_MIN_SCALE = 0.4                     # floor: never shrink below a readable size
_FALLBACK_BAND_FRAC = 0.1            # free band if no content_top is given


@dataclass(frozen=True)
class StageTextElement:
    element_id: str              # "stage:title", "stage:composer", …
    content: str
    page: int                    # 1-based
    x: float                     # page units, y-down (same space as Layout)
    y: float                     # baseline position
    anchor: str                  # "start" | "middle" | "end"
    font_size: float             # page units
    color: str | None = None
    bold: bool = False
    italic: bool = False


# Tempo-overlay replacement texts (Phase 9.2) carry the engraved element's
# id behind this prefix ("stage:overlay:P1:m1:s1:v0:text:0") so the link
# to the hidden original is recoverable and round-trips.
OVERLAY_PREFIX = "stage:overlay:"


def is_header_text(text: StageTextElement) -> bool:
    """The band-fitted title block: page-1 stage texts that are not
    tempo-overlay replacements (overlays sit at their engraved position
    and must never rescale with the header)."""
    return text.page == 1 and not text.element_id.startswith(OVERLAY_PREFIX)


class PresentationMode(enum.Enum):
    """What the stage frames: whole pages (v1 behavior, default) or one
    system band at a time (Phase 7.4). Presentation intent only — the
    Layout is identical in both modes (no re-engrave, rule 7)."""
    PAGED = enum.auto()
    SYSTEM = enum.auto()


@dataclass(frozen=True)
class StageConfig:
    texts: tuple[StageTextElement, ...] = ()
    mode: PresentationMode = PresentationMode.PAGED


def page_content_top(layout: Layout, page: int = 1) -> float:
    """Top edge of the top STAFF on a page — the band the default title
    block may occupy. Tempo and rehearsal marks also live above the top
    staff, but off-center; centered title lines coexist with them the
    same way a running header does."""
    staff_tops = [e.bbox.y for e in layout.elements
                  if e.page == page
                  and e.identity.kind is ElementKind.STAFF_LINES]
    if staff_tops:
        return min(staff_tops)
    tops = [e.bbox.y for e in layout.elements if e.page == page]
    return min(tops) if tops else 0.0


# SMuFL metronome glyphs → text equivalents for the overlay replacement
# (Phase 9.2). Fidelity caveat, accepted at scoping: the replacement
# renders in the stage-text face (a serif), not Bravura — ♩ instead of
# the engraved metronome glyph. Unknown music codepoints fall back to ♩.
_SMUFL_TEXT = {
    "\ueca3": "\U0001d15e",     # metNoteHalfUp
    "\ueca5": "\u2669",         # metNoteQuarterUp
    "\ueca7": "\u266a",         # metNote8thUp
    "\ueca9": ".",              # metAugmentationDot
}
_SMUFL_RANGE = range(0xE000, 0xF900)             # SMuFL private use area


def _runs_text(runs) -> str:
    """Text equivalent of a run sequence. Consecutive duplicate MUSIC
    codepoints collapse across run boundaries first: Verovio's tofu on
    the fixture leaves the metronome codepoint in the 405px text run AND
    the Bravura run (BACKLOG 3) — the overlay must not read ♩♩."""
    raw = "".join(r.content for r in runs)
    kept: list[str] = []
    for ch in raw:
        if ord(ch) in _SMUFL_RANGE and kept and kept[-1] == ch:
            continue
        kept.append(ch)
    return "".join(
        _SMUFL_TEXT.get(ch, "♩" if ord(ch) in _SMUFL_RANGE else ch)
        for ch in kept).replace("\xa0", " ")


def seed_overlay_text(element: RenderedElement) -> StageTextElement:
    """Replacement stage text for an engraved text element (Phase 9.2),
    seeded at its engraved position/size. element_id = OVERLAY_PREFIX +
    the engraved id, so the link to the hidden original is recoverable
    and round-trips. Content joins the runs with music glyphs mapped to
    text equivalents (♩)."""
    prim = element.glyph.texts[0]
    x, y = prim.transform.apply(prim.x, prim.y)
    text_runs = [r for r in prim.runs if r.font_family != "Bravura"]
    lead = text_runs[0] if text_runs else prim.runs[0]
    # axis-aligned scale: font size maps through |d| (the y scale)
    font_size = lead.font_size * abs(prim.transform.d)
    content = _runs_text(prim.runs).strip()
    return StageTextElement(
        element_id=OVERLAY_PREFIX + str(element.identity.element_id),
        content=content,
        page=element.page,
        x=x,
        y=y,
        anchor=prim.anchor,
        font_size=font_size,
        bold=lead.font_weight == "bold",
        italic=lead.font_style == "italic",
    )


def fit_texts(texts: tuple[StageTextElement, ...], band: float,
              top: float = _TOP_MARGIN) -> tuple[StageTextElement, ...]:
    """Uniform scale-down of a text block to fit above `band` (the free
    space page_content_top reports), about y=top: y' = top + (y-top)*s,
    font' = font*s. Down-only — a block that already fits comes back
    unchanged (the same tuple), and nothing ever scales back up: the
    natural-1.0 layout is not stored (rule 5), so there is no baseline
    to grow toward. Never shrinks below _MIN_SCALE."""
    bottom = max((t.y + _DESCENT * t.font_size for t in texts), default=0.0)
    if not bottom > _BAND_FILL * band > top:
        return texts
    scale = max((_BAND_FILL * band - top) / (bottom - top), _MIN_SCALE)
    return tuple(replace(t,
                         y=top + (t.y - top) * scale,
                         font_size=t.font_size * scale)
                 for t in texts)


def default_stage_config(prepared: PreparedScore,
                         content_top: float | None = None) -> StageConfig:
    """Seed stage texts from the score's credits: front-matter credits
    (title/subtitle/composer/… on page 1) become stage text elements.
    Page-number/running-head credits (pages 2+) are deliberately skipped
    in v1. Layout: centered credits stack from the top in document order;
    left- and right-anchored credits then stack in independent columns
    below the centered block. If the block is taller than the free band
    above the music (content_top, from page_content_top), all font sizes
    scale down uniformly to fit (fit_texts — _lay_out is linear in
    scale, so the affine refit equals a re-lay-out at that scale)."""
    front = [c for c in prepared.credits
             if c.page == 1 and c.credit_type != "page number"]
    band = content_top if content_top is not None \
        else _FALLBACK_BAND_FRAC * prepared.page_height
    texts = _lay_out(front, prepared, scale=1.0, top=_TOP_MARGIN)
    return StageConfig(texts=fit_texts(texts, band))


def _lay_out(front: list[CreditText], prepared: PreparedScore,
             scale: float, top: float = 0.0) -> tuple[StageTextElement, ...]:
    centered, sides = _split(front)
    texts: list[StageTextElement] = []
    counters: dict[str, int] = {}

    def emit(credit: CreditText, baseline: float) -> None:
        tag = credit.credit_type or "text"
        n = counters.get(tag, 0)
        counters[tag] = n + 1
        anchor = _ANCHOR_BY_JUSTIFY.get(credit.justify or "", "start")
        texts.append(StageTextElement(
            element_id=f"stage:{tag}" + (f":{n}" if n else ""),
            content=credit.text,
            page=credit.page,
            x=_X_FRAC[anchor] * prepared.page_width,
            y=baseline,
            anchor=anchor,
            font_size=_size(credit) * scale,
            color=credit.color,
        ))

    cursor = top
    for credit in centered:
        cursor += _size(credit) * scale      # ascent ≈ font size
        emit(credit, cursor)
        cursor += (_LINE_ADVANCE - 1.0) * _size(credit) * scale

    columns = {"start": cursor, "end": cursor}
    for credit in sides:
        anchor = _ANCHOR_BY_JUSTIFY.get(credit.justify or "", "start")
        columns[anchor] += _size(credit) * scale
        emit(credit, columns[anchor])
        columns[anchor] += (_LINE_ADVANCE - 1.0) * _size(credit) * scale

    return tuple(texts)


def _split(front: list[CreditText]) -> tuple[list[CreditText], list[CreditText]]:
    centered = [c for c in front
                if _ANCHOR_BY_JUSTIFY.get(c.justify or "") == "middle"]
    return centered, [c for c in front if c not in centered]


def _size(credit: CreditText) -> float:
    return (credit.font_size_pt or 10.0) * PT_TO_PAGE_UNITS
