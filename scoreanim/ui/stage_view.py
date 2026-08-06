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
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

from scoreanim.core.editing import COARSE_NUDGE, NUDGE_STEP
from scoreanim.ui.stage_frame import StageFraming
from scoreanim.ui.stage_scrollbars import TransientScrollbars

_LETTERBOX = QColor("#3a3a3a")
# The canvas frame's own edge: light enough to read on the letterbox,
# quiet enough not to read as part of the score.
_FRAME_EDGE = QColor("#7a7a7a")
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
        self._framing = StageFraming()       # frame/band/mask geometry
        self._preview_fill: QColor | None = None   # overlay preview
        self._press_pos = None               # viewport px, for click detect
        self.nudge_probe = None              # set by the window (M3.2)
        self._drag_origin: QPointF | None = None   # scene pos of the press
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # Esc needs focus

    def set_canvas(self, canvas) -> None:
        """The document's video canvas (or None): reframe in place,
        keeping whatever page or band is showing."""
        self._framing.set_canvas(canvas)
        scene = self.scene()
        if scene is not None:
            page = scene.sceneRect()
            if self._framing.band is not None:
                self._framing.set_system_band(page, self._framing.band)
            else:
                self._framing.set_page(page)
            self.setSceneRect(self._framing.scene_rect(page))
            if self._fit_mode:
                self._fit()
        self.viewport().update()

    def set_overlay_preview(self, active: bool, color: QColor) -> None:
        """View-only composite preview: fill the frame with `color`
        (the video the overlay will sit on) behind the ink. Never
        reaches export — ruling R1 keeps frames transparent."""
        self._preview_fill = QColor(color) if active else None
        self.viewport().update()

    def show_scene(self, scene: QGraphicsScene) -> None:
        """Page flip: swap scenes, keep the current fit/zoom behavior."""
        self.setScene(scene)
        page = scene.sceneRect()
        self._framing.set_page(page)
        self.setSceneRect(self._framing.scene_rect(page))
        if self._fit_mode:
            self._fit()
        self.viewport().update()

    def show_system_band(self, scene: QGraphicsScene, band: QRectF) -> None:
        """System flip (Phase 7.4; framing revised Phase 10R): swap to
        the band's page scene and fit a PAGE-SIZED window centered
        vertically on the band — the frame keeps the page's aspect, the
        system occupies the middle at natural page width; everything
        outside the band letterboxes. A hard cut, exactly like a page
        flip (ruling R2)."""
        self.setScene(scene)
        page = scene.sceneRect()
        self._framing.set_system_band(page, band)
        self.setSceneRect(self._framing.scene_rect(page))
        if self._fit_mode:
            self._fit()
        self.viewport().update()

    def clear_band(self) -> None:
        """Back to paged framing (band mask off; the canvas stays)."""
        if self.scene() is not None:
            page = self.scene().sceneRect()
            self._framing.set_page(page)
            self.setSceneRect(self._framing.scene_rect(page))
        else:
            self._framing.band = None
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
        target = self._framing.fit_target(self.scene().sceneRect())
        if self._framing.canvas is not None:
            self._fit_canvas(target)
            return
        self.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)

    def _fit_canvas(self, frame: QRectF) -> None:
        """Fit the canvas frame so it CANNOT move between systems.

        fitInView rounds through the integer scrollbars, and how it
        rounds depends on the frame's scene position — the canvas edge
        wobbled 1–4 px between systems during playback. Three choices
        pin it: the zoom is set directly (no fitInView, no 2 px margin —
        the canvas edge IS the picture); the scroll range is one
        CONSTANT page-independent overscan rect, so Qt's origin math is
        identical for every system; and the frame is nudged a quarter
        device pixel off the integer grid (at most half a pixel against
        the band — invisible), so every rounding along the way lands
        the same side for every system."""
        vp = self.viewport().rect()
        if vp.isEmpty() or frame.isEmpty():
            return
        z = min(vp.width() / frame.width(), vp.height() / frame.height())
        frame = QRectF(frame)
        frame.translate(
            (round(frame.left() * z) + 0.25) / z - frame.left(),
            (round(frame.top() * z) + 0.25) / z - frame.top())
        self._framing.frame = frame
        page = self.scene().sceneRect()
        self.setSceneRect(page.adjusted(-frame.width(), -frame.height(),
                                        frame.width(), frame.height()))
        transform = self.transform()
        transform.setMatrix(z, 0, 0, 0, z, 0, 0, 0, 1)
        self.setTransform(transform)
        self.centerOn(frame.center())

    def drawBackground(self, painter, rect) -> None:  # noqa: N802
        """The overlay preview: the chosen video color inside the
        frame, behind the ink. The paper rect is hidden by the window
        while the preview is on, so the ink composites over this the
        way the exported overlay will over footage."""
        super().drawBackground(painter, rect)
        fill = self._preview_fill
        if fill is None or self.scene() is None:
            return
        target = self._framing.frame
        if target is None:
            target = self.scene().sceneRect()
        painter.fillRect(target.intersected(rect), fill)

    def drawForeground(self, painter, rect) -> None:  # noqa: N802
        """Letterbox masking outside the visible region (geometry in
        stage_frame.py), then the canvas frame's edge — a thin line so
        the video's boundary reads even where page and letterbox meet
        flush."""
        super().drawForeground(painter, rect)
        for strip in self._framing.mask_strips(rect):
            painter.fillRect(strip, _LETTERBOX)
        if self._framing.canvas is not None \
                and self._framing.frame is not None:
            pen = QPen(_FRAME_EDGE)
            pen.setCosmetic(True)           # 1 device px at every zoom
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._framing.frame)

    # -- selection gesture -------------------------------------------------

    def in_band(self, scene_pos: QPointF) -> bool:
        """Is this scene point inside the visible band?

        In system mode the scene under the view is the whole PAGE and the
        letterbox is painted in drawForeground, so ink from a neighbouring
        system is invisible but fully hittable. The view is the only
        object that knows the band, so it gates here and the selection
        controller stays mode-blind. Paged mode: everything is visible."""
        return self._framing.contains(scene_pos)

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
