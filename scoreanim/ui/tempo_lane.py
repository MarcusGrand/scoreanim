"""TempoLaneView: the timeline lane under the waveform (PHASES 4.2).

The host widget. It owns everything the lane's modes share — the
background, the measure-number strip, the time-axis mapping, the cached
`TempoMap` and the playhead — and delegates drawing and gestures to the
mode that is showing:

- `ui/lane_tempo.py` — tempo events as draggable points (the red step
  line).
- `ui/lane_ticks.py` — the grid lines as drag handles, for lining the
  score up with the waveform.

Which one is showing is `AppState.grid.display` (ui/grid_options.py),
transient view state set from the transport strip.

Observes AppState only — the same axis object as the waveform, so the two
views scroll and zoom together without knowing of each other.

Swing does not live here (ruling 2026-07-11): v1 swing is one global
ratio set numerically on the transport bar (ui/transport.py,
SetGlobalSwing); per-region authoring returns later (BACKLOG 7).

x ⇄ beat mapping goes through the document's own TempoMap (beat →
seconds → axis x). A mode's drag may pass its own PRE-DRAG map, so the
mapping doesn't slide under the cursor while the preview retimes
everything else live.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from scoreanim.core.score.identity import Beats
from scoreanim.core.timing import TempoMap
from scoreanim.ui.app_state import AppState, apply_wheel
from scoreanim.ui.grid_options import LaneDisplay
from scoreanim.ui.lane_style import BG, GRID, GRID_TEXT, PLAYHEAD, TOP_PAD
from scoreanim.ui.lane_tempo import TempoPointsMode
from scoreanim.ui.lane_ticks import TickAlignMode


class TempoLaneView(QWidget):
    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._map = TempoMap(list(app_state.doc.timing.tempo_events))
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)           # the tick grid hovers
        self._modes = {LaneDisplay.TEMPO: TempoPointsMode(self),
                       LaneDisplay.TICKS: TickAlignMode(self)}
        self._mode = self._modes[app_state.grid.display]
        app_state.axis.changed.connect(self.update)
        app_state.grid.changed.connect(self._on_grid_changed)
        app_state.document_changed.connect(self._on_document_changed)
        app_state.playhead_changed.connect(lambda _t: self.update())

    def sizeHint(self):  # noqa: N802
        hint = super().sizeHint()
        hint.setHeight(130)
        return hint

    def _on_grid_changed(self) -> None:
        """Mode switch, or a new grid step. A mode that was mid-drag when
        the user switched away cancels its preview on the way out."""
        mode = self._modes[self._state.grid.display]
        if mode is not self._mode:
            self._mode.deactivate()
            self._mode = mode
        self.update()

    def _on_document_changed(self) -> None:
        self._map = TempoMap(list(self._state.doc.timing.tempo_events))
        self._mode.document_changed()
        self.update()

    # -- what the modes read ----------------------------------------------------

    @property
    def state(self) -> AppState:
        return self._state

    @property
    def tempo_map(self) -> TempoMap:
        """The map of the document as it is showing (preview included)."""
        return self._map

    def x_of_beat(self, beat: Beats, tempo_map: TempoMap | None = None
                  ) -> float:
        m = tempo_map or self._map
        t = self._state.doc.timing.offset_seconds + m.seconds_at(beat)
        return self._state.axis.x_of(t, self.width())

    def beat_of_x(self, x: float, tempo_map: TempoMap | None = None) -> Beats:
        m = tempo_map or self._map
        t = self._state.axis.t_of(x, self.width())
        return m.beats_at(max(0.0, t - self._state.doc.timing.offset_seconds))

    # -- painting ---------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), BG)
        w, h = self.width(), self.height()
        self._draw_measure_grid(painter, w, h)
        self._mode.paint(painter)
        x = self._state.axis.x_of(self._state.playhead, w)
        if 0 <= x <= w:
            painter.setPen(QPen(PLAYHEAD, 1))
            painter.drawLine(QPointF(x, 0), QPointF(x, h))
        painter.end()

    def _draw_measure_grid(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(QPen(GRID, 1))
        xs = []
        for m in self._state.measures:
            x = self.x_of_beat(m.start)
            if -50 <= x <= w + 50:
                painter.drawLine(QPointF(x, TOP_PAD), QPointF(x, h))
                xs.append((x, m.number))
        painter.setPen(GRID_TEXT)
        last_label_x = -1e9
        for x, number in xs:
            if x - last_label_x >= 28:           # avoid label pile-up
                painter.drawText(QPointF(x + 2, TOP_PAD - 4), f"m{number}")
                last_label_x = x

    # -- interaction ------------------------------------------------------------
    #
    # The mode gets first refusal on every gesture; what it does not take
    # falls back to the lane's own click-to-seek.

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._mode.press(event) \
                and event.button() == Qt.MouseButton.LeftButton:
            t = self._state.axis.t_of(event.position().x(), self.width())
            self._state.request_seek(
                min(max(t, 0.0), self._state.axis.duration))
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._mode.move(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._mode.release(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._mode.double_click(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if not self._mode.key(event):
            super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        apply_wheel(self._state.axis, event, self.width())
