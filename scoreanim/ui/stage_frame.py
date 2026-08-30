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
from scoreanim.core.engraving.systems import SystemsFrame
from scoreanim.core.engraving.types import Rect
from scoreanim.core.project.stage_config import VideoCanvas


class StageFraming:
    """The view's frame (what a fit targets) and band (what is visible).

    Paged mode, no canvas: both None — the scene rect is the frame and
    everything is visible. System mode: one CONSTANT frame (the load's
    `SystemsFrame`, 2026-08-30) placed so the current band is centred in
    it, with everything outside the band masked. A video canvas
    (2026-08-06) replaces the frame's shape in BOTH modes with the
    user's own — what shows inside the frame is what the video frame
    will carry. What the canvas is fitted AROUND is the mode's own
    unit: the whole page when paged, and the systems frame when in
    system mode (2026-08-30), so a system fills the video frame instead
    of sitting in a page-tall strip of it.

    Whenever there IS a frame the view fills it edge to edge and masks
    in two colours, so the frame reads as one still rectangle whose
    content changes rather than a shape that moves with the music."""

    def __init__(self) -> None:
        self.band: QRectF | None = None
        # how far the band may show before a NEIGHBOUR system would come
        # into view: (above, below), None on a side with no neighbour
        self.bounds: tuple[float | None, float | None] = (None, None)
        self.frame: QRectF | None = None
        self.canvas: VideoCanvas | None = None
        self.systems: SystemsFrame | None = None

    def set_canvas(self, canvas: VideoCanvas | None) -> None:
        """Store the document's canvas; the caller re-runs set_page or
        set_system_band to recompute the frame."""
        self.canvas = canvas

    def set_systems_frame(self, systems: SystemsFrame | None) -> None:
        """Store the load's constant systems-mode frame; the caller
        re-runs set_system_band to recompute the frame."""
        self.systems = systems

    def systems_frame(self) -> SystemsFrame | None:
        """The systems-mode frame as it stands right now: the load's
        constant frame, reshaped to the video canvas when there is one.

        Both inputs hold for a whole load, so this does too — the frame
        is still the same size and shape for every system, and a switch
        is still a translation. It changes only when the user changes
        the canvas, and that reframes in place."""
        if self.systems is None or self.canvas is None:
            return self.systems
        return self.systems.for_canvas(self.canvas.width,
                                       self.canvas.height)

    def set_page(self, page: QRectF) -> None:
        self.band = None
        self.bounds = (None, None)
        self.frame = self._canvas_frame(page)

    def set_system_band(self, page: QRectF, band: QRectF,
                        bounds: tuple[float | None, float | None]
                        = (None, None)) -> None:
        self.band = QRectF(band)
        self.bounds = bounds
        systems = self.systems_frame()
        if systems is not None:
            r = systems.rect_for(Rect(band.x(), band.y(),
                                      band.width(), band.height()))
            self.frame = QRectF(r.x, r.y, r.w, r.h)
        elif self.canvas is not None:
            # a canvas with no load behind it (a bare StageView in a
            # test): the page is the only unit there is to fit around
            self.frame = self._canvas_frame(page,
                                            center_y=band.center().y())
        else:
            # no load behind this view (a bare StageView in a test, or a
            # band shown before bind): the page's own height, which is
            # what systems mode framed with before the fixed frame
            self.frame = QRectF(page.left(),
                                band.center().y() - page.height() / 2,
                                page.width(), page.height())

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
        lets a fit centre there instead of clamping to the page — the
        overhang renders as view background, which is the letterbox.
        (A fitted frame replaces this with the constant overscan rect
        `fit_geometry` returns.)"""
        if self.frame is None:
            return page
        return self.frame.united(page)

    def visible_rect(self) -> QRectF | None:
        """The scene region actually on show, or None for everything.
        A frame crops to itself; a band crops to the system it owns;
        with both, what shows is their intersection."""
        if self.frame is None:
            return self.band
        if self.band is None:
            return self.frame
        return self.owned_band().intersected(self.frame)

    def owned_band(self) -> QRectF:
        """The band widened to everything this system owns.

        The mask has one job: hide the OTHER systems on the same paper.
        So it stops at a neighbour's edge rather than at this system's
        own ink, and where there is no neighbour — above the first
        system on a page, below the last — it opens to the frame. That
        is what shows the page's title block whole instead of slicing it
        where the first system's ink happens to start (Marcus,
        2026-08-30). Between two systems the mask still covers the whole
        gap: the neighbour's own bound IS the edge."""
        assert self.band is not None and self.frame is not None
        above, below = self.bounds
        top = self.frame.top() if above is None else max(above,
                                                         self.frame.top())
        bottom = self.frame.bottom() if below is None \
            else min(below, self.frame.bottom())
        if bottom <= top:                    # degenerate: trust the band
            return QRectF(self.band)
        return QRectF(self.band.left(), top, self.band.width(),
                      bottom - top)

    def contains(self, scene_pos: QPointF) -> bool:
        """Is this scene point inside the visible region? Ink cropped
        away by the frame (or masked outside the band) is invisible but
        fully hittable, so the view gates clicks here."""
        visible = self.visible_rect()
        return visible is None or visible.contains(scene_pos)

    def frame_mask(self, rect: QRectF) -> tuple[list[QRectF],
                                                list[QRectF]]:
        """Masking in two colours: (inside, outside).

        `outside` is everything in `rect` past the frame — letterbox.
        `inside` is the part of the frame holding a NEIGHBOR system's
        ink (frame minus band, system mode only) — painted in the
        frame's own fill, so the frame reads as ONE still rectangle
        whose content changes, never a box that reshapes per system."""
        assert self.frame is not None
        outside = strips_outside(rect, self.frame)
        exposed_frame = self.frame.intersected(rect)
        if self.band is None or exposed_frame.isEmpty():
            return [], outside
        inside = strips_outside(exposed_frame,
                                self.owned_band().intersected(self.frame))
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


