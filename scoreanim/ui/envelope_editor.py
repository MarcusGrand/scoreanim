"""EnvelopeEditor: the picture of an envelope, with handles you drag.

The classic synthesizer picture. Time runs left to right across the
span the shape plays over, level runs bottom to top, and the curve is
drawn by SAMPLING the envelope that actually plays — so what the user
shapes here and what the score does are the same object, easings and
all.

Nothing in here belongs to one effect. It takes an `EnvelopeSpec` in
and hands one back out; which document keys those six values live in is
the caller's business, which is what lets a second effect grow an
envelope later without touching this file.

The gesture is the live field's contract in mouse form (PATTERNS, "a
number field previews as you type"): every mouse-move of a drag emits
`changed`, so the score responds while the handle is held, and the
release emits exactly one `committed`, which is the one undo entry. The
caller turns a spec into a command and owns the no-op guard — the same
`edit(value) -> Command | None` split, so a preview and a commit can
never ask for different things.

`set_spec` is ignored while a drag is live, for the reason
`LiveField.resync` skips its `setValue`: a preview comes straight back
as a resync, and it must not rewrite what the hand is holding.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QPen, QPolygonF)
from PySide6.QtWidgets import QSizePolicy, QWidget

from scoreanim.core.animation import EnvelopeSpec, spec_envelope
from scoreanim.core.editing import Box, Handle, drag, handle_at, handle_points
from scoreanim.ui.theme import palette as theme

# The canvas sits in a panel about 250 px wide. Room for the labels
# under the curve, and a little air around it.
_PAD = 10.0
_LABELS = 16.0                   # the strip under the box for the per cents
_HANDLE = 3.5                    # half a handle square's side
_GRAB = 7.0                      # how close a press has to be to take one
_MIN_HEIGHT = 130

# Which way each handle moves, said with the pointer.
_CURSORS = {
    Handle.ATTACK: Qt.CursorShape.SizeHorCursor,
    Handle.RELEASE: Qt.CursorShape.SizeHorCursor,
    Handle.SUSTAIN: Qt.CursorShape.SizeVerCursor,
    Handle.SWELL: Qt.CursorShape.SizeAllCursor,
}


class EnvelopeEditor(QWidget):
    """Draws one `EnvelopeSpec` and edits it by dragging."""

    changed = Signal(object)     # an EnvelopeSpec, on every move of a drag
    committed = Signal(object)   # an EnvelopeSpec, once, on release

    def __init__(self, spec: EnvelopeSpec,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
        self._drag: Handle | None = None
        self.setMinimumHeight(_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # -- what it is showing ---------------------------------------------------

    @property
    def spec(self) -> EnvelopeSpec:
        return self._spec

    def dragging(self) -> bool:
        """A handle is being held — the caller's "am I previewing"."""
        return self._drag is not None

    def set_spec(self, spec: EnvelopeSpec) -> None:
        """Show what the document says, unless a drag owns the widget."""
        if self.dragging() or spec == self._spec:
            return
        self._spec = spec
        self.update()

    def box(self) -> Box:
        """The rectangle the curve is drawn in."""
        rect = self.rect()
        return Box(x=_PAD, y=_PAD, w=max(0.0, rect.width() - 2.0 * _PAD),
                   h=max(0.0, rect.height() - 2.0 * _PAD - _LABELS))

    # -- the gesture ----------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() is not Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        self._drag = handle_at(self._spec, self.box(), pos.x(), pos.y(), _GRAB)
        if self._drag is not None:
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        if self._drag is None:
            over = handle_at(self._spec, self.box(), pos.x(), pos.y(), _GRAB)
            # the cursor says which way the handle under it moves
            self.setCursor(_CURSORS.get(over, Qt.CursorShape.ArrowCursor))
            return
        moved = drag(self._spec, self._drag, self.box(), pos.x(), pos.y())
        event.accept()
        if moved == self._spec:
            return                       # inside the clamp: nothing to say
        self._spec = moved
        self.update()
        self.changed.emit(moved)

    def mouseReleaseEvent(self, event) -> None:
        """One drag, one `committed` — even when the handle ended up
        back where it started. The caller's no-op guard is what decides
        whether that is an edit, exactly as it does for a typed field."""
        if self._drag is None:
            return
        self._drag = None
        event.accept()
        self.committed.emit(self._spec)

    # -- the picture ----------------------------------------------------------

    def paintEvent(self, _event) -> None:
        box = self.box()
        if box.w <= 0.0 or box.h <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        frame = QRectF(box.x, box.y, box.w, box.h)
        painter.fillRect(frame, palette.base())
        painter.setPen(QPen(palette.mid().color(), 1.0))
        painter.drawRect(frame)

        curve = self._curve(box)
        # the curve is content, not a selection: it takes the theme's
        # accent rather than the palette's quiet highlight (ui/theme)
        accent = QColor(theme.ACCENT)
        under = _faded(accent, 70)
        area = QPolygonF(curve + [QPointF(box.x + box.w, box.y + box.h),
                                  QPointF(box.x, box.y + box.h)])
        path = QPainterPath()
        path.addPolygon(area)
        painter.fillPath(path, under)
        painter.setPen(QPen(accent, 1.6))
        painter.drawPolyline(QPolygonF(curve))

        self._paint_handles(painter, box, accent)
        self._paint_labels(painter, box)
        painter.end()

    def _curve(self, box: Box) -> list[QPointF]:
        """The envelope that plays, sampled once per pixel across the
        box — so the drawn easings are the played ones, not a guess at
        them."""
        envelope = spec_envelope(self._spec, 1.0, 1.0)
        points = []
        if self._spec.attack <= 0.0:
            # Nothing to rise over: the level is up AT the trigger, and
            # the picture says so with the step it really is.
            points.append(QPointF(box.x, box.y + box.h))
        for step in range(int(box.w) + 1):
            frac = step / box.w
            level = envelope.value_at(frac)
            points.append(QPointF(box.x + step, box.y + (1.0 - level) * box.h))
        return points

    def _paint_handles(self, painter: QPainter, box: Box,
                       accent: QColor) -> None:
        painter.setPen(QPen(accent.darker(140), 1.0))
        painter.setBrush(accent)
        for handle, (x, y) in handle_points(self._spec, box).items():
            if handle is Handle.SUSTAIN:
                continue             # the whole held line is the handle
            painter.drawRect(QRectF(x - _HANDLE, y - _HANDLE,
                                    2.0 * _HANDLE, 2.0 * _HANDLE))
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_labels(self, painter: QPainter, box: Box) -> None:
        """Per cents under the two time handles, and the held level
        beside the line it belongs to."""
        font = painter.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 2.0))
        painter.setFont(font)
        painter.setPen(self.palette().windowText().color())
        metrics = painter.fontMetrics()
        points = handle_points(self._spec, box)
        baseline = box.y + box.h + _LABELS - 3.0
        attack = f"{round(self._spec.attack * 100)} %"
        release = f"{round(self._spec.release * 100)} %"
        left = _centred(points[Handle.ATTACK][0], attack, metrics, box)
        right = _centred(points[Handle.RELEASE][0], release, metrics, box)
        if left + metrics.horizontalAdvance(attack) + 4.0 > right:
            # The two handles have met — a full release starts where a
            # zero attack ends. Send each label to its own end rather
            # than printing them over one another.
            left = box.x
            right = box.x + box.w - metrics.horizontalAdvance(release)
        painter.drawText(QPointF(left, baseline), attack)
        painter.drawText(QPointF(right, baseline), release)
        x, y = points[Handle.SUSTAIN]
        held = f"{round(self._spec.sustain * 100)} %"
        away = metrics.height() if self._spec.sustain > 0.5 else -4.0
        painter.drawText(QPointF(_centred(x, held, metrics, box), y + away),
                         held)


def _centred(x: float, text: str, metrics, box: Box) -> float:
    """Where a label starts to sit under the handle it belongs to —
    kept inside the box, so a handle at either edge still has its number
    written where it can be read."""
    width = metrics.horizontalAdvance(text)
    return min(max(x - width / 2.0, box.x), box.x + box.w - width)


def _faded(color: QColor, alpha: int) -> QColor:
    """The same colour, see-through — what fills the area under the
    curve without hiding the box's own edge."""
    faded = QColor(color)
    faded.setAlpha(alpha)
    return faded
