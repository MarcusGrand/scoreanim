"""TimelineBar, offscreen: the document timing fields (Tempo, Offset,
Swing). The lane's view options moved to the gear (C4) and are tested
in tests/test_lane_menu.py.

All three fields preview as you type and commit when the edit ends
(`ui/live_field.py`): one command each, an epsilon no-op guard, a resync
that never re-executes, and one undo entry for a whole typing session.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.timeline_bar import TimelineBar  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_time_fields_commit_one_command_each(qapp) -> None:
    """Tempo/Offset/Swing live in the lower zone (ruling 2026-07-24) with
    the alpha commit wiring: epsilon no-op guard, one undoable command."""
    state = AppState()
    widget = TimelineBar(state)

    widget._offset_spin.setValue(1.25)
    widget._offset.commit()
    assert state.doc.timing.offset_seconds == 1.25
    widget._offset.commit()                      # same value → no-op
    state.undo()
    assert state.doc.timing.offset_seconds == 0.0
    assert not state.can_undo                    # exactly one command

    widget._bpm_spin.setValue(96.0)
    widget._bpm.commit()
    assert state.doc.timing.tempo_events[0].bpm == 96.0
    state.undo()
    assert not state.can_undo

    # swing with no measures loaded: guarded no-op (no end beat to span)
    widget._swing_spin.setValue(0.67)
    widget._swing.commit()
    assert not state.can_undo


def test_sync_from_document_never_reexecutes(qapp) -> None:
    state = AppState()
    widget = TimelineBar(state)
    widget._offset_spin.setValue(1.25)
    widget._offset.commit()
    widget.sync_from_document(state.doc)         # the resync pass
    assert widget._offset_spin.value() == 1.25
    assert widget._bpm_spin.value() == state.doc.timing.tempo_events[0].bpm
    assert widget._swing_spin.value() == 0.5     # no regions → straight
    state.undo()                                 # resync added no command
    assert not state.can_undo
    widget.sync_from_document(state.doc)
    assert widget._offset_spin.value() == 0.0


def test_the_bar_holds_only_document_timing(qapp) -> None:
    """C4: the lane's view options left for the gear. What is still here
    is three fields, and all three edit the document."""
    from PySide6.QtWidgets import QComboBox, QToolButton

    state = AppState()
    widget = TimelineBar(state)
    assert not widget.findChildren(QComboBox)
    assert not widget.findChildren(QToolButton)
    assert len(widget.live_fields) == 3


def test_the_tempo_field_still_follows_the_lane(qapp) -> None:
    """The bar dropped the lane CONTROLS, not the lane signal: switching
    to the tempo lane drops the selected line, so the field goes back to
    saying "Tempo"."""
    from scoreanim.core.score.model import MeasureInfo
    from scoreanim.ui.grid_options import LaneDisplay

    state = AppState()
    state.set_measures(tuple(MeasureInfo(number=n + 1, start=n * 4.0,
                                         quarter_length=4.0)
                             for n in range(8)))
    widget = TimelineBar(state)
    state.grid.set_selected_beat(8.0)
    assert widget._bpm_label.text() == "Tempo from m3"
    state.grid.set_display(LaneDisplay.TEMPO)     # what the gear does
    assert widget._bpm_label.text() == "Tempo"
    assert not state.can_undo and not state.is_dirty


def test_tempo_field_follows_the_lane_selection(qapp) -> None:
    """Clicking a line and typing a tempo is the replacement for dragging
    the old tempo line: it sets the tempo from there to the end."""
    from scoreanim.core.score.model import MeasureInfo
    from scoreanim.core.timing import TempoEvent

    state = AppState()
    state.set_measures(tuple(MeasureInfo(number=n + 1, start=n * 4.0,
                                         quarter_length=4.0)
                             for n in range(8)))
    widget = TimelineBar(state)
    assert widget._bpm_label.text() == "Tempo"

    state.grid.set_selected_beat(8.0)
    assert widget._bpm_label.text() == "Tempo from m3"
    widget._bpm_spin.setValue(90.0)
    widget._bpm.commit()
    assert state.doc.timing.tempo_events == (TempoEvent(0.0, 120.0),
                                             TempoEvent(8.0, 90.0))
    assert state.undo_text() == "set tempo"
    assert widget._bpm_spin.value() == 90.0       # shows what it just set
    widget._bpm.commit()                          # same value -> no-op
    state.undo()
    assert not state.can_undo

    state.grid.set_selected_beat(None)            # back to the initial tempo
    assert widget._bpm_label.text() == "Tempo"
    widget._bpm_spin.setValue(96.0)
    widget._bpm.commit()
    assert state.doc.timing.tempo_events[0].bpm == 96.0
    assert state.undo_text() == "move tempo event"


def test_tempo_previews_while_you_type(qapp) -> None:
    """The ticks have to move with the number, not wait for the click
    outside: every valid value previews, and the whole typing session
    still lands as ONE undo entry."""
    from scoreanim.core.score.model import MeasureInfo
    from scoreanim.core.timing import TempoEvent

    state = AppState()
    state.set_measures(tuple(MeasureInfo(number=n + 1, start=n * 4.0,
                                         quarter_length=4.0)
                             for n in range(8)))
    widget = TimelineBar(state)
    state.grid.set_selected_beat(8.0)
    repaints = []
    state.document_changed.connect(lambda: repaints.append(state.doc))

    widget._bpm_spin.setValue(100.0)              # typing, box still focused
    assert state.doc.timing.tempo_events == (TempoEvent(0.0, 120.0),
                                             TempoEvent(8.0, 100.0))
    assert len(repaints) == 1                     # the lanes were told
    assert state.committed.timing.tempo_events == (TempoEvent(0.0, 120.0),)
    assert not state.can_undo                     # nothing committed yet

    widget._bpm_spin.setValue(90.0)               # still typing
    assert state.doc.timing.tempo_events[1].bpm == 90.0
    # previews apply to the COMMITTED doc, so they never stack up
    assert len(state.doc.timing.tempo_events) == 2
    assert not state.can_undo

    widget._bpm.commit()                          # Enter / click away
    assert state.committed.timing.tempo_events == (TempoEvent(0.0, 120.0),
                                                   TempoEvent(8.0, 90.0))
    assert state.undo_text() == "set tempo"
    state.undo()
    assert not state.can_undo                     # exactly one entry


def test_resync_does_not_fight_the_typing(qapp) -> None:
    """A preview emits document_changed, which comes straight back here
    as a resync — it must not rewrite the number under the cursor."""
    state = AppState()
    widget = TimelineBar(state)

    widget._bpm_spin.setValue(100.0)
    widget.sync_from_document(state.doc)          # what the window does
    assert widget._bpm_spin.value() == 100.0
    widget._sync_from_grid()
    assert widget._bpm_spin.value() == 100.0
    assert not state.can_undo

    widget._bpm.commit()
    assert state.committed.timing.tempo_events[0].bpm == 100.0
    # the edit is over: a resync owns the field again
    state.undo()
    widget.sync_from_document(state.doc)
    assert widget._bpm_spin.value() == 120.0


def test_typing_back_to_the_start_cancels_the_preview(qapp) -> None:
    state = AppState()
    widget = TimelineBar(state)

    widget._bpm_spin.setValue(100.0)
    assert state.doc is not state.committed       # a preview is live
    widget._bpm_spin.setValue(120.0)              # back where it started
    assert state.doc is state.committed           # preview dropped
    assert not state.axis._held                   # and the axis released
    widget._bpm.commit()
    assert not state.can_undo and not state.is_dirty


def test_offset_previews_while_you_type(qapp) -> None:
    """The grid slides against the waveform on every digit, and the
    typing session still lands as ONE undo entry."""
    state = AppState()
    widget = TimelineBar(state)
    repaints = []
    state.document_changed.connect(lambda: repaints.append(state.doc))

    widget._offset_spin.setValue(0.5)             # typing
    assert state.doc.timing.offset_seconds == 0.5
    assert state.committed.timing.offset_seconds == 0.0
    assert len(repaints) == 1 and not state.can_undo

    widget._offset_spin.setValue(1.25)            # still typing
    assert state.doc.timing.offset_seconds == 1.25
    assert not state.can_undo

    widget._offset.commit()
    assert state.committed.timing.offset_seconds == 1.25
    assert state.undo_text() == "set offset"
    state.undo()
    assert not state.can_undo                     # exactly one entry

    # typed back to where it started: the preview is dropped, not committed
    widget._offset_spin.setValue(0.5)
    assert state.doc is not state.committed
    widget._offset_spin.setValue(0.0)
    assert state.doc is state.committed
    assert not state.axis._held
    widget._offset.commit()
    assert not state.can_undo and not state.is_dirty


def test_swing_previews_while_you_type(qapp) -> None:
    """Swing needs a score extent to write a region over: with measures
    loaded it previews like the others, and with none it says nothing at
    all — no preview and no commit."""
    from scoreanim.core.score.model import MeasureInfo

    state = AppState()
    widget = TimelineBar(state)

    widget._swing_spin.setValue(0.6)              # no measures yet
    assert state.doc is state.committed           # nothing previewed
    widget._swing.commit()
    assert not state.can_undo

    state.set_measures(tuple(MeasureInfo(number=n + 1, start=n * 4.0,
                                         quarter_length=4.0)
                             for n in range(4)))
    widget._swing_spin.setValue(0.62)             # typing
    assert state.doc.timing.swing_regions[0].ratio == 0.62
    assert state.committed.timing.swing_regions == ()
    widget._swing_spin.setValue(0.67)             # still typing
    regions = state.doc.timing.swing_regions
    assert len(regions) == 1 and regions[0].ratio == 0.67   # never stack
    assert not state.can_undo

    widget._swing.commit()
    assert state.committed.timing.swing_regions[0].ratio == 0.67
    assert state.undo_text() == "set swing"
    state.undo()
    assert not state.can_undo


def test_a_resync_mid_edit_leaves_the_other_fields_alone(qapp) -> None:
    """A preview emits document_changed, so the window resyncs the whole
    bar while one field is still being typed in. The live field keeps its
    number; the others follow the document."""
    state = AppState()
    widget = TimelineBar(state)
    widget._offset.commit()                       # nothing to commit
    widget._offset_spin.setValue(2.0)             # typing
    widget.sync_from_document(state.doc)          # what the window does
    assert widget._offset_spin.value() == 2.0     # not rewritten
    assert widget._bpm_spin.value() == 120.0      # follows the document
    assert not state.can_undo


def test_undo_during_an_edit_takes_the_field_back(qapp) -> None:
    """An undo (or a project load) drops the preview from under the
    field. It must let go rather than sit on a number nothing shows."""
    state = AppState()
    widget = TimelineBar(state)
    widget._bpm_spin.setValue(100.0)
    widget._bpm.commit()

    widget._bpm_spin.setValue(90.0)               # typing again
    assert state.doc.timing.tempo_events[0].bpm == 90.0
    state.undo()                                  # pulls the rug out
    widget.sync_from_document(state.doc)
    assert widget._bpm_spin.value() == 120.0      # follows the document
    assert not widget._bpm.previewing()
