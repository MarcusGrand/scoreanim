"""A short crossfade over a system switch (docs/SYSTEMS_MODE_REWORK.md
stage 5).

The whole transition is one picture painted over the live view. Stage 2
is what makes that enough: the frame is a fixed piece of glass and a
switch never moves it on screen, so a grab of the viewport taken just
before a switch lines up pixel for pixel with the viewport just after
it — fitted or zoomed, with a video canvas or without. Fading that grab
out over the live view IS the dissolve, and the incoming system keeps
animating underneath it the whole time.

View-level, like the mask and the framing: no scene is touched, no item
changes, the camera does not move, and export builds its own scenes and
its own renderer, so an exported frame cannot see any of this.

It runs on PLAYBACK-driven switches only (`ViewRouter.show_system`'s
`smooth` flag, which comes from the tick loop). A seek, a waveform
scrub, prev/next, the mode toggle and a load all stay hard cuts — a
dissolve on a scrub would smear, and a jump the user asked for should
look like a jump. The user can turn the whole thing off in the View
menu; hard cuts are the standard in score videos.
"""
from __future__ import annotations

from PySide6.QtCore import Property, QObject, QPropertyAnimation
from PySide6.QtGui import QPainter, QPixmap

# Long enough to read as a dissolve, short enough that it is over before
# the next beat on anything but very slow music.
CROSSFADE_MS = 150


class SystemCrossfade(QObject):
    """The outgoing system, frozen, fading out over the incoming one.

    The router calls `capture()` before the switch, the view `start()`
    after it and `paint()` from its own paintEvent. Nothing has to
    cancel it: the fade ends on its own, and a camera that moves under
    the snapshot is noticed at the next paint. Opacity is a Qt property
    driven by a QPropertyAnimation — the same idiom the scroll
    indicators fade with (ui/stage_scrollbars.py), which also means a
    test can step it with `animation.setCurrentTime` instead of waiting.
    """

    def __init__(self, view) -> None:
        super().__init__(view)
        self._view = view
        self._snapshot: QPixmap | None = None
        self._opacity = 0.0
        self._enabled = False
        # Where the camera was when the fade started. The snapshot is
        # glued to the SCREEN, so it is only true while the view holds
        # still; a zoom, a scroll or a resize under it would tear.
        self._anchor: tuple | None = None
        self.animation = QPropertyAnimation(self, b"opacity", self)
        self.animation.setDuration(CROSSFADE_MS)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.finished.connect(self.cancel)

    # -- the property the fade animates ------------------------------------

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, value: float) -> None:
        self._opacity = float(value)
        self._view.viewport().update()

    opacity = Property(float, _get_opacity, _set_opacity)

    # -- what the view and the router call ---------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """The View menu's toggle (remembered in QSettings, never the
        document). Turning it off mid-fade ends that fade at once."""
        self._enabled = bool(enabled)
        if not self._enabled:
            self.cancel()

    def is_running(self) -> bool:
        return self._snapshot is not None

    def _camera(self) -> tuple:
        """What the snapshot is true of: the zoom, the scene point at
        the viewport's corner, and the size of the window it was taken
        in. Read rather than remembered, so nothing has to announce a
        camera move for the fade to notice one."""
        view, transform = self._view, self._view.transform()
        return (transform.m11(), transform.m22(),
                view.mapToScene(0, 0).toTuple(),
                view.viewport().size().toTuple())

    def capture(self) -> None:
        """Freeze the outgoing frame. Called BEFORE anything about the
        switch moves — before the item filter hides the system that is
        leaving, which is the picture we are here to keep."""
        if not self._enabled:
            return
        self.animation.stop()
        self._snapshot = self._view.viewport().grab()

    def start(self) -> None:
        """Begin the dissolve. A no-op with nothing captured, which is
        every switch the polish does not apply to."""
        if self._snapshot is None:
            return
        self._anchor = self._camera()    # the switch has finished moving
        self._opacity = 1.0
        self.animation.start()

    def cancel(self) -> None:
        """Drop the snapshot and stop, leaving the live view alone."""
        if self._snapshot is None:
            return
        self._drop()
        self._view.viewport().update()

    def _drop(self) -> None:
        self.animation.stop()
        self._snapshot = None
        self._anchor = None
        self._opacity = 0.0

    def paint(self, painter: QPainter) -> None:
        """The frozen frame over the live one, in device pixels — the
        grab carries its own pixel ratio, so it lands at logical size at
        any DPR. Drawn under the scroll indicators, which belong to the
        view as it is now, not to the frame that is leaving.

        This is also where the fade ends early. A snapshot is only true
        of the camera it was taken with, and the cheapest way to know
        the camera has moved is to look at it while painting — no signal
        to connect, and nothing that can fire during the switch itself
        (which does move the camera, by design)."""
        if self._snapshot is None or self._opacity <= 0.0:
            return
        if self._camera() != self._anchor:
            self._drop()          # the view moved under it: cut, do not tear
            return
        painter.setOpacity(self._opacity)
        painter.drawPixmap(0, 0, self._snapshot)
        painter.setOpacity(1.0)
