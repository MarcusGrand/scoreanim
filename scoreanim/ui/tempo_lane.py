"""TempoLaneView: tempo events as draggable points over the shared time
axis (PHASES 4.2).

Observes AppState only — the same axis object as the waveform, so the two
views scroll and zoom together without knowing of each other. Every
gesture is exactly one undoable command: tempo drags preview against the
committed document and commit on release (see ui/app_state.py); clicks,
double-clicks and the context menu execute one-shot commands.

Swing does not live here (ruling 2026-07-11): v1 swing is one global
ratio set numerically on the transport bar (ui/main_window.py,
SetGlobalSwing); per-region authoring returns later (BACKLOG 7).

x ⇄ beat mapping goes through the document's own TempoMap (beat →
seconds → axis x). During a tempo drag the PRE-DRAG committed map does
the converting, so the mapping doesn't slide under the cursor while the
preview retimes everything else live.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QInputDialog, QMenu, QSizePolicy, QWidget

from scoreanim.core.project import (AddTempoEvent, MoveTempoEvent,
                                    RemoveTempoEvent)
from scoreanim.core.score.identity import Beats
from scoreanim.core.timing import TempoMap
from scoreanim.ui.app_state import AppState, apply_wheel

_BG = QColor("#1d1f24")
_GRID = QColor("#33363d")
_GRID_TEXT = QColor("#8a8f99")
_LINE = QColor("#c46a6a")
_DOT = QColor("#e08585")
_DOT_SELECTED = QColor("#ffd27f")
_PLAYHEAD = QColor("#e8b34a")

_HIT_PX = 7.0                    # dot hit radius
_SNAP_BEATS = 0.5                # drag/add snap (Alt = free)
_MIN_GAP_BEATS = 0.25            # events may not collide while dragging
_BPM_MIN, _BPM_MAX = 20.0, 400.0
_TOP_PAD = 16                    # measure-number strip
_BOTTOM_PAD = 6


@dataclass
class _Drag:
    position: Beats              # identifies the event in the committed doc
    tempo_map: TempoMap          # pre-drag map: stable x → beat conversion
    lo: float                    # frozen bpm range for stable y mapping
    hi: float
    last_cmd: MoveTempoEvent | None = None


class TempoLaneView(QWidget):
    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._map = TempoMap(list(app_state.doc.timing.tempo_events))
        self._drag: _Drag | None = None
        self._selected: Beats | None = None
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        app_state.axis.changed.connect(self.update)
        app_state.document_changed.connect(self._on_document_changed)
        app_state.playhead_changed.connect(lambda _t: self.update())

    def sizeHint(self):  # noqa: N802
        hint = super().sizeHint()
        hint.setHeight(130)
        return hint

    def _on_document_changed(self) -> None:
        self._map = TempoMap(list(self._state.doc.timing.tempo_events))
        if self._selected is not None and not any(
                e.position == self._selected
                for e in self._state.doc.timing.tempo_events):
            self._selected = None
        self.update()

    # -- coordinate mapping ---------------------------------------------------

    def _x_of_beat(self, beat: Beats, tempo_map: TempoMap | None = None
                   ) -> float:
        m = tempo_map or self._map
        t = self._state.doc.timing.offset_seconds + m.seconds_at(beat)
        return self._state.axis.x_of(t, self.width())

    def _beat_of_x(self, x: float, tempo_map: TempoMap | None = None
                   ) -> Beats:
        m = tempo_map or self._map
        t = self._state.axis.t_of(x, self.width())
        return m.beats_at(max(0.0, t - self._state.doc.timing.offset_seconds))

    def _bpm_range(self) -> tuple[float, float]:
        if self._drag is not None:
            return self._drag.lo, self._drag.hi
        bpms = [e.bpm for e in self._state.doc.timing.tempo_events]
        lo = min(60.0, min(bpms) - 15.0)
        hi = max(160.0, max(bpms) + 15.0)
        return lo, hi

    def _y_of_bpm(self, bpm: float) -> float:
        lo, hi = self._bpm_range()
        h = self.height() - _TOP_PAD - _BOTTOM_PAD
        return _TOP_PAD + (hi - bpm) / (hi - lo) * h

    def _bpm_of_y(self, y: float) -> float:
        lo, hi = self._bpm_range()
        h = self.height() - _TOP_PAD - _BOTTOM_PAD
        bpm = hi - (y - _TOP_PAD) / h * (hi - lo)
        return min(max(bpm, _BPM_MIN), _BPM_MAX)

    # -- painting ---------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), _BG)
        w, h = self.width(), self.height()
        self._draw_measure_grid(painter, w, h)
        self._draw_tempo(painter, w)
        x = self._state.axis.x_of(self._state.playhead, w)
        if 0 <= x <= w:
            painter.setPen(QPen(_PLAYHEAD, 1))
            painter.drawLine(QPointF(x, 0), QPointF(x, h))
        painter.end()

    def _draw_measure_grid(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(QPen(_GRID, 1))
        xs = []
        for m in self._state.measures:
            x = self._x_of_beat(m.start)
            if -50 <= x <= w + 50:
                painter.drawLine(QPointF(x, _TOP_PAD), QPointF(x, h))
                xs.append((x, m.number))
        painter.setPen(_GRID_TEXT)
        last_label_x = -1e9
        for x, number in xs:
            if x - last_label_x >= 28:           # avoid label pile-up
                painter.drawText(QPointF(x + 2, _TOP_PAD - 4), f"m{number}")
                last_label_x = x

    def _draw_tempo(self, painter: QPainter, w: int) -> None:
        events = self._state.doc.timing.tempo_events
        painter.setPen(QPen(_LINE, 2))
        xs = [self._x_of_beat(e.position) for e in events]
        for i, event in enumerate(events):
            y = self._y_of_bpm(event.bpm)
            x0 = xs[i] if i > 0 else min(xs[i], 0.0)
            x1 = xs[i + 1] if i + 1 < len(events) else float(w)
            painter.drawLine(QPointF(x0, y), QPointF(x1, y))
            if i + 1 < len(events):
                painter.drawLine(QPointF(x1, y),
                                 QPointF(x1, self._y_of_bpm(events[i + 1].bpm)))
        for event, x in zip(events, xs):
            y = self._y_of_bpm(event.bpm)
            selected = event.position == self._selected
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_DOT_SELECTED if selected else _DOT)
            painter.drawEllipse(QPointF(x, y), 4.5, 4.5)
            if selected or self._drag is not None \
                    and event.position == self._drag.position:
                painter.setPen(_GRID_TEXT)
                painter.drawText(QPointF(x + 7, y - 6),
                                 f"{event.bpm:.1f} @ {event.position:g}")

    # -- interaction --------------------------------------------------------------

    def _event_at(self, pos: QPointF):
        for event in self._state.doc.timing.tempo_events:
            x = self._x_of_beat(event.position)
            y = self._y_of_bpm(event.bpm)
            if (pos.x() - x) ** 2 + (pos.y() - y) ** 2 <= _HIT_PX ** 2:
                return event
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        hit = self._event_at(pos)
        if event.button() == Qt.MouseButton.LeftButton:
            if hit is not None:
                self._selected = hit.position
                lo, hi = self._bpm_range()
                self._drag = _Drag(position=hit.position,
                                   tempo_map=self._map, lo=lo, hi=hi)
            else:
                self._selected = None
                t = self._state.axis.t_of(pos.x(), self.width())
                self._state.request_seek(
                    min(max(t, 0.0), self._state.axis.duration))
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            if hit is not None:
                self._selected = hit.position
                self.update()
                self._context_menu(hit, event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is None:
            return
        drag = self._drag
        beat = self._beat_of_x(event.position().x(), drag.tempo_map)
        if not event.modifiers() & Qt.KeyboardModifier.AltModifier:
            beat = round(beat / _SNAP_BEATS) * _SNAP_BEATS
        beat = self._clamp_between_neighbors(beat, drag)
        bpm = self._bpm_of_y(event.position().y())
        cmd = MoveTempoEvent(drag.position, beat, bpm)
        drag.last_cmd = cmd
        self._selected = beat                    # follows the preview dot
        self._state.preview(cmd)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag is None or event.button() != Qt.MouseButton.LeftButton:
            return
        cmd, self._drag = self._drag.last_cmd, None
        if cmd is None:                          # click without movement
            self._state.cancel_preview()
        else:
            self._selected = cmd.new_position
            self._state.commit(cmd)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton \
                or self._event_at(event.position()) is not None:
            return
        beat = self._beat_of_x(event.position().x())
        if not event.modifiers() & Qt.KeyboardModifier.AltModifier:
            beat = round(beat / _SNAP_BEATS) * _SNAP_BEATS
        bpm = round(self._bpm_of_y(event.position().y()), 1)
        if self._state.execute(AddTempoEvent(max(0.0, beat), bpm)):
            self._selected = max(0.0, beat)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and self._drag is not None:
            self._drag = None
            self._state.cancel_preview()
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) \
                and self._selected is not None and self._drag is None:
            self._state.execute(RemoveTempoEvent(self._selected))
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        apply_wheel(self._state.axis, event, self.width())

    def _clamp_between_neighbors(self, beat: Beats, drag: _Drag) -> Beats:
        # neighbors from the PRE-DRAG map: during a preview the moving
        # event already sits at its new position in state.doc and must not
        # clamp against its own ghost
        others = [e.position for e in drag.tempo_map.events
                  if e.position != drag.position]
        lo = max((p for p in others if p < beat), default=None)
        hi = min((p for p in others if p > beat), default=None)
        # collision at the exact position of another event is clamped away
        if lo is not None and beat - lo < _MIN_GAP_BEATS:
            beat = lo + _MIN_GAP_BEATS
        if hi is not None and hi - beat < _MIN_GAP_BEATS:
            beat = hi - _MIN_GAP_BEATS
        return max(0.0, beat)

    def _context_menu(self, event_hit, global_pos) -> None:
        menu = QMenu(self)
        edit = menu.addAction("Edit BPM…")
        remove = menu.addAction("Delete")
        chosen = menu.exec(global_pos)
        if chosen is edit:
            bpm, ok = QInputDialog.getDouble(
                self, "Tempo event",
                f"BPM at beat {event_hit.position:g}:",
                event_hit.bpm, _BPM_MIN, _BPM_MAX, 1)
            if ok:
                self._state.execute(MoveTempoEvent(
                    event_hit.position, event_hit.position, bpm))
        elif chosen is remove:
            self._state.execute(RemoveTempoEvent(event_hit.position))
