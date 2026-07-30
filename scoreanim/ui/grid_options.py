"""What the timeline lane is showing, and how a tick drag behaves.

Runtime view state, never document intent (rule 5): nothing here is
serialized and nothing is undoable. It lives on AppState next to the time
axis because the transport strip sets it and the lane reads it, and the
views never talk to each other.
"""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, Signal

from scoreanim.core.timing import BARS, GridUnit


class LaneDisplay(Enum):
    """Which of the lane's two modes is showing."""
    TEMPO = "Tempo"              # the red tempo step line, draggable points
    TICKS = "Ticks"              # a draggable grid, no tempo line


class GridOptions(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._display = LaneDisplay.TEMPO
        self._unit: GridUnit = BARS
        self._ripple = False

    @property
    def display(self) -> LaneDisplay:
        return self._display

    def set_display(self, display: LaneDisplay) -> None:
        if display is not self._display:
            self._display = display
            self.changed.emit()

    @property
    def unit(self) -> GridUnit:
        """The grid step: barlines only, or every 1/4, 1/8, 1/8T, 1/16."""
        return self._unit

    def set_unit(self, unit: GridUnit) -> None:
        if unit != self._unit:
            self._unit = unit
            self.changed.emit()

    @property
    def ripple(self) -> bool:
        """False pins the anchors either side of a dragged line; True lets
        everything after it slide, keeping its tempo. Alt flips whichever
        is set, for one drag."""
        return self._ripple

    def set_ripple(self, ripple: bool) -> None:
        if bool(ripple) is not self._ripple:
            self._ripple = bool(ripple)
            self.changed.emit()
