"""AppState + TimeAxis (offscreen Qt): preview/commit lifecycle, undo
wiring, shared-axis math. Painting stays visually verified; the logic
views depend on lives here."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.project import (AddTempoEvent, FileRef,  # noqa: E402
                                    MoveTempoEvent, ProjectDoc, SetOffset,
                                    TimingConfig)
from scoreanim.core.timing import TempoEvent  # noqa: E402
from scoreanim.ui.app_state import AppState, TimeAxis  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def state(qapp) -> AppState:
    return AppState()


def _count(signal) -> list:
    hits: list = []
    signal.connect(lambda *args: hits.append(args))
    return hits


# -- TimeAxis -----------------------------------------------------------------

def test_axis_duration_resets_window(qapp) -> None:
    axis = TimeAxis()
    hits = _count(axis.changed)
    axis.set_duration(34.6)
    assert (axis.t0, axis.t1, axis.duration) == (0.0, 34.6, 34.6)
    assert len(hits) == 1
    axis.set_duration(34.6)                    # no-op: same duration
    assert len(hits) == 1


def test_axis_visible_clamps(qapp) -> None:
    axis = TimeAxis()
    axis.set_duration(30.0)
    axis.set_visible(-5.0, 10.0)               # left clamp
    assert (axis.t0, axis.t1) == (0.0, 15.0)
    axis.set_visible(25.0, 40.0)               # right clamp keeps span
    assert (axis.t0, axis.t1) == (15.0, 30.0)
    axis.set_visible(10.0, 10.1)               # min span
    assert axis.span == pytest.approx(0.5)
    axis.set_visible(-10.0, 100.0)             # span capped at duration
    assert (axis.t0, axis.t1) == (0.0, 30.0)


def test_axis_zoom_keeps_anchor_and_pan_clamps(qapp) -> None:
    axis = TimeAxis()
    axis.set_duration(30.0)
    axis.zoom(2.0, anchor_t=10.0)
    assert (axis.t0, axis.t1) == (5.0, 20.0)
    # anchor stays at the same fraction of the window
    assert (10.0 - axis.t0) / axis.span == pytest.approx(1 / 3)
    axis.pan(-100.0)
    assert axis.t0 == 0.0 and axis.span == pytest.approx(15.0)


def test_axis_x_t_inverse(qapp) -> None:
    axis = TimeAxis()
    axis.set_duration(30.0)
    axis.set_visible(5.0, 20.0)
    for t in (5.0, 9.3, 20.0):
        assert axis.t_of(axis.x_of(t, 800), 800) == pytest.approx(t)
    assert axis.x_of(5.0, 800) == 0.0
    assert axis.x_of(20.0, 800) == 800.0


# -- AppState document flow ----------------------------------------------------

def test_execute_emits_once_and_updates_doc(state) -> None:
    hits = _count(state.document_changed)
    assert state.execute(AddTempoEvent(8.0, 100.0))
    assert len(hits) == 1
    assert TempoEvent(8.0, 100.0) in state.doc.timing.tempo_events
    assert state.can_undo and not state.can_redo


def test_failed_execute_emits_status_not_document(state) -> None:
    doc_hits = _count(state.document_changed)
    status_hits = _count(state.status)
    assert not state.execute(AddTempoEvent(0.0, 100.0))   # duplicate beat 0
    assert not doc_hits
    assert status_hits and "0.0" in status_hits[0][0]
    assert not state.can_undo


def test_preview_commit_is_one_undo_entry(state) -> None:
    committed = state.doc
    hits = _count(state.document_changed)
    # drag: many previews, always against the committed doc
    for bpm in (121.0, 125.0, 130.0):
        state.preview(MoveTempoEvent(0.0, 0.0, bpm))
        assert state.doc.timing.tempo_events[0].bpm == bpm
    assert len(hits) == 3
    assert not state.can_undo                  # nothing pushed yet
    state.commit(MoveTempoEvent(0.0, 0.0, 130.0))
    assert state.doc.timing.tempo_events[0].bpm == 130.0
    state.undo()
    assert state.doc == committed              # ONE undo undoes the gesture


def test_invalid_preview_is_ignored(state) -> None:
    hits = _count(state.document_changed)
    state.preview(MoveTempoEvent(3.0, 4.0, 100.0))        # no such event
    assert not hits
    assert state.doc == ProjectDoc()


def test_cancel_preview_snaps_back(state) -> None:
    state.preview(SetOffset(9.0))
    assert state.doc.timing.offset_seconds == 9.0
    state.cancel_preview()
    assert state.doc.timing.offset_seconds == 0.0
    assert not state.can_undo


def test_undo_redo_round_trip(state) -> None:
    state.execute(SetOffset(2.0))
    state.execute(SetOffset(3.0))
    state.undo()
    assert state.doc.timing.offset_seconds == 2.0
    assert state.undo_text() == "set offset" and state.can_redo
    state.redo()
    assert state.doc.timing.offset_seconds == 3.0


def test_reset_document_clears_stack(state) -> None:
    state.execute(SetOffset(2.0))
    fresh = ProjectDoc(timing=TimingConfig(offset_seconds=7.0))
    state.reset_document(fresh)
    assert state.doc == fresh
    assert not state.can_undo and not state.can_redo and not state.is_dirty


def test_bind_audio_outside_stack_but_dirty(state) -> None:
    ref = FileRef(path="/audio/take.wav", sha256=None)
    state.bind_audio(ref)
    assert state.doc.audio == ref
    assert not state.can_undo                  # not undoable (ruling)
    assert state.is_dirty
    state.mark_saved()
    assert not state.is_dirty


def test_playhead_and_seek_signals(state) -> None:
    heads = _count(state.playhead_changed)
    seeks = _count(state.seek_requested)
    state.set_playhead(3.25)
    state.request_seek(7.5)
    assert heads == [(3.25,)] and seeks == [(7.5,)]
    assert state.playhead == 3.25
