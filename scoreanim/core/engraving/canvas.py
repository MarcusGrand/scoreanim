"""The video canvas: what part of the page the export frame shows.

Pure, no Qt. The one function here is the seam both paths share: the
live stage fits its view to this rect, and export renders exactly this
rect into a canvas.width x canvas.height image — so what you see in the
window is what the frame carries, by construction.

It is the inverse of systems.centered_fit: centered_fit says where a
page lands INSIDE a frame; canvas_view_rect says what page region a
frame covers — the whole page, with letterbox slack on the short axis.
(How BIG the notation is on that page is a different knob entirely:
EngravingParams.scale, an engraving input. The frame always shows the
whole page.)
"""
from __future__ import annotations

from scoreanim.core.engraving.types import Rect


def canvas_view_rect(page_w: float, page_h: float,
                     canvas_w: float, canvas_h: float,
                     center_y: float | None = None) -> Rect:
    """The rect, in page units, that a canvas_w x canvas_h frame shows:
    the page fitted, centered on the page — center_y recenters it
    vertically (system mode centers on the band) while x stays
    page-centered."""
    if page_w <= 0 or page_h <= 0 or canvas_w <= 0 or canvas_h <= 0:
        raise ValueError(f"bad canvas {canvas_w}x{canvas_h} for page "
                         f"{page_w}x{page_h}")
    # pixels per page unit when the page fits the frame; the frame
    # covers frame/ppu page units
    ppu = min(canvas_w / page_w, canvas_h / page_h)
    w = canvas_w / ppu
    h = canvas_h / ppu
    cy = page_h / 2 if center_y is None else center_y
    return Rect(page_w / 2 - w / 2, cy - h / 2, w, h)
