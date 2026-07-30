"""StageView: the paged score at the score's own aspect ratio.

Letterboxing is fitInView(sceneRect, KeepAspectRatio) against a dark
view background — the white page rect in each scene is the "screen".
Fit mode re-letterboxes on every resize; zooming (anchored under the
cursor) leaves fit mode until the Fit action restores it.

Navigation is the ordinary desktop set (ruling 2026-07-30, replacing the
M2 gesture set): pinch zooms, two-finger scroll moves the view, and
Cmd/Ctrl + wheel zooms so a plain mouse can zoom too. There is no
click-and-drag panning, so the cursor over the page is the plain arrow.
Qt's own scrollbars stay off — they would reserve space and shove the
score sideways whenever they appeared — and `TransientScrollbars` paints
a hint that fades instead.

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

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

from scoreanim.core.editing import COARSE_NUDGE, NUDGE_STEP
from scoreanim.ui.stage_scrollbars import TransientScrollbars

_LETTERBOX = QColor("#3a3a3a")
# Arrow key → unit direction (M3.2). Page y grows downward, as in SVG.
_ARROW_KEYS = {Qt.Key.Key_Left: (-1.0, 0.0), Qt.Key.Key_Right: (1.0, 0.0),
               Qt.Key.Key_Up: (0.0, -1.0), Qt.Key.Key_Down: (0.0, 1.0)}
_ZOOM_MIN = 0.05
_ZOOM_MAX = 40.0
# Same zoom CURVE as the timeline views (ui/app_state.apply_wheel — keep
# the numbers in step), but a different trigger on purpose: there a bare
# vertical scroll zooms the time axis, here it scrolls the page and zoom
# needs a pinch or Cmd/Ctrl. One wheel notch (≈40 px) = ×1.1.
_ZOOM_PER_PIXEL = math.log(1.1) / 40.0
_PIXELS_PER_NOTCH = 40.0


def clamped_factor(factor: float, current: float) -> float:
    """Trim a zoom step so it cannot leave the [_ZOOM_MIN, _ZOOM_MAX]
    range, and never moves AGAINST the gesture.

    A fit scale can legitimately sit below _ZOOM_MIN (a big score in a
    small window), so zooming out from there has to hold still rather
    than snap upward into range. Pure, so the limits can be tested
    without a view."""
    if factor < 1.0:
        return max(factor, min(1.0, _ZOOM_MIN / current))
    return min(factor, max(1.0, _ZOOM_MAX / current))


class StageView(QGraphicsView):
    """Selection gesture (M2.3, re-argued 2026-07-30): a click selects.

    The view watches the press/release pair itself and calls it a CLICK
    when the pointer moved less than QApplication.startDragDistance().
    That threshold used to be there because a longer drag was a pan;
    dragging no longer moves the view, so it is now simply a guard — a
    sloppy hand should not change the selection. A drag that starts on
    the selected element's own ink nudges it instead (see nudge_probe);
    every other drag does nothing at all."""

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

    # M3.2 drag-to-nudge. Most drags on the stage do nothing, so the
    # view asks `nudge_probe` at press time whether this particular
    # press should move an element. The probe is set by the window; the
    # view itself knows nothing about selection, scenes, or which kinds
    # are nudgeable.
    drag_started = Signal(QPointF, object)   # (scene pos, scene)
    drag_moved = Signal(QPointF)             # cumulative scene delta
    drag_finished = Signal(QPointF)          # cumulative scene delta
    nudge_key = Signal(float, float)         # arrow keys, in page units

    def __init__(self) -> None:
        super().__init__()
        self.setRenderHints(QPainter.RenderHint.Antialiasing
                            | QPainter.RenderHint.TextAntialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(_LETTERBOX)
        # No drag mode at all: dragging never moves the view, so Qt
        # leaves the plain arrow cursor over the page.
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # Qt's scrollbars reserve space, so appearing mid-gesture would
        # shift the score; scrolling works with them off (the range
        # stays live) and TransientScrollbars paints the hint instead.
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scrollbars = TransientScrollbars(self)
        self._fit_mode = True
        self._band: QRectF | None = None     # masked region (the system)
        self._frame: QRectF | None = None    # fitted region (page-sized)
        self._press_pos = None               # viewport px, for click detect
        self.nudge_probe = None              # set by the window (M3.2)
        self._drag_origin: QPointF | None = None   # scene pos of the press
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
            scene_pos = self.mapToScene(self._press_pos)
            # a press on a nudgeable element turns this drag into a move
            # for the rest of the gesture; every other drag does nothing
            if (self.scene() is not None and self.in_band(scene_pos)
                    and self.nudge_probe is not None
                    and self.nudge_probe(scene_pos, self.scene())):
                self._drag_origin = scene_pos
                self.drag_started.emit(scene_pos, self.scene())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None:
            delta = self.mapToScene(event.position().toPoint()) \
                - self._drag_origin
            self.drag_moved.emit(delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None:
            origin, self._drag_origin = self._drag_origin, None
            self._press_pos = None
            delta = self.mapToScene(event.position().toPoint()) - origin
            self.drag_finished.emit(delta)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        press, self._press_pos = self._press_pos, None
        if press is None or event.button() != Qt.MouseButton.LeftButton:
            return
        moved = (event.position().toPoint() - press).manhattanLength()
        if moved > QApplication.startDragDistance():
            return                        # a drag, not a click: do nothing
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
        # arrow keys nudge the selection (M3.2); Shift is the coarse
        # step. The controller decides whether anything is nudgeable —
        # the view only reports the direction and the modifier.
        step = _ARROW_KEYS.get(event.key())
        if step is not None:
            coarse = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            scale = COARSE_NUDGE if coarse else NUDGE_STEP
            self.nudge_key.emit(step[0] * scale, step[1] * scale)
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        if self._fit_mode:
            self._fit()

    # -- zoom and scroll ---------------------------------------------------

    def zoom_by(self, factor: float) -> None:
        """Zoom about the cursor and leave fit mode.

        Every zoom path goes through here: the pinch gesture, Cmd/Ctrl +
        wheel, and the tests. Zooming is a change to the VIEW transform,
        never to the items — `RevealPathItem` caches a scene-space
        inverse transform and would go stale if items scaled."""
        factor = clamped_factor(factor, self.transform().m11())
        if factor == 1.0:
            return
        self._fit_mode = False
        self.scale(factor, factor)
        self._scrollbars.poke()

    def scroll_by(self, dx: float, dy: float) -> None:
        """Move the view by a delta in device pixels."""
        hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
        before = (hbar.value(), vbar.value())
        hbar.setValue(hbar.value() - round(dx))
        vbar.setValue(vbar.value() - round(dy))
        if (hbar.value(), vbar.value()) != before:
            self._scrollbars.poke()

    def wheelEvent(self, event) -> None:  # noqa: N802
        """Cmd/Ctrl + wheel zooms; a bare wheel or two-finger scroll
        moves the view on both axes.

        Trackpads report pixel-precise deltas already corrected for the
        system's natural-scroll setting; a classic wheel reports angle
        notches instead.

        Scrolling does nothing while fitted, which is the point of being
        fitted: the frame is exactly in the window. Paged mode has no
        slack to scroll into anyway, but SYSTEM mode does — its scene
        rect is deliberately taller than the framed band (show_system_
        band) — and a stray two-finger scroll must not slide the framed
        system away into the letterbox."""
        pixel = event.pixelDelta()
        if not pixel.isNull():
            dx, dy = float(pixel.x()), float(pixel.y())
        else:
            angle = event.angleDelta()
            dx = angle.x() / 120.0 * _PIXELS_PER_NOTCH
            dy = angle.y() / 120.0 * _PIXELS_PER_NOTCH
        mods = event.modifiers()
        zooming = bool(mods & (Qt.KeyboardModifier.ControlModifier
                               | Qt.KeyboardModifier.MetaModifier))
        if zooming:
            if dy:
                self.zoom_by(math.exp(dy * _ZOOM_PER_PIXEL))
        elif (dx or dy) and not self._fit_mode:
            self.scroll_by(dx, dy)
        event.accept()

    def viewportEvent(self, event) -> bool:  # noqa: N802
        """Pinch to zoom. macOS delivers it as a native gesture on the
        viewport, with `value()` as the incremental scale change for that
        step — positive when the fingers spread, so spreading zooms in.
        `spikes/stage_gestures.py` logs the raw stream if the feel ever
        needs re-checking on other hardware."""
        if event.type() == QEvent.Type.NativeGesture:
            if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                self.zoom_by(1.0 + event.value())
                return True
        return super().viewportEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        """The scene, then the fading scroll indicators on top.

        A separate painter on the viewport, in device pixels — unlike
        drawForeground, which paints in scene coordinates and belongs to
        the system-band mask."""
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        self._scrollbars.paint(painter)
        painter.end()
