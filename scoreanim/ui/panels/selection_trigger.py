"""Re-timing controls for the current selection (2026-08-08).

The "Fires" row shows the EFFECTIVE trigger — where the automatic
schedule fires the element, or where the user moved it, with a quiet
"(moved)" marker — and the two step buttons walk the element through
the onset stops of its OWN system (core/animation/onset_stops.py).
Reset hands it back to the automatic schedule. The whole block is
blank and disabled for a selection that cannot be re-timed
(core/animation/retime.py).

Two wiring rules, both about staleness:

- The schedule is read through a PROVIDER bound at install, never
  held: the window swaps the schedule on a live rebuild with no new
  load, and a pull cannot go stale.
- The widget never self-subscribes to `document_changed`. Signal order
  against the window's own reschedule pass is not guaranteed, so the
  window calls `sync_from_document` explicitly AFTER that pass — the
  inspector's own habit. `selection_changed` is transient state and
  safe to subscribe to (the selection panel's precedent).
"""
from __future__ import annotations

from bisect import bisect_right
from typing import Callable, Sequence

from PySide6.QtWidgets import (QFormLayout, QHBoxLayout, QLabel, QPushButton,
                               QWidget)

from scoreanim.core.animation import (TriggerSchedule, is_retimeable,
                                      step_from, stops_for_system)
from scoreanim.core.project import ProjectDoc, SetTriggerBeat
from scoreanim.ui import panel_style
from scoreanim.ui.app_state import AppState

_EMPTY = "—"


def bar_beat_label(beats: float, measures: Sequence) -> str:
    """A beat on the performance axis as "bar · beat": the document-
    order bar (with the printed number when the two differ, the
    Measure row's habit) and the 1-based beat inside it. Off the
    measure axis it falls back to raw beats."""
    starts = [m.start for m in measures]
    i = bisect_right(starts, beats) - 1
    if 0 <= i < len(measures):
        m = measures[i]
        if beats <= m.start + m.quarter_length:
            bar = str(i + 1)
            if m.number != i + 1:
                bar = f"{i + 1} (printed {m.number})"
            return f"{bar} · beat {beats - m.start + 1:g}"
    return f"{beats:g}"


class SelectionTriggerControls(QWidget):
    """The Fires readout and the earlier/later/Reset stepper."""

    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._layout = None                  # bound per load
        self._measures: tuple = ()
        self._schedule: Callable[[], TriggerSchedule | None] = lambda: None
        self._by_id: dict = {}

        self._fires = QLabel(_EMPTY)
        self._moved = QLabel("(moved)")
        self._moved.setEnabled(False)        # the dimmed-caption idiom
        self._moved.setHidden(True)
        fires_row = QHBoxLayout()
        fires_row.setContentsMargins(0, 0, 0, 0)
        fires_row.addWidget(self._fires)
        fires_row.addWidget(self._moved)
        fires_row.addStretch(1)
        fires_box = QWidget()
        fires_box.setLayout(fires_row)

        self._earlier = QPushButton("Earlier")
        self._later = QPushButton("Later")
        self._reset = QPushButton("Reset")
        self._earlier.setToolTip(
            "Fire this element at the previous event of its system")
        self._later.setToolTip(
            "Fire this element at the next event of its system")
        self._reset.setToolTip("Back to the automatic fire time")
        self._earlier.clicked.connect(lambda: self._step(-1))
        self._later.clicked.connect(lambda: self._step(+1))
        self._reset.clicked.connect(self._clear)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(panel_style.ROW_GAP)
        buttons.addWidget(self._earlier)
        buttons.addWidget(self._later)
        buttons.addWidget(self._reset)
        buttons.addStretch(1)
        buttons_box = QWidget()
        buttons_box.setLayout(buttons)

        form = QFormLayout(self)
        # the padding is paid at the Selection panel's own edge
        panel_style.style_form(form, padding=False)
        form.addRow("Fires", fires_box)
        form.addRow("", buttons_box)
        panel_style.fix_label_column(form)

        app_state.selection_changed.connect(self.sync)
        self.sync()

    def bind_score(self, layout, measures,
                   schedule: Callable[[], TriggerSchedule | None]) -> None:
        """Per load: the layout (an element's system, and the stops in
        it), the measure axis (the label), and the current schedule as
        a provider."""
        self._layout = layout
        self._measures = tuple(measures)
        self._schedule = schedule
        self._by_id = {} if layout is None else {
            el.identity.element_id: el for el in layout.elements}
        self.sync()

    def sync_from_document(self, doc: ProjectDoc | None = None) -> None:
        """Window-called after its reschedule pass (execute, undo and
        redo all land here), so the row reads the rebuilt schedule."""
        self.sync()

    # -- state -------------------------------------------------------------

    def _context(self):
        """(element, effective beat) for a re-timeable selection with a
        known trigger, else None — the enablement gate in one place."""
        selection = self._state.selection
        schedule = self._schedule()
        if selection is None or schedule is None:
            return None
        if not is_retimeable(selection.obj):
            return None
        el = self._by_id.get(selection.element_id)
        if el is None or el.system is None:
            return None
        beat = schedule.beats_by_element.get(selection.element_id)
        if beat is None:
            return None
        return el, beat

    def sync(self) -> None:
        ctx = self._context()
        if ctx is None:
            self._fires.setText(_EMPTY)
            self._moved.setHidden(True)
            for button in (self._earlier, self._later, self._reset):
                button.setEnabled(False)
            return
        el, beat = ctx
        moved = (el.identity.element_id
                 in self._state.doc.trigger_overrides)
        self._fires.setText(bar_beat_label(beat, self._measures))
        self._moved.setHidden(not moved)
        stops = stops_for_system(self._layout, el.system)
        self._earlier.setEnabled(step_from(stops, beat, -1) is not None)
        self._later.setEnabled(step_from(stops, beat, +1) is not None)
        self._reset.setEnabled(moved)

    # -- writes ------------------------------------------------------------

    def _step(self, direction: int) -> None:
        ctx = self._context()
        if ctx is None:
            return
        el, beat = ctx
        target = step_from(stops_for_system(self._layout, el.system),
                           beat, direction)
        if target is not None:
            # one press, one command, one undo entry (rule 8)
            self._state.execute(
                SetTriggerBeat(el.identity.element_id, target))

    def _clear(self) -> None:
        selection = self._state.selection
        if selection is not None:
            self._state.execute(
                SetTriggerBeat(selection.element_id, None))
