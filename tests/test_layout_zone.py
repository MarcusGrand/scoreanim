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


def test_a_button_is_an_icon_whose_tooltip_renames_itself(window) -> None:
    """A2: the three buttons lost their long labels, so the label the
    action renames itself to has to reach the user as the tooltip."""
    page_button = window.layout_zone.buttons[2]
    assert page_button.toolButtonStyle() \
        == Qt.ToolButtonStyle.ToolButtonIconOnly
    for button in window.layout_zone.buttons:
        assert not button.icon().isNull()
    assert page_button.toolTip() == "Toggle Page Break Here"

    _barline_in(window, 2)
    assert page_button.toolTip() == "Force Page Break Here"


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


# -- M6.7: the overrides readout --------------------------------------------

def _rows(window) -> list[str]:
    from PySide6.QtWidgets import QLabel
    return [row.findChild(QLabel).text()
            for row in window.layout_zone.overrides._rows]


def _clear_buttons(window):
    from PySide6.QtWidgets import QPushButton
    return [row.findChild(QPushButton)
            for row in window.layout_zone.overrides._rows]


def test_the_readout_is_empty_until_something_is_authored(window) -> None:
    assert _rows(window) == []
    assert window.layout_zone.overrides._empty.isVisibleTo(
        window.layout_zone.overrides)


def test_the_readout_lists_both_maps_in_measure_order(window) -> None:
    """One list, because the user authors both in one pass down the
    score and thinks of them that way."""
    from scoreanim.core.project import (PageBreak, SetPageBreak,
                                        SetSystemBreak, SystemBreak)

    window.app_state.execute(SetPageBreak(12, PageBreak.FORCE))
    window.app_state.execute(SetSystemBreak(3, SystemBreak.FORCE))
    window.app_state.execute(SetSystemBreak(7, SystemBreak.SUPPRESS))
    assert _rows(window) == ["m3: force system break",
                             "m7: remove system break",
                             "m12: force page break"]


def test_a_row_appears_for_each_axis_at_one_ordinal(window) -> None:
    from scoreanim.core.project import (PageBreak, SetPageBreak,
                                        SetSystemBreak, SystemBreak)

    window.app_state.execute(SetSystemBreak(9, SystemBreak.FORCE))
    window.app_state.execute(SetPageBreak(9, PageBreak.SUPPRESS))
    assert _rows(window) == ["m9: force system break",
                             "m9: remove page break"]


def test_the_readout_refreshes_on_every_document_change(window) -> None:
    from scoreanim.core.project import PageBreak, SetPageBreak

    window.app_state.execute(SetPageBreak(3, PageBreak.FORCE))
    assert _rows(window) == ["m3: force page break"]
    window.app_state.undo()
    assert _rows(window) == []
    window.app_state.redo()
    assert _rows(window) == ["m3: force page break"]


def test_a_row_clear_pops_exactly_that_entry_in_one_undo_step(
        window) -> None:
    """D12: no new command — `mode=None` already pops — and it goes
    through execute(), so it re-engraves on the same path the menu
    action does."""
    from scoreanim.core.project import (PageBreak, SetPageBreak,
                                        SetSystemBreak, SystemBreak)

    window.app_state.execute(SetSystemBreak(3, SystemBreak.FORCE))
    window.app_state.execute(SetPageBreak(9, PageBreak.FORCE))
    before = window._scenes

    _clear_buttons(window)[1].click()                  # the page row
    doc = window.app_state.doc
    assert doc.page_break_overrides == {}
    assert doc.system_break_overrides == {3: SystemBreak.FORCE}
    assert _rows(window) == ["m3: force system break"]
    assert window._scenes is not before                # it re-engraved
    assert window.app_state.undo_text() == "clear page break"

    window.app_state.undo()
    assert window.app_state.doc.page_break_overrides == {9: PageBreak.FORCE}
    assert _rows(window) == ["m3: force system break",
                             "m9: force page break"]


def test_clearing_a_system_row_sends_the_system_command(window) -> None:
    from scoreanim.core.project import SetSystemBreak, SystemBreak

    window.app_state.execute(SetSystemBreak(5, SystemBreak.SUPPRESS))
    _clear_buttons(window)[0].click()
    assert window.app_state.doc.system_break_overrides == {}
    assert window.app_state.undo_text() == "clear system break"


def test_the_readout_is_pure_data_a_test_can_assert(window) -> None:
    """`entries` is static so the content can be checked without going
    through widgets — and so the widget has nothing to get wrong beyond
    drawing it."""
    from scoreanim.core.project import PageBreak, ProjectDoc, SystemBreak
    from scoreanim.ui.panels import BreakOverridesList

    doc = ProjectDoc(system_break_overrides={12: SystemBreak.FORCE},
                     page_break_overrides={3: PageBreak.SUPPRESS,
                                           12: PageBreak.FORCE})
    assert BreakOverridesList.entries(doc) == (
        (3, True, PageBreak.SUPPRESS),
        (12, False, SystemBreak.FORCE),
        (12, True, PageBreak.FORCE))
    assert BreakOverridesList.entries(ProjectDoc()) == ()


