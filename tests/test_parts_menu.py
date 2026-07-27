"""Score-menu dynamic content (M1.6), offscreen: the extracted builder
populates the static head + per-part submenus, triggers execute the
same commands as before, checkmarks re-derive from the document (so
they track undo/redo), and Custom… cancelled restores check state
without running a command — the scripted half of the brief's verify
(the interactive tint-and-undo run is done by hand).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from scoreanim.core.score.identity import PartId  # noqa: E402
from scoreanim.core.score.musicxml_prep import PartInfo  # noqa: E402
from scoreanim.ui import parts_menu as parts_menu_module  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.parts_menu import (PART_COLORS, PartsMenu,  # noqa: E402
                                     QColorDialog)

PARTS = (PartInfo(0, PartId("P1"), "Flute", 1, 1),
         PartInfo(1, PartId("P2"), "Viola", 1, 2))
P1, P2 = PartId("P1"), PartId("P2")


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def built(qapp):
    state = AppState()
    menu = QMenu()
    parts_menu = PartsMenu(menu, state, None)
    parts_menu.rebuild(PARTS)
    return parts_menu, state, menu


class _StubDialog:
    """Stands in for a real QDialog: records the parts it was handed and
    never enters a modal loop."""

    opened: list = []

    def __init__(self, app_state, parts=None, parent=None,
                 parts_provider=None) -> None:
        _StubDialog.opened.append(
            tuple(parts) if parts is not None else tuple(parts_provider()))

    def exec(self) -> None:
        pass


@pytest.fixture
def stub_dialogs(monkeypatch):
    """M3.0 (BACKLOG 9b): the three part-shaped dialogs are opened from
    this module now, so the test patches them where they are looked up."""
    _StubDialog.opened = []
    for name in ("ScoreSetupDialog", "StaffGroupsDialog", "PartNamesDialog"):
        monkeypatch.setattr(parts_menu_module, name, _StubDialog)
    return _StubDialog.opened


def _sync(parts_menu: PartsMenu, state: AppState) -> None:
    """What the window's style diff does per part on document change."""
    for pid in parts_menu.part_ids():
        parts_menu.sync_checks(pid, state.doc.style.parts.get(pid))


def _checked(actions: dict) -> list:
    return [key for key, action in actions.items() if action.isChecked()]


def test_rebuild_static_head_and_part_submenus(built, stub_dialogs) -> None:
    parts_menu, _, menu = built
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts == ["Score Setup…", "Staff Groups…", "Part Names…",
                     "Hide Empty Staves",
                     "Hide Empty Staves on First System",
                     "Flute", "Viola"]
    for action in menu.actions()[:3]:
        action.trigger()
    # each of the three head items opens its dialog, on the parts THIS
    # menu was rebuilt with — the window holds no parts tuple any more
    assert stub_dialogs == [PARTS, PARTS, PARTS]
    assert parts_menu.part_ids() == (P1, P2)
    # fresh build: No Color is the checked row
    assert _checked(parts_menu._color_actions[P1]) == [None]


def test_dialogs_no_op_before_a_load(qapp, stub_dialogs) -> None:
    """The guard that lived on the window: no parts, no dialog."""
    parts_menu = PartsMenu(QMenu(), AppState(), None)
    parts_menu.open_score_setup()
    parts_menu.open_staff_groups()
    parts_menu.open_part_names()
    assert stub_dialogs == []


def test_rebuild_refreshes_the_parts_the_dialogs_see(built,
                                                     stub_dialogs) -> None:
    """A part rename re-engraves and calls rebuild() with the effective
    names; Part Names… is a PROVIDER, so it must show the new ones."""
    parts_menu, _, _ = built
    renamed = (PartInfo(0, P1, "Fl.", 1, 1), PartInfo(1, P2, "Vla.", 1, 2))
    parts_menu.rebuild(renamed)
    parts_menu.open_part_names()
    assert stub_dialogs == [renamed]


