"""M6.6 — the layout zone, on a real MainWindow, offscreen.

BACKLOG 17 built as a re-home, so what is pinned here is that it IS one:
the buttons carry the SAME QAction objects the Score menu holds, which is
what makes divergence structurally impossible rather than merely unlikely.
A test that checked "the button is enabled when the action is" would pass
just as well over a parallel implementation; these check identity.

D10's question — whether `_STATE_VERSION` must bump so a stored layout
predating this dock does not place it badly — is answered by measurement
here rather than assumed, because bumping discards every user's saved
window layout.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.editing.page_breaks import (  # noqa: E402
    NO_SELECTION as PAGE_NO_SELECTION)
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.ui.main_window import MainWindow  # noqa: E402
from scoreanim.ui.window_state import (_DOCK_STATE,  # noqa: E402
                                       _STATE_VERSION, restore_window_state,
                                       save_window_state)

TESTSCORE = Path(__file__).parent.parent / "testdata" / "testscore.musicxml"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(TESTSCORE)
    return win


def _barline_in(window, measure: int):
    element = next(el for el in window.animation_inputs.layout.elements
                   if el.identity.kind is ElementKind.BARLINE
                   and str(el.identity.element_id)
                   == f"score:m{measure}:barline:0")
    item = window._scenes.items[element.identity.element_id]
    window.selection.select_at(item.bbox.center(), item.scene())
    return element


# -- the dock ---------------------------------------------------------------

def test_the_zone_is_a_left_dock_with_a_saveState_identity(window) -> None:
    zone = window.layout_zone
    assert zone.objectName() == "LayoutZone"
    assert window.dockWidgetArea(zone) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert zone.allowedAreas() == Qt.DockWidgetArea.LeftDockWidgetArea


def test_its_toggle_is_in_the_view_menu_beside_the_other_docks(window) -> None:
    view_actions = window.menus.view_menu.actions()
    for dock in (window.layout_zone, window.inspector, window.lower_zone):
        assert dock.toggleViewAction() in view_actions


def test_the_toggle_is_the_docks_own_and_is_labelled(window) -> None:
    """The show/hide surface is the dock's `toggleViewAction()`, not a
    close button: the zone carries NoDockWidgetFeatures like the
    inspector and the lower zone (the M1 chrome ruling)."""
    toggle = window.layout_zone.toggleViewAction()
    assert toggle.isCheckable()
    assert toggle.text() == "Layout Zone"
    assert window.layout_zone.features() == \
        window.inspector.features()          # no close/float/move chrome


# -- a second surface, not a second implementation --------------------------

def test_the_buttons_carry_the_SAME_actions_the_score_menu_holds(
        window) -> None:
    """The whole point of D9: one action object per gesture, so enabled
    state, label and status tip cannot diverge between the surfaces."""
    actions = window.break_action.actions
    assert len(window.layout_zone.buttons) == 3
    assert tuple(b.defaultAction() for b in window.layout_zone.buttons) \
        == actions
    for action in actions:
        assert action in window.menus.score_menu.actions()


def test_a_button_mirrors_its_action_without_any_sync_of_its_own(
        window) -> None:
    page_button = window.layout_zone.buttons[2]
    assert not page_button.isEnabled()
    assert page_button.statusTip() == PAGE_NO_SELECTION

    _barline_in(window, 2)
    assert page_button.isEnabled()
    assert page_button.text() == "Force Page Break Here"
    assert page_button.statusTip() == ""


def test_a_button_runs_the_same_command_the_menu_item_does(window) -> None:
    from scoreanim.core.project import PageBreak

    _barline_in(window, 2)
    window.layout_zone.buttons[2].click()
    assert window.app_state.doc.page_break_overrides == {3: PageBreak.FORCE}
    assert window.app_state.undo_text() == "force page break"


def test_the_menu_actions_all_stay(window) -> None:
    """"Menu actions stay" — the zone is an addition, not a move."""
    menu_actions = window.menus.score_menu.actions()
    for action in window.break_action.actions:
        assert action in menu_actions


# -- D10: does a stored layout that predates the dock place it sanely? ------

def test_a_stored_layout_predating_the_zone_still_places_it(qapp, tmp_path):
    """Measured before deciding anything, because bumping
    `_STATE_VERSION` discards every user's saved window layout.

    The state is saved from a window with the dock REMOVED, which is what
    a v0.2-beta.4 store looks like: the zone is simply absent from it.
    Restoring it into a window that has the dock must leave the dock
    where `addDockWidget` put it, at a usable width.
    """
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    old = MainWindow(settings=settings)
    old.removeDockWidget(old.layout_zone)          # a store without it
    save_window_state(old, old.inspector.sections, settings)
    stored = settings.value(_DOCK_STATE)
    assert stored is not None
    assert b"LayoutZone" not in bytes(stored)

    fresh = MainWindow(settings=settings)          # restores in __init__
    restore_window_state(fresh, fresh.inspector.sections, settings)
    assert fresh.dockWidgetArea(fresh.layout_zone) \
        == Qt.DockWidgetArea.LeftDockWidgetArea
    assert not fresh.layout_zone.isHidden()
    assert fresh.layout_zone.width() > 0
    # and the other two docks are still where the stored state put them
    assert fresh.dockWidgetArea(fresh.inspector) \
        == Qt.DockWidgetArea.RightDockWidgetArea
    assert fresh.dockWidgetArea(fresh.lower_zone) \
        == Qt.DockWidgetArea.BottomDockWidgetArea


def test_the_state_version_did_not_need_bumping() -> None:
    """The conclusion of the test above, pinned as a statement: v0 stored
    layouts restore correctly with the third dock present, so
    `_STATE_VERSION` stays 0 and no user loses their window layout."""
    assert _STATE_VERSION == 0


def test_the_zone_round_trips_through_the_existing_persistence(qapp,
                                                               tmp_path):
    """`window_state.py` needs no change (§1.5): one saveState pair
    persists all three docks."""
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    first = MainWindow(settings=settings)
    first.layout_zone.hide()                            # what the toggle does
    save_window_state(first, first.inspector.sections, settings)

    second = MainWindow(settings=settings)              # restores in __init__
    assert second.layout_zone.isHidden()
    second.layout_zone.show()
    save_window_state(second, second.inspector.sections, settings)

    third = MainWindow(settings=settings)
    assert not third.layout_zone.isHidden()
    assert third.dockWidgetArea(third.layout_zone) \
        == Qt.DockWidgetArea.LeftDockWidgetArea
