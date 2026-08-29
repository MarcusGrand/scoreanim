"""The lane's view options, behind one gear at the right of the strip.

What the lane shows (Tempo or Ticks), which grid lines it draws, and
whether a tick drag flattens or keeps the tempo shape. None of it is
document intent (rule 5): every item here sets `AppState.grid`, so
nothing is undoable and nothing is saved.

Split out of `ui/timeline_bar.py` (C4): the bottom bar was one row of
six controls where three edited the document and three only changed the
view. The three view ones came up here, to the header above the lanes
they move, and the bar below keeps document timing alone.

A menu, not three visible widgets, because these are set-and-forget:
you pick a grid step once and then work. The gear's tooltip names the
current lane so you can read the state without opening it.
"""
from __future__ import annotations

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from scoreanim.core.timing import GRID_UNITS
from scoreanim.ui import tips
from scoreanim.ui.app_state import AppState
from scoreanim.ui.grid_options import LaneDisplay
from scoreanim.ui.theme import icons

_SHAPE_TIP = ("Flatten: a dragged span comes out evenly spaced, at one "
              "tempo.\n"
              "Off: it stretches instead, so tempo detail already inside "
              "survives.\n"
              "Alt while dragging flips whichever is set.")

# One sentence per lane, and one for the grid step. Both only mean
# something in the ticks lane, so both say so while they are grayed.
_LANE_TIPS = {
    LaneDisplay.TEMPO: "Show the tempo as draggable points — the red "
                       "step line",
    LaneDisplay.TICKS: "Show the grid lines, and drag them onto the "
                       "recording",
}
_TICKS_ONLY = "Only the ticks lane has a grid to set"


class LaneOptionsButton(QToolButton):
    """Gear at the right edge of the lane header: the lane's own view
    options, none of which touch the document.

    The menu is built once and resynced from `AppState.grid`, which is
    also what the ticks lane reads — so the checkmarks and the lane can
    never disagree, whoever set the state. Grid step and Flatten mean
    nothing in tempo mode, so they gray out there rather than lie.
    """

    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state

        self.menu_widget = QMenu(self)
        self.setIcon(icons.icon("settings"))
        self.setIconSize(icons.BUTTON_SIZE)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setMenu(self.menu_widget)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Lane: which of the two modes is showing. One exclusive group,
        # so the menu cannot show two lanes checked at once.
        self._heading("Lane")
        self._lane_group = QActionGroup(self)
        self._lane_group.setExclusive(True)
        self.lane_actions: dict[LaneDisplay, QAction] = {}
        for display in LaneDisplay:
            action = self._checkable(display.value, self._lane_group)
            tips.describe(action, _LANE_TIPS[display])
            action.triggered.connect(
                lambda _checked, d=display: self._set_display(d))
            self.lane_actions[display] = action

        # Grid: the step the tick lines are drawn on.
        self.menu_widget.addSeparator()
        self._heading("Grid")
        self._unit_group = QActionGroup(self)
        self._unit_group.setExclusive(True)
        self.unit_actions = []
        for unit in GRID_UNITS:
            action = self._checkable(unit.label, self._unit_group)
            tips.describe(action,
                          f"Draw a grid line every {unit.label}")
            action.triggered.connect(
                lambda _checked, u=unit: self._state.grid.set_unit(u))
            self.unit_actions.append(action)

        self.menu_widget.addSeparator()
        self.flatten_action = QAction("Flatten dragged spans", self)
        self.flatten_action.setCheckable(True)
        tips.describe(self.flatten_action, _SHAPE_TIP)
        self.flatten_action.toggled.connect(self._state.grid.set_flatten)
        self.menu_widget.addAction(self.flatten_action)

        self._sync_from_grid()
        app_state.grid.changed.connect(self._sync_from_grid)

    def _heading(self, text: str) -> None:
        """A group label inside the menu.

        A disabled item, not `QMenu.addSection`: the app's stylesheet
        paints `QMenu::separator` as a plain 1-px line, which is exactly
        what a section is drawn as — the text disappeared. A disabled
        item keeps the words and picks up the dim colour the stylesheet
        already gives them.
        """
        heading = QAction(text, self)
        heading.setEnabled(False)
        self.menu_widget.addAction(heading)

    def _checkable(self, text: str, group: QActionGroup) -> QAction:
        action = QAction(text, self)
        action.setCheckable(True)
        group.addAction(action)
        self.menu_widget.addAction(action)
        return action

    def _set_display(self, display: LaneDisplay) -> None:
        self._state.grid.set_display(display)

    def _sync_from_grid(self) -> None:
        """Push the grid state onto the menu. `blockSignals` all the way
        through: a resync must never look like the user picking an item,
        or the round trip would fight whoever set the state."""
        grid = self._state.grid
        ticks = grid.display is LaneDisplay.TICKS
        for display, action in self.lane_actions.items():
            action.blockSignals(True)
            action.setChecked(display is grid.display)
            action.blockSignals(False)
        for unit, action in zip(GRID_UNITS, self.unit_actions):
            action.blockSignals(True)
            action.setChecked(unit == grid.unit)
            action.blockSignals(False)
            tips.gate(action, ticks, _TICKS_ONLY)
        self.flatten_action.blockSignals(True)
        self.flatten_action.setChecked(grid.flatten)
        self.flatten_action.blockSignals(False)
        tips.gate(self.flatten_action, ticks,
                  "Only a tick drag has a shape to flatten")
        # the state you can read without opening the menu
        self.setToolTip(f"Lane options — showing {grid.display.value}")
