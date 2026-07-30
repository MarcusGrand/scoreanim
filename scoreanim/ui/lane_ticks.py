"""Ticks mode: the grid lines are the drag handles.

Drag a barline (or a beat, at the chosen subdivision) onto the waveform
and the tempo around it re-spaces to suit. The red tempo line is not
drawn here — the same edit shows up as a step in tempo mode, because both
modes are two views of one set of tempo events.

What holds still while you drag is the whole feel of this, and it is a
statement the user makes rather than a guess we take:

- **double-click a line to lock it**, and it stays at that timestamp.
  Locked lines draw thick and orange with a padlock. Double-click again
  to unlock.
- a drag re-spaces the span from the previous lock (or the score start)
  to the line, EVENLY — one tempo across it. If a lock sits after the
  line, the span up to it evens out too; otherwise the music after keeps
  its tempo and slides along.
- a drag locks the line it just placed, so aligning left to right holds
  everything you have already put down. "Keep shape" on the strip (or
  Alt for one drag) stretches the span proportionally instead, which is
  what you want after tapping a rubato passage.
- the first line has no anchor before it, so dragging it is the "line the
  score up with the recording" move: it sets the offset and slides the
  whole score, exactly what the Offset field does.

Beat domains, the one thing to keep straight here: ticks and locks are
MUSICAL beats, while a tempo event's position is a SWING-WARPED beat.
Ticks warp on their way to a pixel (`_x_of_tick`); nothing here goes the
other way, because nothing here reads tempo events.

`ui/lane_align_drag.py` owns the drag itself; this module owns the grid,
the painting and the hit-testing.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication

from scoreanim.core.project import SetBeatLock
from scoreanim.core.score.identity import Beats
from scoreanim.core.timing import (GridUnit, TempoMap, bpm_at, coarsened,
                                   grid_ticks, swing_warp)
from scoreanim.core.timing.grid import EMPTY, GridTick, TickGrid
from scoreanim.ui import lane_align_drag as drag_rules
from scoreanim.ui.lane_style import (BOTTOM_PAD, GRID_TEXT, HIT_PX, LOCK,
                                     TOP_PAD)

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


class TickAlignMode:
    def __init__(self, lane) -> None:
        self._lane = lane
        self._state = lane.state
        self._grid: TickGrid = EMPTY
        self._grid_key: tuple | None = None
        self._drag: drag_rules.AlignDrag | None = None
        self._hover: Beats | None = None

    # -- the grid ---------------------------------------------------------------

    def _px_per_beat(self) -> float:
        axis = self._state.axis
        doc = self._state.doc
        centre = (axis.t0 + axis.t1) / 2.0 - doc.timing.offset_seconds
        beat = self._lane.tempo_map.beats_at(max(0.0, centre))
        bpm = bpm_at(doc.timing.tempo_events, beat)
        return self._lane.width() / axis.span * 60.0 / bpm

    def grid_unit(self) -> GridUnit:
        """The step actually drawn — thinned when ticks would crowd, and
        frozen for the length of a drag: retiming a span changes px per
        beat, and a grid that changes resolution under the cursor reads
        as the view jumping."""
        if self._drag is not None:
            return self._drag.unit
        return coarsened(self._state.grid.unit, self._px_per_beat())

    def _ticks(self) -> TickGrid:
        unit = self.grid_unit()
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

    def _handles(self) -> tuple[tuple[float, GridTick], ...]:
        """Every line the pointer can grab: the visible grid ticks, plus
        every lock. A lock is a handle whatever the grid step is —
        otherwise a lock set at 1/16 becomes ungrabbable, and invisible,
        the moment the user switches to Bars, while still steering every
        drag."""
        grid = self._ticks()
        w = self._lane.width()
        lo = self._lane.beat_of_x(-_EDGE_PX) - 1.0    # a warp shifts by < 1
        hi = self._lane.beat_of_x(w + _EDGE_PX) + 1.0
        beats = {t.beat: t for t in grid.between(lo, hi)}
        for beat in self._state.doc.timing.locked_beats:
            beats.setdefault(beat, GridTick(beat, False, None))
        out = []
        for beat, tick in sorted(beats.items()):
            x = self._x_of_tick(beat)
            if -_EDGE_PX <= x <= w + _EDGE_PX:
                out.append((x, tick))
        return tuple(out)

    # -- painting ---------------------------------------------------------------

    def paint(self, painter: QPainter) -> None:
        w, h = self._lane.width(), self._lane.height()
        top = TOP_PAD + (h - TOP_PAD - BOTTOM_PAD) * _SUB_TOP
        locked = set(self._state.doc.timing.locked_beats)
        for x, tick in self._handles():
            if tick.beat in locked:
                self._draw_lock(painter, x, h)
            elif tick.barline:
                # over the host's grid line: in this mode a barline is a
                # handle, so it has to read as structure, not as one more
                # tick in the row
                painter.setPen(QPen(_BAR, 1))
                painter.drawLine(QPointF(x, TOP_PAD), QPointF(x, h))
            else:
                whole = abs(tick.beat - round(tick.beat)) < _EPS
                painter.setPen(QPen(_SUB_STRONG if whole else _SUB, 1))
                painter.drawLine(QPointF(x, top), QPointF(x, h - BOTTOM_PAD))
        self._draw_bar_tempos(painter, w, h)
        handle = self._drag.beat if self._drag is not None else self._hover
        if handle is not None and handle not in locked:
            # the LIVE map, so the highlight sits on the previewed
            # position and tracks the pointer — the pre-drag map would
            # leave it behind at the beat's old pixel
            painter.setPen(QPen(_HANDLE, 2))
            x = self._x_of_tick(handle)
            painter.drawLine(QPointF(x, TOP_PAD), QPointF(x, h))

    def _draw_lock(self, painter: QPainter, x: float, h: int) -> None:
        """A locked line, with a padlock drawn from primitives — a glyph
        would land on whatever font the platform has."""
        painter.setPen(QPen(LOCK, 2))
        painter.drawLine(QPointF(x, TOP_PAD), QPointF(x, h))
        shackle = QRectF(x - 2.5, TOP_PAD - 10.5, 5.0, 5.0)
        painter.drawArc(shackle, 0, 180 * 16)         # the loop on top
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(LOCK)
        painter.drawRect(QRectF(x - 3.5, TOP_PAD - 8.0, 7.0, 6.0))

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
        for tick_x, tick in self._handles():
            dx = abs(tick_x - x)
            if dx < best_dx:
                best, best_dx = tick, dx
        return best

    @staticmethod
    def _label(tick: GridTick) -> str:
        return f"m{tick.measure}" if tick.barline else f"beat {tick.beat:g}"

    def press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        tick = self._tick_at(event.position().x())
        if tick is None:
            return False
        self._drag = drag_rules.begin(self._state, self._lane, tick.beat,
                                      self._label(tick),
                                      self.grid_unit())
        return True

    def move(self, event) -> None:
        if self._drag is None:
            self._update_hover(event.position().x())
            return
        seconds = self._state.axis.t_of(event.position().x(),
                                        self._lane.width())
        drag_rules.move(self._state, self._drag, seconds,
                        alt=bool(event.modifiers()
                                 & Qt.KeyboardModifier.AltModifier))

    def release(self, event) -> None:
        if self._drag is None or event.button() != Qt.MouseButton.LeftButton:
            return
        cmd, self._drag = self._drag.last_cmd, None
        if cmd is None:                          # a click, not a drag
            self._state.cancel_preview()
        else:
            self._state.commit(cmd)

    def double_click(self, event) -> bool:
        """Lock the line, or let it go. Qt sends press → release before
        this, so the click's own drag has already been cancelled."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        tick = self._tick_at(event.position().x())
        if tick is None:
            return False
        locked = tick.beat in set(self._state.doc.timing.locked_beats)
        if self._state.execute(SetBeatLock(tick.beat, not locked)):
            self._state.status.emit(
                f"{self._label(tick)} {'unlocked' if locked else 'locked'}")
        return True

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
