"""Tempo mode: the red tempo step line with draggable tempo points.

One of the timeline lane's two modes (the other is ui/lane_ticks.py); the
host widget is ui/tempo_lane.py, which owns the time axis mapping, the
measure grid and the playhead. This module owns everything about tempo
events: the step line, the bpm y-axis, and the four gestures that edit
them.

Every gesture is exactly one undoable command: a point drag previews
against the committed document and commits on release, and clicks,
double-clicks and the context menu execute one-shot commands.

The drag holds the PRE-DRAG map, so x → beat does not slide under the
cursor while the preview retimes everything else live, and it freezes the
bpm range so the y axis stays still too.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QInputDialog, QMenu

from scoreanim.core.project import (AddTempoEvent, MoveTempoEvent,
                                    RemoveTempoEvent)
from scoreanim.core.score.identity import Beats
from scoreanim.core.timing import TempoMap
from scoreanim.ui.lane_style import (BOTTOM_PAD, BPM_MAX, BPM_MIN, GRID_TEXT,
                                     HIT_PX, TOP_PAD)

_LINE = QColor("#c46a6a")
_DOT = QColor("#e08585")
_DOT_SELECTED = QColor("#ffd27f")

_SNAP_BEATS = 0.5                # drag/add snap (Alt = free)
_MIN_GAP_BEATS = 0.25            # events may not collide while dragging


@dataclass
class _Drag:
    position: Beats              # identifies the event in the committed doc
    tempo_map: TempoMap          # pre-drag map: stable x → beat conversion
    lo: float                    # frozen bpm range for stable y mapping
    hi: float
    last_cmd: MoveTempoEvent | None = None


class TempoPointsMode:
    """Tempo events as points over the shared time axis (PHASES 4.2)."""

    def __init__(self, lane) -> None:
        self._lane = lane
        self._state = lane.state
        self._drag: _Drag | None = None
        self._selected: Beats | None = None

    # -- bpm axis ---------------------------------------------------------------

    def _bpm_range(self) -> tuple[float, float]:
        if self._drag is not None:
            return self._drag.lo, self._drag.hi
        bpms = [e.bpm for e in self._state.doc.timing.tempo_events]
        lo = min(60.0, min(bpms) - 15.0)
        hi = max(160.0, max(bpms) + 15.0)
        return lo, hi

    def _y_of_bpm(self, bpm: float) -> float:
        lo, hi = self._bpm_range()
        h = self._lane.height() - TOP_PAD - BOTTOM_PAD
        return TOP_PAD + (hi - bpm) / (hi - lo) * h

    def _bpm_of_y(self, y: float) -> float:
        lo, hi = self._bpm_range()
        h = self._lane.height() - TOP_PAD - BOTTOM_PAD
        bpm = hi - (y - TOP_PAD) / h * (hi - lo)
        return min(max(bpm, BPM_MIN), BPM_MAX)

    # -- painting ---------------------------------------------------------------

    def paint(self, painter: QPainter) -> None:
        w = self._lane.width()
        events = self._state.doc.timing.tempo_events
        painter.setPen(QPen(_LINE, 2))
        xs = [self._lane.x_of_beat(e.position) for e in events]
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
                painter.setPen(GRID_TEXT)
                painter.drawText(QPointF(x + 7, y - 6),
                                 f"{event.bpm:.1f} @ {event.position:g}")

    # -- interaction --------------------------------------------------------------

    def document_changed(self) -> None:
        if self._selected is not None and not any(
                e.position == self._selected
                for e in self._state.doc.timing.tempo_events):
            self._selected = None

    def _event_at(self, pos: QPointF):
        for event in self._state.doc.timing.tempo_events:
            x = self._lane.x_of_beat(event.position)
            y = self._y_of_bpm(event.bpm)
            if (pos.x() - x) ** 2 + (pos.y() - y) ** 2 <= HIT_PX ** 2:
                return event
        return None

    def press(self, event) -> bool:
        """True when the press hit a point; False lets the host seek."""
        hit = self._event_at(event.position())
        if hit is None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._selected = None
            return False
        if event.button() == Qt.MouseButton.LeftButton:
            self._selected = hit.position
            lo, hi = self._bpm_range()
            self._drag = _Drag(position=hit.position,
                               tempo_map=self._lane.tempo_map, lo=lo, hi=hi)
            return True
        if event.button() == Qt.MouseButton.RightButton:
            self._selected = hit.position
            self._lane.update()
            self._context_menu(hit, event.globalPosition().toPoint())
            return True
        return False

    def move(self, event) -> None:
        if self._drag is None:
            return
        drag = self._drag
        beat = self._lane.beat_of_x(event.position().x(), drag.tempo_map)
        if not event.modifiers() & Qt.KeyboardModifier.AltModifier:
            beat = round(beat / _SNAP_BEATS) * _SNAP_BEATS
        beat = self._clamp_between_neighbors(beat, drag)
        bpm = self._bpm_of_y(event.position().y())
        cmd = MoveTempoEvent(drag.position, beat, bpm)
        drag.last_cmd = cmd
        self._selected = beat                    # follows the preview dot
        self._state.preview(cmd)

    def release(self, event) -> None:
        if self._drag is None or event.button() != Qt.MouseButton.LeftButton:
            return
        cmd, self._drag = self._drag.last_cmd, None
        if cmd is None:                          # click without movement
            self._state.cancel_preview()
        else:
            self._selected = cmd.new_position
            self._state.commit(cmd)

    def double_click(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton \
                or self._event_at(event.position()) is not None:
            return False
        beat = self._lane.beat_of_x(event.position().x())
        if not event.modifiers() & Qt.KeyboardModifier.AltModifier:
            beat = round(beat / _SNAP_BEATS) * _SNAP_BEATS
        bpm = round(self._bpm_of_y(event.position().y()), 1)
        if self._state.execute(AddTempoEvent(max(0.0, beat), bpm)):
            self._selected = max(0.0, beat)
        return True

    def key(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._drag is not None:
            self._drag = None
            self._state.cancel_preview()
            return True
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) \
                and self._selected is not None and self._drag is None:
            self._state.execute(RemoveTempoEvent(self._selected))
            return True
        return False

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
        menu = QMenu(self._lane)
        edit = menu.addAction("Edit BPM…")
        remove = menu.addAction("Delete")
        chosen = menu.exec(global_pos)
        if chosen is edit:
            bpm, ok = QInputDialog.getDouble(
                self._lane, "Tempo event",
                f"BPM at beat {event_hit.position:g}:",
                event_hit.bpm, BPM_MIN, BPM_MAX, 1)
            if ok:
                self._state.execute(MoveTempoEvent(
                    event_hit.position, event_hit.position, bpm))
        elif chosen is remove:
            self._state.execute(RemoveTempoEvent(event_hit.position))