def test_swatch_commits_and_checks_track_undo_redo(built) -> None:
    parts_menu, state, _ = built
    swatch = PART_COLORS[0]
    parts_menu._color_actions[P1][swatch].trigger()
    assert state.doc.style.parts[P1].color == swatch
    assert state.undo_text() == "set part color"
    _sync(parts_menu, state)
    assert _checked(parts_menu._color_actions[P1]) == [swatch]
    assert _checked(parts_menu._color_actions[P2]) == [None]  # untouched
    state.undo()
    _sync(parts_menu, state)
    assert _checked(parts_menu._color_actions[P1]) == [None]
    state.redo()
    _sync(parts_menu, state)
    assert _checked(parts_menu._color_actions[P1]) == [swatch]


def test_effect_radio_group_dropped_part_rules_survive(built) -> None:
    """M4 (brief F5): the per-part effect radio group is gone — no
    submenu entry mentions an effect — but a part rule's effect in the
    document is untouched by the menu machinery (honored and
    round-tripped until M3's Selection panel makes it authorable)."""
    from scoreanim.core.animation import ElementStyle
    from scoreanim.core.project import SetPartEffect

    parts_menu, state, menu = built
    assert not hasattr(parts_menu, "_effect_actions")
    # keep the submenu's owning action referenced while reading it —
    # a temporary wrapper from a discarded generator takes the C++
    # submenu down with it (the shiboken-lifetime gotcha)
    viola = next(a for a in menu.actions() if a.text() == "Viola")
    assert not any("ffect" in a.text() for a in viola.menu().actions())
    # a part effect rule still lives in the doc and survives color sync
    state.execute(SetPartEffect(P2, "pop"))
    _sync(parts_menu, state)
    assert state.doc.style.parts[P2] == ElementStyle(effect="pop")


def test_custom_color_accepted_commits_and_checks(built, monkeypatch) -> None:
    parts_menu, state, _ = built
    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor("#123456"))
    parts_menu._color_actions[P1]["custom"].trigger()
    assert state.doc.style.parts[P1].color == "#123456"
    _sync(parts_menu, state)
    assert _checked(parts_menu._color_actions[P1]) == ["custom"]


def test_custom_color_cancelled_restores_checks(built, monkeypatch) -> None:
    parts_menu, state, _ = built
    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor())    # invalid = cancelled
    parts_menu._color_actions[P1]["custom"].trigger()
    assert not state.can_undo                        # no command ran
    assert _checked(parts_menu._color_actions[P1]) == [None]


def test_hide_staves_commits_and_resync_never_reexecutes(built) -> None:
    parts_menu, state, menu = built
    hide = next(a for a in menu.actions()
                if a.text() == "Hide Empty Staves")
    initial = state.doc.hide_empty_staves
    assert hide.isChecked() == initial
    hide.trigger()
    assert state.doc.hide_empty_staves != initial
    assert state.undo_text() in ("hide empty staves", "show empty staves")
    state.undo()
    parts_menu.sync_from_document(state.doc)         # the resync pass
    assert hide.isChecked() == state.doc.hide_empty_staves
    assert not state.can_undo                        # resync added nothing


def test_hide_first_system_commits_and_enables_with_parent(built) -> None:
    parts_menu, state, menu = built
    first = next(a for a in menu.actions()
                 if a.text() == "Hide Empty Staves on First System")
    assert first.isEnabled() == state.doc.hide_empty_staves
    assert not first.isChecked()                     # convention default
    first.trigger()
    assert state.doc.hide_first_system is True
    assert state.undo_text() == "hide empty staves on first system"
    state.undo()
    parts_menu.sync_from_document(state.doc)
    assert not first.isChecked()
    assert not state.can_undo
    # the toggle enables/disables with its parent option
    hide = next(a for a in menu.actions()
                if a.text() == "Hide Empty Staves")
    hide.trigger()                                   # flip hide_empty_staves
    parts_menu.sync_from_document(state.doc)
    assert first.isEnabled() == state.doc.hide_empty_staves
