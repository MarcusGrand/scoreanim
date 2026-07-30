"""Ticks mode: the grid lines are the drag handles.

Drag a barline (or a beat, at the chosen subdivision) onto the waveform
and the tempo around it retimes to suit. The red tempo line is not drawn
here — the same edit shows up as a step in tempo mode, because both modes
are two views of one set of tempo events.

Which lines hold still while you drag is the whole feel of this:

- the anchors are the nearest BARLINE OR EXISTING TEMPO POINT either
  side, not the neighbouring ticks. Neighbouring ticks would give a 1/16
  drag a few milliseconds of travel before the bpm clamp stopped it;
  barlines give every resolution the same usable range. Aligning several
  beats inside one bar still works left to right, because each drag
  leaves a tempo point behind, which the next drag then anchors on.
- ripple (or Alt, which flips whatever the button says) drops the anchor
  after the line: the tempo past it is untouched and slides along.
- the first line has no anchor before it, so dragging it is the "line the
  score up with the recording" move — it sets the offset and slides the
  whole score, exactly what the Offset field does.

Beat domains, the one thing to keep straight here: a tick is a MUSICAL
beat, while a tempo event's position is a SWING-WARPED beat. Ticks are
warped on their way to a pixel (`_x_of_tick`) and event positions are
unwarped on their way to being compared with ticks (`_anchors`).
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication

from scoreanim.core.project import AlignBeat, Command, SetOffset
from scoreanim.core.score.identity import Beats
from scoreanim.core.timing import (GridUnit, TempoMap, bpm_at, coarsened,
                                   grid_ticks, retime_bounds, swing_unwarp,
                                   swing_warp)
from scoreanim.core.timing.grid import EMPTY, GridTick, TickGrid
from scoreanim.ui.lane_style import BOTTOM_PAD, GRID_TEXT, HIT_PX, TOP_PAD
from scoreanim.ui.readouts import format_time

_BAR = QColor("#5b6472")         # barline, brighter here than the host's
_SUB = QColor("#3d424c")         # subdivision line
_SUB_STRONG = QColor("#4b5563")  # subdivision on a whole beat
_HANDLE = QColor("#7fb8e8")      # the line under the pointer, or dragging
_BPM_TEXT = QColor("#6f7681")

_SUB_TOP = 0.42                  # subdivisions start this far down the lane
_BPM_MIN_PX = 34.0               # about the text's own width: a narrower
                                 # bar gets no bpm readout
_EDGE_PX = 60.0                  # how far off-screen to still consider ticks
_EPS = 1e-6
_OFFSET_MIN, _OFFSET_MAX = -60.0, 3600.0     # the Offset field's own range


@dataclass
class _Drag:
    beat: Beats                              # musical beat being dragged
    left: Beats | None                       # anchor before; None = first line
    right: Beats | None                      # anchor after, when pinning
    tempo_map: TempoMap                      # pre-drag: stable geometry
    unit: GridUnit                           # frozen: the grid must not
                                             # change resolution mid-drag
    pinned: tuple[float, float] | None       # reachable audio seconds
    rippled: tuple[float, float] | None
    label: str
    last_cmd: Command | None = None


class TickAlignMode:
    def __init__(self, lane) -> None:
        self._lane = lane
        self._state = lane.state
        self._grid: TickGrid = EMPTY
        self._grid_key: tuple | None = None
        self._drag: _Drag | None = None
        self._hover: Beats | None = None

    # -- the grid ---------------------------------------------------------------

    def _px_per_beat(self) -> float:
        axis = self._state.axis
        doc = self._state.doc
        centre = (axis.t0 + axis.t1) / 2.0 - doc.timing.offset_seconds
        beat = self._lane.tempo_map.beats_at(max(0.0, centre))
        bpm = bpm_at(doc.timing.tempo_events, beat)
        return self._lane.width() / axis.span * 60.0 / bpm

    def _unit(self) -> GridUnit:
        """The step actually drawn — thinned when ticks would crowd, and
        frozen for the length of a drag: retiming a span changes px per
        beat, and a grid that changes resolution under the cursor reads
        as the view jumping."""
        if self._drag is not None:
            return self._drag.unit
        return coarsened(self._state.grid.unit, self._px_per_beat())

    def _ticks(self) -> TickGrid:
        unit = self._unit()
        key = (self._state.measures, unit.label)
        if key != self._grid_key:
            self._grid = grid_ticks(self._state.measures, unit)
            self._grid_key = key
        return self._grid

    def _x_of_tick(self, beat: Beats,
                   tempo_map: TempoMap | None = None) -> float:
        """A musical beat to a pixel: warp first, so the line sits where
        the beat actually sounds."""
        warped = swing_warp(beat, self._state.doc.timing.swing_regions)
        return self._lane.x_of_beat(warped, tempo_map)

    def _visible(self) -> tuple[tuple[float, GridTick], ...]:
        grid = self._ticks()
        if not grid.ticks:
            return ()
        w = self._lane.width()
        lo = self._lane.beat_of_x(-_EDGE_PX) - 1.0    # a warp shifts by < 1
        hi = self._lane.beat_of_x(w + _EDGE_PX) + 1.0
        out = []
        for tick in grid.between(lo, hi):
            x = self._x_of_tick(tick.beat)
            if -_EDGE_PX <= x <= w + _EDGE_PX:
                out.append((x, tick))
        return tuple(out)

    # -- painting ---------------------------------------------------------------

    def paint(self, painter: QPainter) -> None:
        w, h = self._lane.width(), self._lane.height()
        top = TOP_PAD + (h - TOP_PAD - BOTTOM_PAD) * _SUB_TOP
        for x, tick in self._visible():
            if tick.barline:
                # over the host's grid line: in this mode a barline is a
                # handle, so it has to read as structure, not as one more
                # tick in the row
                painter.setPen(QPen(_BAR, 1))
                painter.drawLine(QPointF(x, TOP_PAD), QPointF(x, h))
                continue
            whole = abs(tick.beat - round(tick.beat)) < _EPS
            painter.setPen(QPen(_SUB_STRONG if whole else _SUB, 1))
            painter.drawLine(QPointF(x, top), QPointF(x, h - BOTTOM_PAD))
        self._draw_bar_tempos(painter, w, h)
        handle = self._drag.beat if self._drag is not None else self._hover
        if handle is not None:
            # the LIVE map, so the highlight sits on the previewed
            # position and tracks the pointer — the pre-drag map would
            # leave it behind at the beat's old pixel
            painter.setPen(QPen(_HANDLE, 2))
            x = self._x_of_tick(handle)
            painter.drawLine(QPointF(x, TOP_PAD), QPointF(x, h))

    def _draw_bar_tempos(self, painter: QPainter, w: int, h: int) -> None:
        """Each bar's effective tempo, in place of the red line — but only
        where it CHANGES. The same number under every bar is a wall of
        noise; printing the changes makes them the thing you see."""
        painter.setPen(_BPM_TEXT)
        tempo_map = self._lane.tempo_map
        previous: float | None = None
        for measure in self._state.measures:
            end = measure.start + measure.quarter_length
            span = (tempo_map.seconds_at(end)
                    - tempo_map.seconds_at(measure.start))
            if span <= 0.0 or measure.quarter_length <= 0.0:
                continue
            bpm = 60.0 * measure.quarter_length / span
            changed = previous is None or abs(bpm - previous) > 0.05
            previous = bpm
            x = self._x_of_tick(measure.start)
            if not (changed and -20.0 <= x <= w):
                continue
            if self._x_of_tick(end) - x >= _BPM_MIN_PX:
                painter.drawText(QPointF(x + 3, h - 4), f"{bpm:.1f}")

    # -- interaction ------------------------------------------------------------

    def document_changed(self) -> None:
        pass                     # the grid cache keys on measures + unit

    def deactivate(self) -> None:
        if self._drag is not None:
            self._drag = None
            self._state.cancel_preview()
        self._hover = None
        self._lane.unsetCursor()

    def _tick_at(self, x: float) -> GridTick | None:
        best, best_dx = None, HIT_PX
        for tick_x, tick in self._visible():
            dx = abs(tick_x - x)
            if dx < best_dx:
                best, best_dx = tick, dx
        return best

    def _anchors(self) -> list[Beats]:
        """Barlines and existing tempo points, as musical beats."""
        regions = self._state.doc.timing.swing_regions
        beats = {round(m.start, 6) for m in self._state.measures}
        beats |= {round(swing_unwarp(e.position, regions), 6)
                  for e in self._state.doc.timing.tempo_events}
        return sorted(beats)

    def _bounds(self, beat: Beats, left: Beats,
                right: Beats | None) -> tuple[float, float] | None:
        doc = self._state.doc
        regions = doc.timing.swing_regions
        try:
            lo, hi = retime_bounds(
                doc.timing.tempo_events,
                beat=swing_warp(beat, regions), left=swing_warp(left, regions),
                right=None if right is None else swing_warp(right, regions))
        except ValueError:
            return None
        offset = doc.timing.offset_seconds
        return (lo + offset, hi + offset) if hi - lo > 2e-3 else None

    def press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        tick = self._tick_at(event.position().x())
        if tick is None:
            return False
        anchors = self._anchors()
        left = max((p for p in anchors if p < tick.beat - _EPS), default=None)
        right = min((p for p in anchors if p > tick.beat + _EPS), default=None)
        label = f"m{tick.measure}" if tick.barline else f"beat {tick.beat:g}"
        pinned = rippled = None
        if left is not None:
            rippled = self._bounds(tick.beat, left, None)
            pinned = self._bounds(tick.beat, left, right) if right is not None \
                else rippled
            if pinned is None and rippled is None:
                self._state.status.emit(
                    f"{label} has no room to move between its neighbours")
                return True
        self._drag = _Drag(beat=tick.beat, left=left, right=right,
                           tempo_map=self._lane.tempo_map, unit=self._unit(),
                           pinned=pinned, rippled=rippled, label=label)
        return True

    def move(self, event) -> None:
        if self._drag is None:
            self._update_hover(event.position().x())
            return
        drag = self._drag
        seconds = self._state.axis.t_of(event.position().x(),
                                        self._lane.width())
        if drag.left is None:
            self._preview_offset(drag, seconds)
            return
        ripple = self._state.grid.ripple ^ bool(
            event.modifiers() & Qt.KeyboardModifier.AltModifier)
        bounds = drag.rippled if ripple else drag.pinned
        right = None if ripple else drag.right
        if bounds is None:                       # that rule has no room
            bounds = drag.pinned if ripple else drag.rippled
            right = drag.right if ripple else None
        seconds = min(max(seconds, bounds[0] + 1e-4), bounds[1] - 1e-4)
        drag.last_cmd = AlignBeat(drag.beat, seconds, drag.left, right)
        self._state.preview(drag.last_cmd)
        self._state.status.emit(
            f"{drag.label} → {format_time(seconds)} · "
            f"{self._span_bpm(drag, seconds):.1f} bpm"
            f"{' · ripple' if ripple else ''}")

    def _preview_offset(self, drag: _Drag, seconds: float) -> None:
        """The first line: slide the whole score under the recording."""
        warped = swing_warp(drag.beat, self._state.doc.timing.swing_regions)
        offset = min(max(seconds - drag.tempo_map.seconds_at(warped),
                         _OFFSET_MIN), _OFFSET_MAX)
        drag.last_cmd = SetOffset(offset)
        self._state.preview(drag.last_cmd)
        self._state.status.emit(f"{drag.label} → offset {offset:+.2f} s")

    def _span_bpm(self, drag: _Drag, seconds: float) -> float:
        """Effective tempo of the span the drag is stretching."""
        regions = self._state.doc.timing.swing_regions
        start = self._state.doc.timing.offset_seconds \
            + drag.tempo_map.seconds_at(swing_warp(drag.left, regions))
        span = seconds - start
        return 60.0 * (drag.beat - drag.left) / span if span > 0.0 else 0.0

    def release(self, event) -> None:
        if self._drag is None or event.button() != Qt.MouseButton.LeftButton:
            return
        cmd, self._drag = self._drag.last_cmd, None
        if cmd is None:                          # a click, not a drag
            self._state.cancel_preview()
        else:
            self._state.commit(cmd)

    def double_click(self, event) -> bool:
        return self._tick_at(event.position().x()) is not None

    def key(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._drag is not None:
            self._drag = None
            self._state.cancel_preview()
            self._state.status.emit("align cancelled")
            return True
        return False

    def _update_hover(self, x: float) -> None:
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return                               # a drag elsewhere is running
        tick = self._tick_at(x)
        beat = tick.beat if tick is not None else None
        if beat == self._hover:
            return
        self._hover = beat
        if beat is None:
            self._lane.unsetCursor()
        else:
            self._lane.setCursor(Qt.CursorShape.SizeHorCursor)
        self._lane.update()