# -- the deleted-elements readout -------------------------------------------

def _deleted_rows(window) -> list[str]:
    from PySide6.QtWidgets import QLabel
    return [row.findChild(QLabel).text()
            for row in window.layout_zone.deleted._rows]


def _restore_buttons(window):
    from PySide6.QtWidgets import QPushButton
    return [row.findChild(QPushButton)
            for row in window.layout_zone.deleted._rows]


def _delete_first(window, kind):
    """Select the first element of `kind` and delete it."""
    element = next(el for el in window.animation_inputs.layout.elements
                   if el.identity.kind is kind)
    window.app_state.set_selection(element.identity)
    window.delete_action.trigger()
    return element.identity.element_id


def test_nothing_deleted_until_something_is(window) -> None:
    panel = window.layout_zone.deleted
    assert _deleted_rows(window) == []
    assert panel._empty.isVisibleTo(panel)
    assert not panel.restore_all_button.isEnabled()


def test_a_delete_adds_a_row_and_undo_removes_it(window) -> None:
    _delete_first(window, ElementKind.TEXT)
    assert len(_deleted_rows(window)) == 1
    assert window.layout_zone.deleted.restore_all_button.isEnabled()
    window.app_state.undo()
    assert _deleted_rows(window) == []


def test_a_broken_spanner_is_one_row(window) -> None:
    """Three hidden ids, one deleted object."""
    from scoreanim.core.project import LayoutOverride, ProjectDoc
    from scoreanim.core.score.identity import ElementId
    from scoreanim.ui.panels import DeletedElementsList

    hairpin = "P1:m4:s1:v1:hairpin:0"
    doc = ProjectDoc(layout_overrides={
        ElementId(hairpin): LayoutOverride(hidden=True),
        ElementId(hairpin + ":seg1"): LayoutOverride(hidden=True),
        ElementId(hairpin + ":seg2"): LayoutOverride(hidden=True)})
    assert DeletedElementsList.entries(doc) == (
        (ElementId(hairpin), ElementId(hairpin + ":seg1"),
         ElementId(hairpin + ":seg2")),)


def test_a_row_restores_exactly_that_object_in_one_undo_step(window) -> None:
    first = _delete_first(window, ElementKind.TEXT)
    _delete_first(window, ElementKind.DYNAMIC)
    assert len(_deleted_rows(window)) == 2

    row = [i for i, family in
           enumerate(window.layout_zone.deleted.entries(window.app_state.doc))
           if family[0] == first][0]
    _restore_buttons(window)[row].click()

    doc = window.app_state.doc
    assert first not in doc.layout_overrides
    assert len(_deleted_rows(window)) == 1
    assert window._scenes.items[first].isVisible()      # back on screen
    assert window.app_state.undo_text() == "restore element"


def test_restore_all_brings_everything_back_in_one_undo_step(window) -> None:
    _delete_first(window, ElementKind.TEXT)
    _delete_first(window, ElementKind.DYNAMIC)
    before = dict(window.app_state.doc.layout_overrides)

    window.layout_zone.deleted.restore_all_button.click()

    assert window.app_state.doc.layout_overrides == {}
    assert _deleted_rows(window) == []
    assert window.app_state.undo_text() == "restore elements"
    window.app_state.undo()                              # ONE entry
    assert window.app_state.doc.layout_overrides == before


def test_a_text_replaced_by_an_overlay_is_not_listed_as_deleted(
        window) -> None:
    """It is hidden, but it is REPLACED, not deleted — restoring it here
    would leave the engraved mark under its replacement text. Its own
    restore lives in the Texts dialog."""
    from dataclasses import replace as rep

    from scoreanim.core.project import (OVERLAY_PREFIX, AddTempoOverlay,
                                        LayoutOverride, ProjectDoc)
    from scoreanim.core.project.stage_config import seed_overlay_text
    from scoreanim.core.score.identity import ElementId
    from scoreanim.ui.panels import DeletedElementsList

    text = next(el for el in window.animation_inputs.layout.elements
                if el.identity.kind is ElementKind.TEXT)
    eid = text.identity.element_id
    seed = rep(seed_overlay_text(text), content="replaced")
    assert window.app_state.execute(AddTempoOverlay(eid, seed))

    assert window.app_state.doc.layout_overrides[eid].hidden is True
    assert _deleted_rows(window) == []           # hidden, but not deleted
    assert seed.element_id == OVERLAY_PREFIX + str(eid)

    # ... and once the overlay is gone it would list normally
    doc = ProjectDoc(layout_overrides={eid: LayoutOverride(hidden=True)})
    assert DeletedElementsList.entries(doc) == ((ElementId(eid),),)
