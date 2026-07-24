"""Inspector dock (M1.4), offscreen: the toggles/field that moved off
the interim toolbar commit the same commands as before, the resync pass
never re-executes a command, and Follow stays transient — one shared
QAction, never resynced from the document.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDockWidget  # noqa: E402

from scoreanim.core.animation import RevealMode  # noqa: E402
from scoreanim.core.project import PresentationMode  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.inspector import Inspector  # noqa: E402


class FakePlayback(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.follow_calls: list[bool] = []

    def set_follow(self, follow: bool) -> None:
        self.follow_calls.append(follow)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def inspector(qapp):
    state = AppState()
    playback = FakePlayback()
    return Inspector(state, playback), state, playback


def test_is_a_fixed_right_dock_with_three_sections(inspector) -> None:
    dock, _, _ = inspector
    assert dock.objectName() == "Inspector"      # saveState identity (M1.8)
    assert dock.features() \
        == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
    assert dock.allowedAreas() == Qt.DockWidgetArea.RightDockWidgetArea
    assert set(dock.sections) == {"playback", "appearance", "selection"}
    assert all(s.expanded for s in dock.sections.values())


def test_follow_is_one_shared_action(inspector) -> None:
    """Menu item and inspector toggle are the SAME QAction (brief flag
    3) — the checkbox is bound both ways and cannot diverge."""
    dock, _, playback = inspector
    assert dock.follow_action.isChecked()
    dock._follow_box.setChecked(False)           # inspector side
    assert not dock.follow_action.isChecked()
    assert playback.follow_calls == [False]
    dock.follow_action.setChecked(True)          # menu side
    assert dock._follow_box.isChecked()
    assert playback.follow_calls == [False, True]


def test_follow_never_resynced_from_document(inspector) -> None:
    dock, state, _ = inspector
    dock._follow_box.setChecked(False)
    dock.sync_from_document(state.doc)
    assert not dock.follow_action.isChecked()    # transient state survives
    assert not state.can_undo                    # and no command ever ran


def test_systems_commits_presentation_mode(inspector) -> None:
    dock, state, _ = inspector
    dock._systems_box.setChecked(True)
    assert state.doc.stage.mode is PresentationMode.SYSTEM
    assert state.undo_text() == "set presentation mode"
    state.undo()
    assert state.doc.stage.mode is PresentationMode.PAGED
    dock.sync_from_document(state.doc)           # undo restores the toggle
    assert not dock._systems_box.isChecked()
    assert not state.can_undo


def test_sweep_commits_reveal_mode(inspector) -> None:
    dock, state, _ = inspector
    dock._sweep_box.setChecked(True)
    assert state.doc.style.reveal_mode is RevealMode.CONTINUOUS
    assert state.undo_text() == "set reveal mode"
    state.undo()
    assert state.doc.style.reveal_mode is RevealMode.STEPPED
    dock.sync_from_document(state.doc)
    assert not dock._sweep_box.isChecked()


def test_floor_commits_one_command_with_epsilon_guard(inspector) -> None:
    dock, state, _ = inspector
    dock._floor_spin.setValue(0.25)
    dock._commit_floor()
    assert state.doc.style.floor_opacity == 0.25
    assert state.undo_text() == "set floor opacity"
    dock._commit_floor()                         # same value → no-op
    state.undo()
    assert not state.can_undo                    # exactly one command
    dock.sync_from_document(state.doc)           # undo restores the field
    assert dock._floor_spin.value() == state.doc.style.floor_opacity


def test_sync_from_document_never_reexecutes(inspector) -> None:
    dock, state, _ = inspector
    dock._systems_box.setChecked(True)
    dock._sweep_box.setChecked(True)
    dock._floor_spin.setValue(0.1)
    dock._commit_floor()
    depth = 0
    while state.can_undo:                        # measure stack depth
        state.undo()
        depth += 1
    for _ in range(depth):
        state.redo()
    dock.sync_from_document(state.doc)           # the resync pass
    assert dock._systems_box.isChecked()
    assert dock._sweep_box.isChecked()
    assert dock._floor_spin.value() == 0.1
    for _ in range(depth):                       # resync added no command
        state.undo()
    assert not state.can_undo
    assert depth == 3
