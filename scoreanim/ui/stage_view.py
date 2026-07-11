"""StageView: the paged score at the score's own aspect ratio.

Letterboxing is fitInView(sceneRect, KeepAspectRatio) against a dark
view background — the white page rect in each scene is the "screen".
Fit mode re-letterboxes on every resize; wheel zoom (anchored under the
cursor) leaves fit mode until the Fit action restores it. Drag to pan.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
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

    def show_scene(self, scene: QGraphicsScene) -> None:
        """Page flip: swap scenes, keep the current fit/zoom behavior."""
        self.setScene(scene)
        if self._fit_mode:
            self._fit()

    def fit(self) -> None:
        """Letterbox the page in the window and stay fitted on resize."""
        self._fit_mode = True
        self._fit()

    def _fit(self) -> None:
        if self.scene() is not None:
            self.fitInView(self.scene().sceneRect(),
                           Qt.AspectRatioMode.KeepAspectRatio)

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
