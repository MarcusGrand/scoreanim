"""The Help menu and its shortcut sheet (B3), offscreen.

The point of the sheet is that it is HARVESTED: the checks below aim at
that, not at a copy of today's key table. They assert the keys the brief
names (Space, Ctrl+E, F5) reach the dialog from the menus that own them,
that nothing in it has an empty key column, and that a shortcut added
after the window was built — as the Score menu's break actions are, on
load — is picked up because the sheet is built when it opens.

Menus are read through the refs `MainMenus` holds, never through
`QAction.menu()`: that call deletes the menu it returns (the quirk
`ui/menus.py` documents, which this dialog was written around).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QAction, QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.ui import about_dialog  # noqa: E402
from scoreanim.ui.main_window import MainWindow  # noqa: E402
from scoreanim.ui.shortcuts_dialog import (GESTURES, ShortcutsDialog,
                                           harvest)  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(qapp):
    return MainWindow()


def _texts(menu) -> list[str]:
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def _native(key) -> str:
    return QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)


def _rows(groups) -> dict[str, str]:
    return {row.label: row.keys for group in groups for row in group.rows}


def test_help_menu_is_last_and_holds_the_two_entries(window) -> None:
    assert [a.text() for a in window.menuBar().actions()] \
        == ["&File", "&Edit", "&View", "&Score", "&Playback", "&Help"]
    assert [m.title() for m in window.menus.all_menus] \
        == ["&File", "&Edit", "&View", "&Score", "&Playback", "&Help"]
    assert _texts(window.menus.help_menu) \
        == ["Keyboard Shortcuts…", "About ScoreAnim"]


def test_harvest_groups_by_menu(window) -> None:
    """One group per menu that has a key in it, in bar order, with the
    mnemonic marker stripped off the heading. Score is empty until a
    load and Help carries no key, so neither is a heading here."""
    groups = harvest(window.menus.all_menus)
    assert [group.title for group in groups] \
        == ["File", "Edit", "View", "Playback"]
    assert all(group.rows for group in groups)


def test_the_brief_s_three_keys_are_in_the_sheet(window) -> None:
    rows = _rows(harvest(window.menus.all_menus))
    assert rows["Export Video…"] == _native("Ctrl+E")
    assert rows["Reload Tempo"] == _native("F5")
    assert rows["Play"] == _native("Space")
    # keys are written the way this platform writes them
    assert rows["Open Score…"] \
        == _native(QKeySequence.StandardKey.Open)


def test_no_row_has_an_empty_key_column(window) -> None:
    dialog = ShortcutsDialog(window.menus.all_menus, window)
    assert dialog.groups
    for group in dialog.groups:
        assert group.rows, group.title
        for row in group.rows:
            assert row.label.strip(), group.title
            assert row.keys.strip(), row.label
    dialog.deleteLater()


def test_actions_without_a_shortcut_stay_out(window) -> None:
    """Texts… and Open Project's recents submenu have no key, so they
    are not in the sheet — the menu still has them."""
    rows = _rows(harvest(window.menus.all_menus))
    assert "Texts…" in _texts(window.menus.edit_menu)
    assert "Texts…" not in rows
    assert "Open Recent" in _texts(window.menus.file_menu)
    assert "Open Recent" not in rows


def test_the_sheet_is_built_when_it_opens(window) -> None:
    """A key that appears after the window was built — the Score menu
    fills on load — is in the next sheet, because the sheet reads the
    bar rather than a list captured at startup."""
    late = QAction("Break Here", window)
    late.setShortcut(QKeySequence("Ctrl+Return"))
    window.menus.score_menu.addAction(late)
    try:
        rows = _rows(harvest(window.menus.all_menus))
        assert rows["Break Here"] == _native("Ctrl+Return")
    finally:
        window.menus.score_menu.removeAction(late)
    assert "Break Here" not in _rows(harvest(window.menus.all_menus))


def test_a_renaming_action_keeps_its_name_in_the_sheet(window) -> None:
    """Undo says "Undo import tempo (…)" in the Edit menu once there is
    something to undo. The sheet calls it Undo, because a key belongs
    under a name that does not move."""
    undo = window.menus.undo_action
    undo.setText("Undo import tempo (testscore.tempo)")
    try:
        rows = _rows(harvest(window.menus.all_menus))
        assert rows["Undo"] == _native(QKeySequence.StandardKey.Undo)
    finally:
        undo.setText("Undo")


def test_gestures_are_the_last_group(window) -> None:
    """The half Qt cannot report, hand-kept and shown under the menus."""
    dialog = ShortcutsDialog(window.menus.all_menus, window)
    assert dialog.groups[-1] is GESTURES
    labels = {row.label for row in GESTURES.rows}
    assert "Move the selected object" in labels     # drag to nudge
    assert "Edit a text where it sits" in labels    # double-click
    assert "Hide a stave, in this system or everywhere" in labels
    dialog.deleteLater()


def test_about_names_the_app_and_the_project_format() -> None:
    from scoreanim.core.project import PROJECT_VERSION
    text = about_dialog.about_text()
    assert "ScoreAnim" in text
    assert f"v{PROJECT_VERSION}" in text
    assert "Verovio" in text and "music21" in text
