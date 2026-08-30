"""The tooltip mechanism (E2, ui/tips.py): the shortcut suffix, and the
swap a disabled control makes.

Offscreen widgets, because a QAction and a QWidget are exactly what the
module is written against — but nothing here draws or shows anything.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QAction, QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from scoreanim.ui import tips  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_a_described_control_shows_its_sentence(qapp) -> None:
    button = QPushButton()
    tips.describe(button, "Bring every deleted object back")
    assert button.toolTip() == "Bring every deleted object back"
    assert tips.live_tip(button) == "Bring every deleted object back"


def test_an_action_tooltip_carries_its_key(qapp) -> None:
    """The key is read off the action, so the two cannot drift apart."""
    action = QAction("Save")
    action.setShortcut(QKeySequence.StandardKey.Save)
    tips.describe_action(action, "Save the project")
    native = action.shortcut().toString(
        QKeySequence.SequenceFormat.NativeText)
    assert action.toolTip() == f"Save the project ({native})"
    assert native            # the platform writes something for Ctrl+S


def test_an_action_with_no_key_gets_the_sentence_alone(qapp) -> None:
    action = QAction("About")
    tips.describe_action(action, "Version and credits")
    assert action.toolTip() == "Version and credits"


def test_two_keys_for_one_gesture_name_only_the_first(qapp) -> None:
    """Delete and Backspace are one key to most people; a tooltip
    naming both would read as two things to press."""
    action = QAction("Delete")
    action.setShortcuts([QKeySequence("Backspace"), QKeySequence("Del")])
    tips.describe_action(action, "Hide the selected object")
    assert action.toolTip().count("(") == 1


def test_a_gated_control_says_why_and_gets_its_sentence_back(qapp) -> None:
    button = QPushButton()
    tips.describe(button, "Render the animation to a video file")
    tips.gate(button, False, tips.NEEDS_SCORE)
    assert not button.isEnabled()
    assert button.toolTip() == tips.NEEDS_SCORE
    tips.gate(button, True, tips.NEEDS_SCORE)
    assert button.isEnabled()
    assert button.toolTip() == "Render the animation to a video file"


def test_no_reason_leaves_the_sentence_showing(qapp) -> None:
    """A control grayed for something already obvious on screen keeps
    saying what it does."""
    button = QPushButton()
    tips.describe(button, "Zoom in")
    tips.gate(button, False, "")
    assert not button.isEnabled()
    assert button.toolTip() == "Zoom in"


def test_gate_works_on_an_action_too(qapp) -> None:
    action = QAction("Export Video…")
    tips.describe(action, "Render the animation to a video file")
    tips.gate(action, False, tips.NEEDS_SCORE)
    assert action.toolTip() == tips.NEEDS_SCORE
