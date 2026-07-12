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
from dataclasses import dataclass

from scoreanim.core.engraving.types import Layout
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


def default_stage_config(prepared: PreparedScore,
                         content_top: float | None = None) -> StageConfig:
    """Seed stage texts from the score's credits: front-matter credits
    (title/subtitle/composer/… on page 1) become stage text elements.
    Page-number/running-head credits (pages 2+) are deliberately skipped
    in v1. Layout: centered credits stack from the top in document order;
    left- and right-anchored credits then stack in independent columns
    below the centered block. If the block is taller than the free band
    above the music (content_top, from page_content_top), all font sizes
    scale down uniformly to fit."""
    front = [c for c in prepared.credits
             if c.page == 1 and c.credit_type != "page number"]
    band = content_top if content_top is not None \
        else _FALLBACK_BAND_FRAC * prepared.page_height
    top = _TOP_MARGIN
    texts = _lay_out(front, prepared, scale=1.0, top=top)
    bottom = max((t.y + _DESCENT * t.font_size for t in texts), default=0.0)
    if bottom > _BAND_FILL * band > top:
        scale = max((_BAND_FILL * band - top) / (bottom - top), _MIN_SCALE)
        texts = _lay_out(front, prepared, top=top, scale=scale)
    return StageConfig(texts=texts)


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
