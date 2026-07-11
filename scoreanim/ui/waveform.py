"""WaveformView: rendered peaks over the shared time axis (PHASES 4.1).

Observes AppState only (ARCHITECTURE §7) — repaints on axis/peaks/
playhead changes, emits ``request_seek`` on click; it knows nothing of
the tempo lane or the controller. The peak image is cached as a QPixmap
rebuilt only when the axis window, the peak data, or the widget size
change; the per-frame overlay (playhead, tap markers) is a few lines.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSizePolicy, QWidget

from scoreanim.core.audio import column_extents
from scoreanim.core.project import ApplyTaps, RemoveTapSession
from scoreanim.core.timing.taps import (TapSession, derive_tempo_events,
                                        lock_to_taps)
from scoreanim.ui.app_state import AppState, apply_wheel

_BG = QColor("#1d1f24")
_PEAK = QColor("#4f7fb5")
_RMS = QColor("#7fa8d4")
_MIDLINE = QColor("#33363d")
_PLAYHEAD = QColor("#e8b34a")
_TAP = QColor("#5fd47f")


class WaveformView(QWidget):
    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._pixmap: QPixmap | None = None
        self._pan_anchor: tuple[float, float] | None = None   # (x, t0)
        self.setMinimumHeight(70)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)
        app_state.axis.changed.connect(self._invalidate)
        app_state.peaks_changed.connect(self._invalidate)
        app_state.playhead_changed.connect(lambda _t: self.update())
        app_state.document_changed.connect(self.update)   # tap markers

    def sizeHint(self):  # noqa: N802 (Qt override)
        hint = super().sizeHint()
        hint.setHeight(110)
        return hint

    def _invalidate(self) -> None:
        self._pixmap = None
        self.update()

    # -- painting -----------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        if (self._pixmap is None
                or self._pixmap.deviceIndependentSize().toSize()
                != self.size()):
            self._pixmap = self._render_peaks()
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        self._draw_overlay(painter)
        painter.end()

    def _render_peaks(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        pixmap = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(_BG)
        axis = self._state.axis
        w, h = self.width(), self.height()
        painter = QPainter(pixmap)
        mid = h / 2
        painter.setPen(QPen(_MIDLINE, 1))
        painter.drawLine(QPointF(0, mid), QPointF(w, mid))
        cache = self._state.peaks
        if cache is not None and w > 0:
            cols = column_extents(cache, axis.t0, axis.t1, w)
            half = mid - 2.0
            peak_pen = QPen(_PEAK, 1)
            rms_pen = QPen(_RMS, 1)
            for x in range(w):
                lo, hi, rms = cols[x]
                if lo == 0.0 and hi == 0.0:
                    continue
                painter.setPen(peak_pen)
                painter.drawLine(QPointF(x + 0.5, mid - hi * half),
                                 QPointF(x + 0.5, mid - lo * half))
                if rms > 0.0:
                    painter.setPen(rms_pen)
                    painter.drawLine(QPointF(x + 0.5, mid - rms * half),
                                     QPointF(x + 0.5, mid + rms * half))
        painter.end()
        return pixmap

    def _draw_overlay(self, painter: QPainter) -> None:
        axis = self._state.axis
        w, h = self.width(), self.height()
        for session in self._state.doc.timing.tap_sessions:
            painter.setPen(QPen(_TAP, 1))
            for tap in session.taps:
                x = axis.x_of(tap.seconds, w)
                if 0 <= x <= w:
                    painter.drawLine(QPointF(x, h * 0.78), QPointF(x, h))
        x = axis.x_of(self._state.playhead, w)
        if 0 <= x <= w:
            painter.setPen(QPen(_PLAYHEAD, 1))
            painter.drawLine(QPointF(x, 0), QPointF(x, h))

    # -- interaction ----------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        axis = self._state.axis
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._pan_anchor = (event.position().x(), axis.t0)
            else:
                self._seek_to(event.position().x())
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._pan_anchor = (event.position().x(), axis.t0)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        axis = self._state.axis
        if self._pan_anchor is not None:
            x0, t0 = self._pan_anchor
            dt = (x0 - event.position().x()) / self.width() * axis.span
            axis.set_visible(t0 + dt, t0 + dt + axis.span)
        elif event.buttons() & Qt.MouseButton.LeftButton:
            self._seek_to(event.position().x())

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802
        self._pan_anchor = None

    def wheelEvent(self, event) -> None:  # noqa: N802
        apply_wheel(self._state.axis, event, self.width())

    def _seek_to(self, x: float) -> None:
        axis = self._state.axis
        t = min(max(axis.t_of(x, self.width()), 0.0), axis.duration)
        self._state.request_seek(t)

    # -- tap-session context menu (lock to taps, PHASES 4.3) ---------------------

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        t = self._state.axis.t_of(event.pos().x(), self.width())
        hit = self._session_at(t)
        if hit is None:
            return
        index, session = hit
        menu = QMenu(self)
        lock = menu.addAction(
            f"Lock tempo to taps ({len(session.taps)} anchors)")
        derive = menu.addAction("Re-derive smoothed tempo")
        remove = menu.addAction("Remove tap markers")
        chosen = menu.exec(event.globalPos())
        if chosen is lock:
            self._apply(session, lock_to_taps(session), "lock")
        elif chosen is derive:
            self._apply(session, derive_tempo_events(session), "derive")
        elif chosen is remove:
            self._state.execute(RemoveTapSession(index))

    def _session_at(self, t: float) -> tuple[int, TapSession] | None:
        for index, session in enumerate(
                self._state.doc.timing.tap_sessions):
            if session.taps[0].seconds - 0.5 <= t \
                    <= session.taps[-1].seconds + 0.5:
                return index, session
        return None

    def _apply(self, session: TapSession, derivation, mode: str) -> None:
        self._state.execute(ApplyTaps(
            session, derivation.events,
            (derivation.first_beat, derivation.last_beat), mode))
