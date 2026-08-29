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
from scoreanim.ui.stage_zoom import FIT_MARGIN, fit_scale, percent
from scoreanim.ui.theme import palette

_LETTERBOX = QColor(palette.WINDOW)
# The canvas frame's own edge: light enough to read on the letterbox,
# quiet enough not to read as part of the score.
_FRAME_EDGE = QColor(palette.DIM)
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
    # 2026-08-09: right-click opens the stage context menu. The view
    # only reports (global QPoint, scene QPointF) — the menu itself
    # lives in ui/stage_menu.py, the "view emits, controller decides"
    # contract every other gesture here follows.
    context_menu_requested = Signal(object, QPointF)
    # D2: the page changed size on screen — zoomed, fitted, or the
    # window resized under a fitted view. Carries nothing; whoever
    # cares reads `zoom_percent()`.
    zoom_changed = Signal()

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
        self._page_fill = QColor(Qt.GlobalColor.white)   # doc page color
        self._press_pos = None               # viewport px, for click detect
        self.nudge_probe = None              # set by the window (M3.2)
        # "is anything nudgeable selected right now?" — set by the
        # window too, and read only by the ShortcutOverride guard below
        self.nudge_target = None
        self.overlay_painter = None          # drawn AFTER the mask, so
        # it can render outside the system frame (the onset ruler)
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
        self.zoom_changed.emit()      # a canvas reshapes what "fit" means

    def set_overlay_preview(self, active: bool, color: QColor) -> None:
        """View-only composite preview: fill the frame with `color`
        (the video the overlay will sit on) behind the ink. Never
        reaches export — ruling R1 keeps frames transparent."""
        self._preview_fill = QColor(color) if active else None
        self.viewport().update()

    def set_page_fill(self, color: QColor) -> None:
        """The document's page background (light or dark mode) — the
        canvas frame fills with it when the overlay preview is off, so
        the box reads as one solid rectangle whatever mode shows."""
        self._page_fill = QColor(color)
        self.viewport().update()

    def _frame_fill(self) -> QColor:
        return self._preview_fill if self._preview_fill is not None \
            else self._page_fill

    def show_scene(self, scene: QGraphicsScene) -> None:
        """Page flip: swap scenes, keep the current fit/zoom behavior."""
        self.setScene(scene)
        page = scene.sceneRect()
        self._framing.set_page(page)
        self.setSceneRect(self._framing.scene_rect(page))
        if self._fit_mode:
            self._fit()
        self.viewport().update()
        self.zoom_changed.emit()      # first scene: there is a size now

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
        else:
            self.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_changed.emit()

    def fit_scale(self) -> float:
        """The scale a fit would land on right now — what `zoom_percent`
        is a percentage of. Worked out, never remembered, so it is still
        right after the window is resized under a zoomed-in view."""
        if self.scene() is None:
            return 0.0
        target = self._framing.fit_target(self.scene().sceneRect())
        viewport = self.viewport().rect()
        # the canvas path sets the scale itself and keeps no margin;
        # every other fit goes through fitInView, which keeps one
        return fit_scale(viewport.width(), viewport.height(),
                         target.width(), target.height(),
                         0.0 if self._framing.canvas is not None
                         else FIT_MARGIN)

    def zoom_percent(self) -> int:
        """How big the page is on screen, as a percentage of fitted."""
        return percent(self.transform().m11(), self.fit_scale())

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
        """The frame's own fill, behind the ink.

        With a canvas the whole frame fills — the overlay-preview color
        when the preview is on (paper hidden, so the ink composites the
        way the exported overlay will over footage), else the page
        background, so the letterbox slack beside the page belongs to
        the box instead of reading as a hole in it. Without a canvas
        only the preview fills, over the page."""
        super().drawBackground(painter, rect)
        if self.scene() is None:
            return
        frame = self._framing.frame
        if self._framing.canvas is not None and frame is not None:
            painter.fillRect(frame.intersected(rect), self._frame_fill())
        elif self._preview_fill is not None:
            target = frame if frame is not None \
                else self.scene().sceneRect()
            painter.fillRect(target.intersected(rect), self._preview_fill)

    def drawForeground(self, painter, rect) -> None:  # noqa: N802
        """The masking, then the canvas frame's edge, then the one
        overlay that must never be masked (the onset ruler renders
        outside the system frame on purpose)."""
        super().drawForeground(painter, rect)
        self._draw_mask(painter, rect)
        if self.overlay_painter is not None:
            self.overlay_painter(painter, self.scene())

    def _draw_mask(self, painter, rect) -> None:
        """No canvas: letterbox over everything outside the visible band
        (geometry in stage_frame.py). Canvas: letterbox only OUTSIDE
        the frame; inside it, a neighbor system's ink is covered with
        the frame's own fill — so the box is one still rectangle whose
        content changes, never a box that reshapes per system."""
        framing = self._framing
        if framing.canvas is None:
            for strip in framing.mask_strips(rect):
                painter.fillRect(strip, _LETTERBOX)
            return
        if framing.frame is None:
            return
        inside, outside = framing.canvas_mask(rect)
        fill = self._frame_fill()
        for strip in inside:
            painter.fillRect(strip, fill)
        for strip in outside:
            painter.fillRect(strip, _LETTERBOX)
        pen = QPen(_FRAME_EDGE)
        pen.setCosmetic(True)               # 1 device px at every zoom
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(framing.frame)

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
            # the scroll indicators get first refusal: a press on one is
            # a scroll gesture, never a click on the score under it
            if self._scrollbars.press(event.position()):
                event.accept()
                return
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
        if self._scrollbars.drag(event.position()):
            event.accept()
            return
        if self._drag_origin is not None:
            delta = self.mapToScene(event.position().toPoint()) \
                - self._drag_origin
            self.drag_moved.emit(delta)
            event.accept()
            return
        # no button down: reaching for an edge brings its bar up
        self._scrollbars.hover(event.position())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._scrollbars.release(event.position()):
            event.accept()
            return
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

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """Right-click (or the menu key): report where, decide nothing."""
        if self.scene() is None:
            return
        self.context_menu_requested.emit(
            event.globalPos(), self.mapToScene(event.pos()))
        event.accept()

    def event(self, event) -> bool:
        """Keep the arrow keys for nudging when there is something to
        nudge.

        The window binds Left and Right to seeking (`ui/seek_keys.py`),
        and Qt gives a window shortcut the key BEFORE the focused
        widget ever sees it. ShortcutOverride is the one way back: a
        widget that accepts it is saying "this key is mine", and the
        key then arrives as a normal press in `keyPressEvent` below.

        So the arrows nudge while a nudgeable object is selected, and
        seek the rest of the time. Anything the window has not asked
        for falls through untouched — this only ever accepts, never
        blocks.
        """
        if (event.type() == QEvent.Type.ShortcutOverride
                and event.key() in _ARROW_KEYS
                and self.nudge_target is not None
                and self.nudge_target() is not None):
            event.accept()
            return True
        return super().event(event)

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
        else:
            # the transform did not move, but a fit would land somewhere
            # else now, so the percentage of it did
            self.zoom_changed.emit()

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
        self.zoom_changed.emit()

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
        """Pinch to zoom, and the pointer leaving the stage.

        macOS delivers a pinch as a native gesture on the viewport, with
        `value()` as the incremental scale change for that step —
        positive when the fingers spread, so spreading zooms in.
        `spikes/stage_gestures.py` logs the raw stream if the feel ever
        needs re-checking on other hardware.

        Leave is watched here rather than in the view's own leaveEvent
        because the two are not the same moment: the zoom controls are a
        child of the VIEW sitting over the viewport, so moving onto them
        leaves the viewport while the view still has the pointer. The
        scroll indicators want the viewport's answer — that is the
        surface they are drawn on."""
        if event.type() == QEvent.Type.Leave:
            self._scrollbars.leave()
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
