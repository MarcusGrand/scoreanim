"""Framing state for the stage view: the fitted frame, the visible
band, and the letterbox mask outside it.

View-level on purpose (the StageView docstring's ruling): the scenes
are shared with export, which must never see a mask item, so everything
here describes what the VIEW paints and fits, never what a scene
contains. Pure geometry over QRectF — no widget, so it tests without a
window.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF


class StageFraming:
    """The view's frame (what fitInView targets) and band (what is
    visible).

    Paged mode: both None — the scene rect is the frame and everything
    is visible. System mode: a page-sized frame centered vertically on
    the band, everything outside the band masked."""

    def __init__(self) -> None:
        self.band: QRectF | None = None
        self.frame: QRectF | None = None

    def set_page(self) -> None:
        self.band = None
        self.frame = None

    def set_system_band(self, page: QRectF, band: QRectF) -> None:
        self.band = QRectF(band)
        self.frame = QRectF(page.left(),
                            band.center().y() - page.height() / 2,
                            page.width(), page.height())

    def fit_target(self, scene_rect: QRectF) -> QRectF:
        return self.frame if self.frame is not None else scene_rect

    def scene_rect(self, page: QRectF) -> QRectF:
        """What the view's scene rect should be. The frame may extend
        past the page (a system near the page's top or bottom); widening
        the view's scene rect lets fitInView center there instead of
        clamping to the page — the overhang renders as view background,
        which is the letterbox, exactly right."""
        if self.frame is None:
            return page
        return self.frame.united(page)

    def contains(self, scene_pos: QPointF) -> bool:
        """Is this scene point inside the visible region?"""
        return self.band is None or self.band.contains(scene_pos)

    def mask_strips(self, rect: QRectF) -> list[QRectF]:
        """Letterbox strips covering the part of the exposed region
        `rect` outside the band (four edges; corner overlap is harmless
        — the mask is the same opaque color as the view background)."""
        band = self.band
        if band is None:
            return []
        strips: list[QRectF] = []
        if rect.top() < band.top():
            strips.append(QRectF(rect.left(), rect.top(), rect.width(),
                                 band.top() - rect.top()))
        if rect.bottom() > band.bottom():
            strips.append(QRectF(rect.left(), band.bottom(), rect.width(),
                                 rect.bottom() - band.bottom()))
        if rect.left() < band.left():
            strips.append(QRectF(rect.left(), rect.top(),
                                 band.left() - rect.left(), rect.height()))
        if rect.right() > band.right():
            strips.append(QRectF(band.right(), rect.top(),
                                 rect.right() - band.right(), rect.height()))
        return strips
