"""The hint bar on a real MainWindow, offscreen.

The wording is pinned headless in tests/test_hints.py; what is pinned
here is the WIRING — that a real click on a real score produces true
gestures, that the bar goes back to naming the recording when the
selection clears, and that a status message covers the hint and then
gives it back.

That last one is the whole reason `HintBar.message` exists: Qt hides the
bar's normal widgets while a TEMPORARY message shows and puts them back
when it expires, so a message with no timeout would bury the hint
forever. The last test is the pin that nobody adds an untimed
`showMessage` back.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.editing.hints import (DELETE, FLIP_STEM,  # noqa: E402
                                          MOVE, NO_RECORDING, RETIME)
from scoreanim.core.project.document import FileRef  # noqa: E402
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.ui.main_window import MainWindow  # noqa: E402

FIXTURE = (Path(__file__).parent.parent / "testdata" / "testscore.musicxml")
UI_DIR = Path(__file__).parent.parent / "scoreanim" / "ui"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(qapp):
    w = MainWindow()
    w.files.open_score(FIXTURE)
    return w


def _select(window, kind: ElementKind):
    """Select the first element of this kind, the way a click would end."""
    for item in window._scenes.items.values():
        if item.identity is not None and item.identity.kind is kind:
            window.app_state.set_selection(item.identity)
            return item.identity
    pytest.skip(f"no {kind} in the fixture")


# -- with nothing selected --------------------------------------------------

def test_idle_names_the_recording(window):
    window.app_state.set_selection(None)
    assert window.hints.text == NO_RECORDING

    window.app_state.bind_audio(FileRef(path="/tmp/take3.wav", sha256="x"))
    assert window.hints.text == "Recording: take3.wav"
    window.app_state.bind_audio(None)
    assert window.hints.text == NO_RECORDING


# -- with something selected ------------------------------------------------

def test_a_note_says_what_it_is_and_what_f_does(window):
    _select(window, ElementKind.NOTEHEAD)
    hint = window.hints.text
    assert hint.startswith("Note · ")
    assert " · m. 1" in hint
    assert FLIP_STEM in hint
    # a note is a reveal anchor, so it has no onset line to drag — the
    # bar must not offer one
    assert RETIME not in hint


def test_a_dynamic_offers_the_drags_it_really_has(window):
    _select(window, ElementKind.DYNAMIC)
    hint = window.hints.text
    assert hint.startswith("Dynamic · ")
    assert MOVE in hint            # nudgeable
    assert RETIME in hint          # the onset line is drawn for it
    assert FLIP_STEM not in hint


def test_a_barline_offers_the_break_with_this_platforms_keys(window):
    _select(window, ElementKind.BARLINE)
    hint = window.hints.text
    native = window.break_action.action.shortcut().toString(
        QKeySequence.SequenceFormat.NativeText)
    assert hint.startswith("Barline · m. ")
    assert native in hint
    assert "system" in hint


def test_the_hint_follows_the_selection_and_gives_it_back(window):
    _select(window, ElementKind.NOTEHEAD)
    assert window.hints.text.startswith("Note")
    window.app_state.set_selection(None)
    assert window.hints.text == NO_RECORDING


def test_a_document_change_re_derives_the_gestures(window):
    """Deleting is a document change that disables its own gesture. The
    delete clears the selection, so the hint is checked on the way in."""
    _select(window, ElementKind.DYNAMIC)
    assert DELETE in window.hints.text
    window.delete_action.trigger()
    assert window.app_state.selection is None
    assert window.hints.text == NO_RECORDING
    window.app_state.undo()


# -- messages over the hint -------------------------------------------------

def test_a_message_covers_the_hint_and_the_hint_comes_back(window):
    # shown on purpose: QStatusBar only hides a normal widget that is
    # currently visible, so the swap this test is about does not happen
    # at all on a window nobody ever showed
    window.show()
    _select(window, ElementKind.NOTEHEAD)
    hint = window.hints.text
    label = window.statusBar().findChild(type(window.hints._label),
                                         "HintBar")

    window.hints.message("export: 40 / 200 frames")
    assert window.statusBar().currentMessage() == "export: 40 / 200 frames"
    assert not label.isVisible()          # Qt hides it under a message

    window.statusBar().clearMessage()     # what the timeout does
    assert label.isVisible()
    assert window.hints.text == hint
    window.hide()


def test_the_hint_elides_rather_than_widening_the_window(window):
    _select(window, ElementKind.DYNAMIC)
    label = window.hints._label
    label.setFixedWidth(60)
    label.set_hint(window.hints.text)
    assert len(label.text()) < len(label.full_text())
    assert label.minimumSizeHint().width() < 200


def test_nobody_bypasses_the_hint_bar_with_an_untimed_message():
    """An untimed showMessage never expires, so the hint would never
    come back. Every status message goes through HintBar.message."""
    offenders = [path.name for path in sorted(UI_DIR.glob("*.py"))
                 if path.name != "hint_bar.py"
                 and "showMessage" in path.read_text()]
    assert offenders == []
