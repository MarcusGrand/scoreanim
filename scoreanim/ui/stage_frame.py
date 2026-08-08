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

from scoreanim.core.engraving.canvas import canvas_view_rect
from scoreanim.core.project.stage_config import VideoCanvas


class StageFraming:
    """The view's frame (what fitInView targets) and band (what is
    visible).

    Paged mode, no canvas: both None — the scene rect is the frame and
    everything is visible. System mode: a frame centered vertically on
    the band, everything outside the band masked. A video canvas
    (2026-08-06) replaces the frame's shape in BOTH modes with the
    user's own, computed by the same pure rect export renders, and
    masks outside it — what shows inside the frame is what the video
    frame will carry."""

    def __init__(self) -> None:
        self.band: QRectF | None = None
        self.frame: QRectF | None = None
        self.canvas: VideoCanvas | None = None

    def set_canvas(self, canvas: VideoCanvas | None) -> None:
        """Store the document's canvas; the caller re-runs set_page or
        set_system_band to recompute the frame."""
        self.canvas = canvas

    def set_page(self, page: QRectF) -> None:
        self.band = None
        self.frame = self._canvas_frame(page)

    def set_system_band(self, page: QRectF, band: QRectF) -> None:
        self.band = QRectF(band)
        if self.canvas is None:
            self.frame = QRectF(page.left(),
                                band.center().y() - page.height() / 2,
                                page.width(), page.height())
        else:
            self.frame = self._canvas_frame(page,
                                            center_y=band.center().y())

    def _canvas_frame(self, page: QRectF,
                      center_y: float | None = None) -> QRectF | None:
        if self.canvas is None:
            return None
        r = canvas_view_rect(page.width(), page.height(),
                             self.canvas.width, self.canvas.height,
                             center_y)
        return QRectF(r.x, r.y, r.w, r.h)

    def fit_target(self, scene_rect: QRectF) -> QRectF:
        return self.frame if self.frame is not None else scene_rect

    def scene_rect(self, page: QRectF) -> QRectF:
        """What the view's scene rect should be: the frame may extend
        past the page (a system near the page's top or bottom, or a
        canvas with letterbox slack); widening the view's scene rect
        lets fitInView center there instead of clamping to the page —
        the overhang renders as view background, which is the
        letterbox. (The canvas fit replaces this with its own constant
        overscan rect — see StageView._fit_canvas.)"""
        if self.frame is None:
            return page
        return self.frame.united(page)

    def visible_rect(self) -> QRectF | None:
        """The scene region actually on show, or None for everything.
        A canvas crops to its frame; a band crops to the system; with
        both, what shows is their intersection."""
        if self.canvas is None:
            return self.band
        if self.band is None:
            return self.frame
        return self.band.intersected(self.frame)

    def contains(self, scene_pos: QPointF) -> bool:
        """Is this scene point inside the visible region? Ink cropped
        away by the canvas (or masked outside the band) is invisible
        but fully hittable, so the view gates clicks here."""
        visible = self.visible_rect()
        return visible is None or visible.contains(scene_pos)

    def mask_strips(self, rect: QRectF) -> list[QRectF]:
        """No-canvas masking: letterbox strips covering the part of the
        exposed region `rect` outside the visible region."""
        band = self.visible_rect()
        if band is None:
            return []
        return strips_outside(rect, band)

    def canvas_mask(self, rect: QRectF) -> tuple[list[QRectF],
                                                 list[QRectF]]:
        """Canvas masking, two colors: (inside, outside).

        `outside` is everything in `rect` past the frame — letterbox.
        `inside` is the part of the frame holding a NEIGHBOR system's
        ink (frame minus band, system mode only) — painted in the
        frame's own fill, so the canvas reads as ONE still rectangle
        whose content changes, never a box that reshapes per system."""
        assert self.frame is not None
        outside = strips_outside(rect, self.frame)
        exposed_frame = self.frame.intersected(rect)
        if self.band is None or exposed_frame.isEmpty():
            return [], outside
        inside = strips_outside(exposed_frame,
                                self.band.intersected(self.frame))
        return inside, outside


def strips_outside(rect: QRectF, inner: QRectF) -> list[QRectF]:
    """The part of `rect` outside `inner`, as four edge strips (corner
    overlap is harmless — every caller fills them one opaque color)."""
    strips: list[QRectF] = []
    if rect.top() < inner.top():
        strips.append(QRectF(rect.left(), rect.top(), rect.width(),
                             inner.top() - rect.top()))
    if rect.bottom() > inner.bottom():
        strips.append(QRectF(rect.left(), inner.bottom(), rect.width(),
                             rect.bottom() - inner.bottom()))
    if rect.left() < inner.left():
        strips.append(QRectF(rect.left(), rect.top(),
                             inner.left() - rect.left(), rect.height()))
    if rect.right() > inner.right():
        strips.append(QRectF(inner.right(), rect.top(),
                             rect.right() - inner.right(), rect.height()))
    return strips
