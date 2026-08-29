"""TimelineBar: the document's own timing, under the lanes.

Tempo, Offset and Swing — the three numbers that say where the score
sits against the recording, grouped under one "Timing" label. Nothing
else: the lane's view options (which lane, which grid lines, Flatten)
moved up to the gear on the strip above (`ui/lane_menu.py`) in C4,
because a bar that mixed three document fields with three view controls
gave no clue which was which.

Ruling (Marcus, 2026-07-24): everything time-related lives in the lower
zone, not in the inspector.

All three number fields preview as you type (`ui/live_field.py`): the
ticks move with the number, so you can see whether a tempo, an offset
or a swing ratio fits the recording while you are still setting it.
Each supplies the one `_*_edit` function its preview and its commit both
call, and each resyncs through `sync_from_document` — the window calls
that on every document change, so a resync never re-executes a command.

The Tempo field still watches `AppState.grid`, even with the lane
controls gone: it retitles itself for the grid line the user has
selected ("Tempo from m3"), so what it would set is readable before
typing.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QDoubleSpinBox, QHBoxLayout, QLabel,
                               QWidget)

from scoreanim.core.project import (Command, ProjectDoc, SetGlobalSwing,
                                    SetOffset)
from scoreanim.ui import panel_style
from scoreanim.ui.app_state import AppState
from scoreanim.ui.grid_options import LaneDisplay
from scoreanim.ui.live_field import LiveField
from scoreanim.ui.readouts import (global_swing_ratio, tempo_command,
                                   tempo_scope)


class TimelineBar(QWidget):
    """The three document timing fields, in one left-aligned row."""

    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state

        # initial tempo (FIX 2): edits the beat-0 tempo event through the
        # existing tempo-map machinery (MoveTempoEvent) — not a parallel
        # path. With no audio it sets the no-audio playback pace; the
        # offset is simply 0 then.
        self._bpm_spin = QDoubleSpinBox()
        self._bpm_spin.setDecimals(1)
        self._bpm_spin.setSingleStep(1.0)
        self._bpm_spin.setRange(20.0, 400.0)
        self._bpm_spin.setToolTip(
            "Tempo in bpm. With a grid line selected in the lane it sets "
            "the tempo\nfrom that line to the end and releases the locks "
            "after it; with nothing\nselected it sets the initial tempo.")

        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setSuffix(" s")      # a unit, not a label
        self._offset_spin.setDecimals(2)
        self._offset_spin.setSingleStep(0.05)
        self._offset_spin.setRange(-60.0, 3600.0)

        # global swing ratio (ruling 2026-07-11): 0.50 straight … 0.67
        # triplet, one value for the whole piece; regions later (BACKLOG 7)
        self._swing_spin = QDoubleSpinBox()
        self._swing_spin.setDecimals(2)
        self._swing_spin.setSingleStep(0.01)
        self._swing_spin.setRange(0.50, 0.75)

        self._bpm = LiveField(self._bpm_spin, app_state, self._bpm_edit)
        self._offset = LiveField(self._offset_spin, app_state,
                                 self._offset_edit)
        self._swing = LiveField(self._swing_spin, app_state, self._swing_edit)
        # the tuple is what holds the fields alive, and the test scans it
        self.live_fields = (self._bpm, self._offset, self._swing)

        self._bpm_label = QLabel("Tempo")
        # One field and its label are a group; the 12 px gaps below are
        # what keep "Swing" reading as the swing field's own label and
        # not as something that belongs to the field before it.
        row = QHBoxLayout(self)
        row.setContentsMargins(panel_style.PADDING, panel_style.ROW_GAP,
                               panel_style.PADDING, panel_style.ROW_GAP)
        row.setSpacing(panel_style.COLUMN_GAP)
        heading = QLabel("Timing")
        heading.setObjectName("ZoneHeading")
        row.addWidget(heading)
        row.addSpacing(panel_style.GROUP_GAP)
        row.addWidget(self._bpm_label)
        row.addWidget(self._bpm_spin)
        for text, spin in (("Offset", self._offset_spin),
                           ("Swing", self._swing_spin)):
            row.addSpacing(panel_style.GROUP_GAP)
            row.addWidget(QLabel(text))
            row.addWidget(spin)
        row.addStretch(1)                # left-aligned: the gap goes right
        self._sync_from_grid()

        app_state.grid.changed.connect(self._sync_from_grid)

    # -- document sync ---------------------------------------------------------

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Resync the time fields from document intent (execute, undo,
        redo, and project load all arrive here via the window). A field
        with a live edit keeps its number — see `LiveField.resync`."""
        self._offset.resync(doc.timing.offset_seconds)
        self._sync_from_grid()           # the Tempo field lives there now
        self._swing.resync(global_swing_ratio(doc))

    # -- the lane's selected line ----------------------------------------------

    def _sync_from_grid(self) -> None:
        """Retitle the Tempo field for whatever grid line is selected,
        and show that line's tempo. The lane's own view options live in
        the gear now (`ui/lane_menu.py`); this is all the bar still
        wants from the grid."""
        label, bpm = tempo_scope(self._state.doc, self._selected_beat(),
                                 self._state.measures)
        self._bpm_label.setText(label)
        self._bpm.resync(bpm)            # skipped while the edit is live

    # -- what each field means by a number -------------------------------------
    #
    # One function per field, called by both its preview and its commit,
    # so the two can never ask for different edits. All three read the
    # COMMITTED document: `state.doc` hands a field back its own preview,
    # so a no-op guard reading it would compare the value with itself and
    # never let anything commit. None means "changes nothing".

    def _selected_beat(self):
        """The lane's selected line, only while the lane is showing it."""
        grid = self._state.grid
        return grid.selected_beat if grid.display is LaneDisplay.TICKS \
            else None

    def _bpm_edit(self, value: float) -> Command | None:
        """With a line selected it sets the tempo from there to the end
        (SetTempoFrom); with nothing selected it edits the initial tempo
        through the existing machinery — MoveTempoEvent on the first
        event, so a tempo curve's later events survive."""
        doc = self._state.committed
        beat = self._selected_beat()
        _label, showing = tempo_scope(doc, beat, self._state.measures)
        if abs(value - showing) < 1e-9:
            return None
        return tempo_command(doc, beat, value)

    def _offset_edit(self, value: float) -> Command | None:
        if abs(value - self._state.committed.timing.offset_seconds) < 1e-9:
            return None
        return SetOffset(value)

    def _swing_edit(self, value: float) -> Command | None:
        """No measures loaded means no score extent to swing, so the
        field says nothing at all — no preview and no commit."""
        if abs(value - global_swing_ratio(self._state.committed)) < 1e-9:
            return None
        measures = self._state.measures
        if not measures:
            return None
        end_beat = measures[-1].start + measures[-1].quarter_length
        return SetGlobalSwing(value, end_beat)