def scroll_rect(frame: QRectF, page: QRectF) -> QRectF:
    """How far the view may scroll: the page with one frame of slack on
    every side.

    It depends on the page and the frame's SIZE, never on where the
    frame currently sits, so in system mode it is one rect for the whole
    load. That is what makes every system's arithmetic identical — a
    fitted frame cannot wobble on a switch, and a zoomed one cannot be
    clamped differently from the switch before it."""
    return page.adjusted(-frame.width(), -frame.height(),
                         frame.width(), frame.height())


def snapped_frame(frame: QRectF, scale: float) -> QRectF:
    """`frame` nudged so its top-left corner lands a quarter of a device
    pixel off the whole-pixel grid — at most half a pixel of movement
    against the band, which is invisible.

    Two things rest on it. Every rounding downstream lands the same side
    for every system, so a fitted frame cannot wobble on a switch. And
    two snapped frames are a WHOLE number of device pixels apart, so a
    zoomed camera can translate from one to the other exactly, with
    nothing left over to drift on the next switch."""
    snapped = QRectF(frame)
    snapped.translate(
        (round(frame.left() * scale) + 0.25) / scale - frame.left(),
        (round(frame.top() * scale) + 0.25) / scale - frame.top())
    return snapped


def frame_offset(frame: QRectF, origin: QPointF,
                 scale: float) -> QPointF:
    """Where the frame's top-left corner is sitting in the viewport, in
    device pixels. `origin` is the scene point at the viewport's own
    top-left corner (`QGraphicsView.mapToScene(0, 0)`).

    This is "where the glass is on screen", and holding it still across
    a switch is the whole of stage 2: the frame stays put, the music
    behind it changes, so the user's zoom and their place in the system
    both survive. Measured rather than remembered — it is a fact about
    the view, and the user moves it whenever they zoom or scroll."""
    return QPointF((frame.left() - origin.x()) * scale,
                   (frame.top() - origin.y()) * scale)


def fit_geometry(frame: QRectF, page: QRectF,
                 viewport_w: float, viewport_h: float,
                 ) -> tuple[float, QRectF, QRectF] | None:
    """How to fit a frame so it CANNOT move: (scale, snapped frame,
    scroll rect). None when there is nothing to fit.

    QGraphicsView.fitInView rounds through the integer scrollbars, and
    how it rounds depends on the frame's scene position — the canvas
    edge wobbled 1-4 px between systems during playback (2026-08-06),
    and a systems frame that slides with the band would do the same.
    Three choices pin it, and all three are the arithmetic here: the
    zoom is set directly (no fitInView, no 2 px margin — the frame IS
    the picture); the scroll range is one CONSTANT page-independent
    overscan rect (`scroll_rect`), so Qt's origin math is identical for
    every system; and the frame is nudged a quarter device pixel off
    the integer grid (`snapped_frame`), so every rounding along the way
    lands the same side for every system.

    Pure, so the constancy can be checked without a window."""
    if viewport_w <= 0 or viewport_h <= 0 or frame.isEmpty():
        return None
    scale = min(viewport_w / frame.width(), viewport_h / frame.height())
    return scale, snapped_frame(frame, scale), scroll_rect(frame, page)
