"""Arrow-key seeking (D1 revision), offscreen.

Three things to hold down. The amounts and the keys; the clamp in
`PlaybackController.seek_by`; and — the reason this file drives real
key presses rather than triggering actions — who gets an arrow when two
things want it. A window shortcut normally beats the focused widget, so
"the Tempo box still takes its arrows" and "a selected note still
nudges" are claims about Qt's ShortcutOverride path, and only a real
keystroke through a real window tests them.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QDoubleSpinBox, QMainWindow,
                               QVBoxLayout, QWidget)

from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing import TempoMap
from scoreanim.core.timing.tempo_map import TempoEvent
from scoreanim.ui.playback import PlaybackController
from scoreanim.ui.seek_keys import JUMP_SECONDS, STEP_SECONDS, SeekKeys
from scoreanim.ui.stage_view import StageView


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakePlayback:
    """Records what the keys asked for."""
    def __init__(self):
        self.deltas = []

    def seek_by(self, delta):
        self.deltas.append(delta)


class _FakeApplier:
    def set_timing(self, tempo_map, swing): pass
    def set_audio(self, peaks, offset_seconds): pass
    def refresh(self, t): pass
    def apply_at(self, t): return 0
    def current_page(self): return 1
    def current_system(self): return 1


def _controller():
    """8 seconds of score and no recording, so the wall clock is
    master and a seek is exact."""
    controller = PlaybackController()
    measures = tuple(MeasureInfo(number=i + 1, start=i * 4.0,
                                 quarter_length=4.0) for i in range(4))
    controller.set_animation(_FakeApplier(), measures)
    controller.set_timing_config(0.0, TempoMap([TempoEvent(0.0, 120.0)]))
    return controller


# -- the actions themselves ------------------------------------------------

def test_the_four_keys_and_what_they_are_worth(qapp) -> None:
    playback = _FakePlayback()
    keys = SeekKeys(playback)
    shortcuts = [a.shortcut().toString() for a in keys.actions]
    assert shortcuts == [QKeySequence(Qt.Key.Key_Left).toString(),
                         QKeySequence(Qt.Key.Key_Right).toString(),
                         QKeySequence("Shift+Left").toString(),
                         QKeySequence("Shift+Right").toString()]
    for action in keys.actions:
        action.trigger()
    assert keys.actions[0].parent() is keys       # held alive by the owner
    assert playback.deltas == [-STEP_SECONDS, +STEP_SECONDS,
                               -JUMP_SECONDS, +JUMP_SECONDS]


def test_go_to_start_is_not_duplicated_here(qapp) -> None:
    """Home belongs to the strip's own Go to Start action; a second
    action on the same key would be two objects behind one press."""
    keys = SeekKeys(_FakePlayback())
    assert len(keys.actions) == 4
    assert not any(a.shortcut() == QKeySequence(Qt.Key.Key_Home)
                   for a in keys.actions)


# -- the clamp -------------------------------------------------------------

def test_seek_by_moves_relative_to_the_playhead(qapp) -> None:
    controller = _controller()
    controller.seek(3.0)
    controller.seek_by(+1.0)
    assert controller._clock.now_seconds() == pytest.approx(4.0)
    controller.seek_by(-5.0)
    assert controller._clock.now_seconds() == pytest.approx(0.0)


def test_seek_by_stays_inside_the_timeline(qapp) -> None:
    controller = _controller()                    # 8.0 s of score
    controller.seek(7.5)
    controller.seek_by(+5.0)
    assert controller._clock.now_seconds() == pytest.approx(8.0)
    controller.seek(0.5)
    controller.seek_by(-5.0)
    assert controller._clock.now_seconds() == pytest.approx(0.0)


# -- who gets the arrow ----------------------------------------------------

class _Host(QMainWindow):
    """A window with the seek actions registered the way ui/menus.py
    registers them, plus the two widgets that compete for an arrow."""

    def __init__(self, playback):
        super().__init__()
        self.keys = SeekKeys(playback, self)
        for action in self.keys.actions:
            self.addAction(action)
        self.spin = QDoubleSpinBox()
        self.stage = StageView()
        body = QWidget(self)
        column = QVBoxLayout(body)
        column.addWidget(self.spin)
        column.addWidget(self.stage)
        self.setCentralWidget(body)


@pytest.fixture
def host(qapp):
    playback = _FakePlayback()
    window = _Host(playback)
    window.show()
    QTest.qWaitForWindowExposed(window)
    yield window, playback
    window.close()


def test_arrows_seek_from_anywhere_in_the_window(host) -> None:
    window, playback = host
    window.stage.setFocus()
    QTest.keyClick(window.stage, Qt.Key.Key_Right)
    QTest.keyClick(window.stage, Qt.Key.Key_Left,
                   Qt.KeyboardModifier.ShiftModifier)
    assert playback.deltas == [+STEP_SECONDS, -JUMP_SECONDS]


def test_a_number_field_keeps_its_arrows(host) -> None:
    """Qt hands the key to a spin box's line edit through
    ShortcutOverride, so typing in Tempo never seeks."""
    window, playback = host
    window.spin.setFocus()
    qapp = QApplication.instance()
    qapp.processEvents()
    for key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home):
        QTest.keyClick(window.spin, key)
    assert playback.deltas == []


def test_the_stage_keeps_its_arrows_while_something_is_nudgeable(host) -> None:
    """Arrow keys have nudged the selection since M3.2; that is the
    more specific meaning, so it wins while a target exists."""
    window, playback = host
    nudges = []
    window.stage.nudge_key.connect(lambda dx, dy: nudges.append((dx, dy)))
    window.stage.nudge_target = lambda: "some-element-id"
    window.stage.setFocus()
    QTest.keyClick(window.stage, Qt.Key.Key_Right)
    assert playback.deltas == []
    assert len(nudges) == 1

    # deselect and the same key seeks again
    window.stage.nudge_target = lambda: None
    QTest.keyClick(window.stage, Qt.Key.Key_Right)
    assert playback.deltas == [+STEP_SECONDS]
    assert len(nudges) == 1
