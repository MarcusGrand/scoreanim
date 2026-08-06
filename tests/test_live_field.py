"""LiveField, offscreen: the contract every number field now runs on.

A field previews on every keystroke and commits when the edit ends, so
the typing session is one undo entry. The last test is the standing
rule: a spinbox added to one of these hosts without a LiveField fails
the suite.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QAbstractSpinBox, QApplication,  # noqa: E402
                               QDoubleSpinBox)

from scoreanim.core.project import SetOffset  # noqa: E402
from scoreanim.core.score.model import MeasureInfo  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.live_field import LiveField  # noqa: E402
from scoreanim.ui.panels import EffectsPanel, VideoCanvasPanel  # noqa: E402
from scoreanim.ui.timeline_bar import TimelineBar  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def field(qapp):
    """One spinbox on the document's offset, wired the standard way."""
    state = AppState()
    spin = QDoubleSpinBox()
    spin.setRange(-60.0, 60.0)

    def edit(value):
        if abs(value - state.committed.timing.offset_seconds) < 1e-9:
            return None
        return SetOffset(value)

    return LiveField(spin, state, edit), spin, state


def test_typing_previews_and_the_session_commits_once(field) -> None:
    live, spin, state = field
    spin.setValue(1.0)
    spin.setValue(2.0)
    spin.setValue(3.0)                           # three keystrokes
    assert state.doc.timing.offset_seconds == 3.0
    assert state.committed.timing.offset_seconds == 0.0
    assert live.previewing() and not state.can_undo

    live.commit()
    assert state.committed.timing.offset_seconds == 3.0
    assert not live.previewing()
    state.undo()
    assert not state.can_undo                    # one entry for the session


def test_an_edit_that_changes_nothing_never_speaks(field) -> None:
    live, spin, state = field
    spin.setValue(0.0)                           # already the value
    assert state.doc is state.committed
    live.commit()
    assert not state.can_undo and not state.is_dirty
    assert not state.axis._held                  # and the axis is free


def test_editing_finished_twice_commits_once(field) -> None:
    """Return commits, then focus-out fires editingFinished again."""
    live, spin, state = field
    spin.setValue(1.5)
    live.commit()
    live.commit()
    assert state.can_undo
    state.undo()
    assert not state.can_undo


def test_resync_yields_to_a_live_edit_and_rounds_for_an_int_box(qapp) -> None:
    from PySide6.QtWidgets import QSpinBox

    live, spin, state = None, QSpinBox(), AppState()
    spin.setRange(-500, 500)
    live = LiveField(spin, state, lambda value: None)
    live.resync(250.4)                           # seconds → ms, whole steps
    assert spin.value() == 250

    live, spin, state = None, QDoubleSpinBox(), AppState()
    spin.setRange(0.0, 10.0)
    live = LiveField(spin, state, lambda value: SetOffset(value))
    spin.setValue(4.0)                           # typing
    live.resync(9.0)                             # the window resyncs
    assert spin.value() == 4.0                   # the cursor is not fought
    live.commit()
    live.resync(9.0)                             # the edit is over
    assert spin.value() == 9.0


def test_a_live_field_is_never_grayed_out_from_under_the_cursor(field) -> None:
    live, spin, state = field
    spin.setValue(2.0)                           # typing
    live.set_enabled(False)
    assert spin.isEnabled()                      # refused while live
    live.commit()
    live.set_enabled(False)
    assert not spin.isEnabled()                  # the edit is over
    live.set_enabled(True)
    assert spin.isEnabled()


def test_a_rug_pull_hands_the_field_back(field) -> None:
    """An undo or a project load drops the preview from under the field;
    it must let go rather than sit on a number nothing is showing."""
    live, spin, state = field
    spin.setValue(1.0)
    live.commit()
    spin.setValue(2.0)                           # typing again
    assert live.previewing()
    state.undo()
    assert not live.previewing()
    live.resync(state.doc.timing.offset_seconds)
    assert spin.value() == 0.0


def test_moving_focus_ends_the_edit(qapp) -> None:
    """Only one field previews at a time, and focus is what guarantees
    it: reaching another spinbox commits the first."""
    from PySide6.QtTest import QTest

    state = AppState()
    bar = TimelineBar(state)
    bar.show()
    qapp.processEvents()
    bar.activateWindow()             # focus events need an active window
    qapp.processEvents()
    bar._offset_spin.setFocus()
    bar._offset_spin.selectAll()
    QTest.keyClicks(bar._offset_spin, "2")       # really typing in Offset
    assert state.doc.timing.offset_seconds == 2.0    # previewed
    assert not state.can_undo
    bar._swing_spin.setFocus()                   # click into Swing
    qapp.processEvents()
    assert state.committed.timing.offset_seconds == 2.0
    assert not bar._offset.previewing()
    assert state.undo_text() == "set offset"
    bar.hide()


@pytest.mark.parametrize("build", [
    lambda state: TimelineBar(state),
    lambda state: EffectsPanel(state),
    lambda state: VideoCanvasPanel(state),
])
def test_every_spinbox_is_a_live_field(build) -> None:
    """The standing rule, enforced: a number field that edits the
    document previews as you type — or, for a re-engraving field, once
    per typing pause (LiveField delay_ms). A spinbox added without a
    LiveField fails here (see docs/PATTERNS.md)."""
    state = AppState()
    state.set_measures((MeasureInfo(number=1, start=0.0,
                                    quarter_length=4.0),))
    host = build(state)
    assert {f.spin for f in host.live_fields} == \
        set(host.findChildren(QAbstractSpinBox))
