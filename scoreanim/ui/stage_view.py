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

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

_LETTERBOX = QColor("#3a3a3a")
_ZOOM_MIN = 0.05
_ZOOM_MAX = 40.0
# Same curve as the timeline views (ui/app_state.apply_wheel — keep in
# step): pixel-precise trackpad deltas, one wheel notch (≈40 px) = ×1.1.
_ZOOM_PER_PIXEL = math.log(1.1) / 40.0
_PIXELS_PER_NOTCH = 40.0


class StageView(QGraphicsView):
    """Selection gesture (M2.3): click selects, drag pans.

    ScrollHandDrag consumes mouse events for panning, so the scene never
    sees a press and scene-side itemAt() is dead on arrival. Instead the
    view watches the press/release pair itself and calls it a CLICK when
    the pointer moved less than QApplication.startDragDistance(). Pan
    behavior is unchanged — a sub-threshold drag never panned visibly
    anyway — so no modifier key is needed."""

    # (scene position, the QGraphicsScene it was in). The scene travels
    # WITH the position because every page scene has the same sceneRect
    # — origin (0,0) at page size — so a position alone cannot say which
    # page was clicked, and the view is the only object that knows which
    # scene it is showing.
    clicked = Signal(QPointF, object)
    # M3.1: double-click edits text in place. Carries the scene for the
    # same reason `clicked` does. A double-click also fires `clicked`
    # first (Qt sends press/release before the double-click event), so
    # the element selects and THEN opens for editing — which is the
    # order a user expects anyway.
    double_clicked = Signal(QPointF, object)
    deselect_requested = Signal()        # Esc, or a click outside the band

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
        self._press_pos = None               # viewport px, for click detect
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # Esc needs focus

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

    # -- selection gesture -------------------------------------------------

    def in_band(self, scene_pos: QPointF) -> bool:
        """Is this scene point inside the visible band?

        In system mode the scene under the view is the whole PAGE and the
        letterbox is painted in drawForeground, so ink from a neighbouring
        system is invisible but fully hittable. The view is the only
        object that knows the band, so it gates here and the selection
        controller stays mode-blind. Paged mode: everything is visible."""
        return self._band is None or self._band.contains(scene_pos)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        press, self._press_pos = self._press_pos, None
        if press is None or event.button() != Qt.MouseButton.LeftButton:
            return
        moved = (event.position().toPoint() - press).manhattanLength()
        if moved > QApplication.startDragDistance():
            return                            # that was a pan, not a click
        if self.scene() is None:
            return
        scene_pos = self.mapToScene(press)
        if self.in_band(scene_pos):
            self.clicked.emit(scene_pos, self.scene())
        else:
            self.deselect_requested.emit()    # masked area: nothing there

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """Double-click opens text for in-place editing (M3.1).

        Gated on the band exactly like a click: in system mode the scene
        under the view is the whole page, so masked ink is invisible but
        still hittable, and editing something the user cannot see would
        be worse than ignoring them."""
        super().mouseDoubleClickEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.scene() is None:
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        if self.in_band(scene_pos):
            self.double_clicked.emit(scene_pos, self.scene())

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Esc deselects. View-level, not a window shortcut, so Esc keeps
        its normal meaning in dialogs, inspector fields, and the tempo
        lane's own drag-cancel handler."""
        if event.key() == Qt.Key.Key_Escape:
            self.deselect_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

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
