"""StageView: the paged score at the score's own aspect ratio.

Letterboxing is fitInView(sceneRect, KeepAspectRatio) against a dark
view background — the white page rect in each scene is the "screen".
Fit mode re-letterboxes on every resize; wheel zoom (anchored under the
cursor) leaves fit mode until the Fit action restores it. Drag to pan.

System mode (Phase 7.4, framing revised Phase 10R): show_system_band
keeps the PAGE's own frame — a page-sized, page-aspect window centered
vertically on the system's band, so the frame never changes shape
between modes and the system sits in the middle at natural page width
(ruling 2026-07-13). Masking is drawForeground — the view paints
letterbox color over every exposed scene region outside the band, so a
neighboring system on the same page never bleeds in at any window
aspect, zoom, or pan. View-level on purpose: the scenes are shared with
export (a separate ScoreScenes instance, but the same class rendered
scene-side), which must never see a mask item.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

_LETTERBOX = QColor("#3a3a3a")
_ZOOM_MIN = 0.05
_ZOOM_MAX = 40.0
# Same curve as the timeline views (ui/app_state.apply_wheel — keep in
# step): pixel-precise trackpad deltas, one wheel notch (≈40 px) = ×1.1.
_ZOOM_PER_PIXEL = math.log(1.1) / 40.0
_PIXELS_PER_NOTCH = 40.0


class StageView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.setRenderHints(QPainter.RenderHint.Antialiasing
                            | QPainter.RenderHint.TextAntialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(_LETTERBOX)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._fit_mode = True
        self._band: QRectF | None = None     # masked region (the system)
        self._frame: QRectF | None = None    # fitted region (page-sized)

    def show_scene(self, scene: QGraphicsScene) -> None:
        """Page flip: swap scenes, keep the current fit/zoom behavior."""
        self.setScene(scene)
        self.setSceneRect(scene.sceneRect())
        if self._fit_mode:
            self._fit()

    def show_system_band(self, scene: QGraphicsScene, band: QRectF) -> None:
        """System flip (Phase 7.4; framing revised Phase 10R): swap to
        the band's page scene and fit a PAGE-SIZED window centered
        vertically on the band — the frame keeps the page's aspect, the
        system occupies the middle at natural page width; everything
        outside the band letterboxes. A hard cut, exactly like a page
        flip (ruling R2)."""
        self.setScene(scene)
        self._band = QRectF(band)
        page = scene.sceneRect()
        self._frame = QRectF(page.left(),
                             band.center().y() - page.height() / 2,
                             page.width(), page.height())
        # the frame may extend past the page for systems near its top or
        # bottom; widening the VIEW's scene rect lets fitInView center
        # there instead of clamping to the page (the overhang renders as
        # view background = letterbox, exactly right)
        self.setSceneRect(self._frame.united(page))
        if self._fit_mode:
            self._fit()
        self.viewport().update()

    def clear_band(self) -> None:
        """Back to paged framing (mask off)."""
        self._band = None
        self._frame = None
        if self.scene() is not None:
            self.setSceneRect(self.scene().sceneRect())
        if self._fit_mode:
            self._fit()
        self.viewport().update()

    def fit(self) -> None:
        """Letterbox the page in the window and stay fitted on resize."""
        self._fit_mode = True
        self._fit()

    def _fit(self) -> None:
        if self.scene() is None:
            return
        target = self._frame if self._frame is not None \
            else self.scene().sceneRect()
        self.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)

    def drawForeground(self, painter, rect) -> None:  # noqa: N802
        """Letterbox masking for system mode: fill the exposed scene
        area outside the band (four edge strips; corner overlap is
        harmless — same opaque color as the view background)."""
        super().drawForeground(painter, rect)
        band = self._band
        if band is None:
            return
        if rect.top() < band.top():
            painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(),
                                    band.top() - rect.top()), _LETTERBOX)
        if rect.bottom() > band.bottom():
            painter.fillRect(QRectF(rect.left(), band.bottom(), rect.width(),
                                    rect.bottom() - band.bottom()),
                             _LETTERBOX)
        if rect.left() < band.left():
            painter.fillRect(QRectF(rect.left(), rect.top(),
                                    band.left() - rect.left(),
                                    rect.height()), _LETTERBOX)
        if rect.right() > band.right():
            painter.fillRect(QRectF(band.right(), rect.top(),
                                    rect.right() - band.right(),
                                    rect.height()), _LETTERBOX)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        if self._fit_mode:
            self._fit()

    def wheelEvent(self, event) -> None:  # noqa: N802
        pixel = event.pixelDelta()
        dy = (float(pixel.y()) if not pixel.isNull()
              else event.angleDelta().y() / 120.0 * _PIXELS_PER_NOTCH)
        if not dy:
            return
        factor = math.exp(dy * _ZOOM_PER_PIXEL)
        current = self.transform().m11()
        # clamp to the limits: smooth stop, and never move AGAINST the
        # gesture (a fit scale can legitimately sit below _ZOOM_MIN —
        # zooming out from there just holds, it must not snap upward)
        if factor < 1.0:
            factor = max(factor, min(1.0, _ZOOM_MIN / current))
        else:
            factor = min(factor, max(1.0, _ZOOM_MAX / current))
        if factor != 1.0:
            self._fit_mode = False
            self.scale(factor, factor)
        event.accept()
