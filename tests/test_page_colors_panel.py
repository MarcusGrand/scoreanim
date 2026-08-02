"""The Page block: light or dark, one command per click, and a display
that always re-derives from the document.

Headless — the panel is built on an AppState with no score loaded, which
is all it needs: the mode is document-wide and knows nothing about what
is engraved.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import DARK, LIGHT  # noqa: E402
from scoreanim.core.project import SetColorMode  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.panels.page_colors import PageColorsPanel  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    state = AppState()
    return PageColorsPanel(state), state


def test_it_opens_on_light_with_nothing_stored(panel) -> None:
    p, state = panel
    assert state.doc.style.colors == {}
    assert p._buttons[LIGHT].isChecked()
    assert not p._buttons[DARK].isChecked()


def test_choosing_dark_is_one_command_and_one_undo_entry(panel) -> None:
    p, state = panel
    p._commit(DARK)
    assert state.doc.style.colors == {"mode": "dark"}
    assert state.can_undo
    assert state.undo_text() == "set colour mode"
    assert p._buttons[DARK].isChecked()
    state.undo()
    assert state.doc.style.colors == {}
    assert not state.can_undo             # one entry for the one gesture


def test_choosing_light_removes_the_key_rather_than_storing_it(
        panel) -> None:
    """Light is the default, and the default stores nothing at all —
    which is what keeps an untouched document byte-identical."""
    p, state = panel
    p._commit(DARK)
    p._commit(LIGHT)
    assert state.doc.style.colors == {}
    assert p._buttons[LIGHT].isChecked()


def test_choosing_the_mode_already_in_force_is_not_an_undo_entry(
        panel) -> None:
    p, state = panel
    p._commit(LIGHT)                      # already light
    assert not state.can_undo
    p._commit(DARK)
    p._commit(DARK)                       # again, same mode
    state.undo()
    assert state.doc.style.colors == {}   # one entry, not two


def test_the_display_follows_undo_and_redo(panel) -> None:
    """The resync never re-executes — execute, undo and redo all land in
    the same place and the buttons simply re-read the document."""
    p, state = panel
    p._commit(DARK)
    assert p._buttons[DARK].isChecked()
    state.undo()
    assert p._buttons[LIGHT].isChecked()
    state.redo()
    assert p._buttons[DARK].isChecked()
    assert state.doc.style.colors == {"mode": "dark"}


def test_an_unreadable_stored_mode_shows_as_light(panel) -> None:
    """A hand-edited file: the block shows what the page will actually
    be drawn in, not the nonsense that is stored."""
    p, state = panel
    state.execute(SetColorMode("midnight"))
    assert p._buttons[LIGHT].isChecked()
    # and clicking Dark from there still works — the guard compares what
    # is IN FORCE (light), not what is stored
    p._commit(DARK)
    assert state.doc.style.colors == {"mode": "dark"}
