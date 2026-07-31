"""Trackpad spike: what does a Mac trackpad actually send to a
QGraphicsView, and how do the scrollbars behave?

We are replacing the stage's gesture set — pinch should zoom, two-finger
scroll should move the view, and click-and-drag panning goes away. Four
things need measuring before any of that is written:

1. Does a pinch arrive as a QNativeGestureEvent with
   Qt.NativeGestureType.ZoomNativeGesture, and does it land on the view
   or on the viewport? What value() does one step carry?
2. Does the same pinch ALSO produce wheelEvent calls? If it does, a
   naive "wheel scrolls, pinch zooms" split would both scroll and zoom
   from one gesture.
3. Is SH_ScrollBar_Transient true here? If it is, Qt's own scrollbars
   already overlay the viewport and fade out on their own, which is
   exactly the behaviour we want and nothing needs building.
4. Does the default super().wheelEvent() scroll BOTH axes from
   pixelDelta, and does it wake the transient bars up?

This one needs a real window and a real trackpad, so it is NOT offscreen
and cannot be automated.

Run: python spikes/stage_gestures.py
Then, over the grey box: pinch out, pinch in, two-finger scroll up/down,
two-finger scroll left/right, Cmd+scroll. Read the log. Ctrl+C to quit.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, QRectF, Qt                  # noqa: E402
from PySide6.QtGui import QBrush, QColor                       # noqa: E402
from PySide6.QtWidgets import (                                # noqa: E402
    QApplication, QGraphicsScene, QGraphicsView, QStyle,
)


class ProbeView(QGraphicsView):
    """Logs every gesture and wheel event, changing nothing."""

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self._wheels = 0
        self._gestures = 0

    def viewportEvent(self, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.NativeGesture:
            self._gestures += 1
            print(f"  [viewport] NativeGesture #{self._gestures} "
                  f"type={event.gestureType()} value={event.value():+.5f} "
                  f"pos={event.position().toTuple()} "
                  f"fingers={event.fingerCount()}")
        return super().viewportEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.NativeGesture:
            print(f"  [view]     NativeGesture type={event.gestureType()}")
        return super().event(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        self._wheels += 1
        hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
        before = (hbar.value(), vbar.value())
        mods = event.modifiers()
        print(f"  [wheel] #{self._wheels} "
              f"pixel={event.pixelDelta().toTuple()} "
              f"angle={event.angleDelta().toTuple()} "
              f"phase={event.phase()} "
              f"ctrl={bool(mods & Qt.KeyboardModifier.ControlModifier)} "
              f"meta={bool(mods & Qt.KeyboardModifier.MetaModifier)}")
        # question 4: hand it to Qt and see which bars moved
        super().wheelEvent(event)
        after = (hbar.value(), vbar.value())
        if after != before:
            print(f"          super() scrolled h:{before[0]}->{after[0]} "
                  f"v:{before[1]}->{after[1]}")
        else:
            print("          super() scrolled nothing")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._report_geometry("resize")

    def _report_geometry(self, why: str) -> None:
        hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
        print(f"  [{why}] view={self.width()}x{self.height()} "
              f"viewport={self.viewport().width()}x{self.viewport().height()} "
              f"vbar visible={vbar.isVisible()} width={vbar.width()} "
              f"hbar visible={hbar.isVisible()} height={hbar.height()}")


def main() -> None:
    app = QApplication(sys.argv)

    style = app.style()
    transient = style.styleHint(QStyle.StyleHint.SH_ScrollBar_Transient)
    print(f"style = {style.objectName()!r}")
    print(f"SH_ScrollBar_Transient = {bool(transient)}   "
          "(True = Qt's bars already overlay and fade by themselves)")
    print(f"startDragDistance = {app.startDragDistance()} px")
    print()

    scene = QGraphicsScene()
    # a scene much larger than the window, so scrollbars are needed
    scene.setSceneRect(QRectF(0, 0, 2000, 2000))
    scene.addRect(QRectF(0, 0, 2000, 2000), brush=QBrush(QColor("#cccccc")))
    for x in range(0, 2000, 100):
        for y in range(0, 2000, 100):
            scene.addRect(QRectF(x + 40, y + 40, 20, 20),
                          brush=QBrush(QColor("#333333")))

    view = ProbeView(scene)
    view.setTransformationAnchor(
        QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    view.setWindowTitle("trackpad spike — pinch and scroll over me")
    view.resize(600, 500)
    view.show()
    view._report_geometry("startup")
    print("\nNow pinch / scroll over the window. Ctrl+C in the terminal "
          "to quit.\n")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
