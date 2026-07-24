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
    opened: list[str] = []
    parts_menu = PartsMenu(menu, state, None,
                           lambda: opened.append("setup"),
                           lambda: opened.append("groups"),
                           lambda: opened.append("names"))
    parts_menu.rebuild(PARTS)
    return parts_menu, state, menu, opened


def _sync(parts_menu: PartsMenu, state: AppState) -> None:
    """What the window's style diff does per part on document change."""
    for pid in parts_menu.part_ids():
        parts_menu.sync_checks(pid, state.doc.style.parts.get(pid))


def _checked(actions: dict) -> list:
    return [key for key, action in actions.items() if action.isChecked()]


def test_rebuild_static_head_and_part_submenus(built) -> None:
    parts_menu, _, menu, opened = built
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts == ["Score Setup…", "Staff Groups…", "Part Names…",
                     "Hide Empty Staves", "Flute", "Viola"]
    for action in menu.actions()[:3]:
        action.trigger()
    assert opened == ["setup", "groups", "names"]
    assert parts_menu.part_ids() == (P1, P2)
    # fresh build: No Color and the default effect are the checked rows
    assert _checked(parts_menu._color_actions[P1]) == [None]
    assert _checked(parts_menu._effect_actions[P1]) == [None]


def test_swatch_commits_and_checks_track_undo_redo(built) -> None:
    parts_menu, state, _, _ = built
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


def test_effect_commits_and_checks_track_undo_redo(built) -> None:
    parts_menu, state, _, _ = built
    names = [k for k in parts_menu._effect_actions[P2] if k is not None]
    assert names                       # registry enumerates the presets
    parts_menu._effect_actions[P2][names[0]].trigger()
    assert state.doc.style.parts[P2].effect == names[0]
    assert state.undo_text() == "set part effect"
    _sync(parts_menu, state)
    assert _checked(parts_menu._effect_actions[P2]) == [names[0]]
    state.undo()
    _sync(parts_menu, state)
    assert _checked(parts_menu._effect_actions[P2]) == [None]
    state.redo()
    _sync(parts_menu, state)
    assert _checked(parts_menu._effect_actions[P2]) == [names[0]]


def test_custom_color_accepted_commits_and_checks(built, monkeypatch) -> None:
    parts_menu, state, _, _ = built
    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor("#123456"))
    parts_menu._color_actions[P1]["custom"].trigger()
    assert state.doc.style.parts[P1].color == "#123456"
    _sync(parts_menu, state)
    assert _checked(parts_menu._color_actions[P1]) == ["custom"]


def test_custom_color_cancelled_restores_checks(built, monkeypatch) -> None:
    parts_menu, state, _, _ = built
    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor())    # invalid = cancelled
    parts_menu._color_actions[P1]["custom"].trigger()
    assert not state.can_undo                        # no command ran
    assert _checked(parts_menu._color_actions[P1]) == [None]


def test_hide_staves_commits_and_resync_never_reexecutes(built) -> None:
    parts_menu, state, menu, _ = built
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
