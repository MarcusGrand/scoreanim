"""The Page colours block: one command per gesture, and a display that
always re-derives from the document.

Headless — the panel is built on an AppState with no score loaded, which
is all it needs: these two colours are document-wide and know nothing
about what is engraved.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.project import SetPageColor  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.panels.page_colors import PageColorsPanel  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    state = AppState()
    return PageColorsPanel(state), state


def test_it_opens_showing_the_defaults_as_defaults(panel) -> None:
    """A fresh document stores nothing, and the block says so rather
    than showing a white it would then offer to reset."""
    p, state = panel
    assert state.doc.style.colors == {}
    assert p._swatches["background"].text() == "#ffffff (default)"
    assert p._swatches["ink"].text() == "#000000 (default)"
    assert not p._defaults["background"].isEnabled()
    assert not p._defaults["ink"].isEnabled()


def test_picking_a_colour_is_one_command_and_one_undo_entry(panel) -> None:
    p, state = panel
    p._commit("ink", "#ffffff")
    assert state.doc.style.colors == {"ink": "#ffffff"}
    assert state.can_undo
    assert state.undo_text() == "set page colour"
    assert p._swatches["ink"].text() == "#ffffff"     # no "(default)"
    assert p._defaults["ink"].isEnabled()
    # and only one entry for the one gesture (rule 8)
    state.undo()
    assert state.doc.style.colors == {}
    assert not state.can_undo


def test_default_deletes_the_key_rather_than_storing_the_default(
        panel) -> None:
    """Which is what keeps an untouched document byte-identical: the
    reset writes nothing, it removes."""
    p, state = panel
    p._commit("ink", "#ffffff")
    p._commit("ink", None)
    assert state.doc.style.colors == {}
    assert p._swatches["ink"].text() == "#000000 (default)"


def test_the_two_colours_are_independent(panel) -> None:
    p, state = panel
    p._commit("background", "#101014")
    p._commit("ink", "#f4f4f4")
    assert state.doc.style.colors == {"background": "#101014",
                                      "ink": "#f4f4f4"}
    p._commit("background", None)
    assert state.doc.style.colors == {"ink": "#f4f4f4"}
    assert p._swatches["ink"].text() == "#f4f4f4"


def test_committing_the_same_colour_again_is_not_an_undo_entry(
        panel) -> None:
    p, state = panel
    p._commit("ink", "#ffffff")
    p._commit("ink", "#ffffff")            # again, same value
    state.undo()
    assert state.doc.style.colors == {}       # one entry, not two


def test_the_display_follows_undo_and_redo(panel) -> None:
    """The resync never re-executes — execute, undo and redo all land in
    the same place and the swatches simply re-read the document."""
    p, state = panel
    p._commit("background", "#101014")
    assert p._swatches["background"].text() == "#101014"
    state.undo()
    assert p._swatches["background"].text() == "#ffffff (default)"
    assert state.doc.style.colors == {}
    state.redo()
    assert p._swatches["background"].text() == "#101014"
    assert state.doc.style.colors == {"background": "#101014"}


def test_an_unreadable_stored_value_shows_as_its_default(panel) -> None:
    """A hand-edited file: the block shows what the page will actually
    be drawn in, not the nonsense that is stored."""
    p, state = panel
    state.execute(SetPageColor("ink", "not a colour"))
    assert p._swatches["ink"].text() == "#000000"
    # the key IS there, so the reset is offered — it is how you get rid
    # of the bad value
    assert p._defaults["ink"].isEnabled()


def test_the_swatch_wears_the_colour_it_names(panel) -> None:
    p, _ = panel
    p._commit("background", "#101014")
    style = p._swatches["background"].styleSheet()
    assert "background-color: #101014" in style
    assert "color: #ffffff" in style          # light text on a dark swatch
    p._commit("background", "#f4f4f4")
    assert "color: #000000" in p._swatches["background"].styleSheet()
