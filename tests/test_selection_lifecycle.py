"""Selection lifecycle (M2.6) on a real MainWindow, offscreen.

When a selection must CLEAR (the items it names are destroyed), when it
must SURVIVE (D2: page flips and mode switches — the scenes are all
retained), and the two gestures that clear it deliberately (Esc, a click
in the masked area of system mode).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.project import (ProjectDoc,  # noqa: E402
                                    SetHideEmptyStaves)
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.ui.main_window import MainWindow  # noqa: E402

TESTSCORE = Path(__file__).parent.parent / "testdata" / "testscore.musicxml"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    from PySide6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    # the real open path, so doc.score is set and the re-engrave trigger
    # in _on_document_changed can actually fire
    win.files.open_score(TESTSCORE)
    return win


def _select_a_notehead(window) -> object:
    """Select the first notehead through the real click path."""
    layout = window.animation_inputs.layout
    note = next(el for el in layout.elements
                if el.identity.kind is ElementKind.NOTEHEAD)
    item = window._scenes.items[note.identity.element_id]
    window.selection.select_at(item.bbox.center(), item.scene())
    return note


# -- clears --------------------------------------------------------------

def test_reengrave_carries_a_surviving_selection(window) -> None:
    """M5.5 (D9) changed this: a re-engrave rebuilds every ElementItem,
    but the identity is re-resolved against the fresh table, so a
    selection whose musical id survived comes back — on the NEW item,
    tint and all. Before D9 it cleared, and toggling a break deselected
    the barline you had just clicked."""
    note = _select_a_notehead(window)
    assert window.app_state.selected is not None
    before = window._scenes
    doc = window.app_state.doc
    window.app_state.execute(SetHideEmptyStaves(not doc.hide_empty_staves))
    assert window._scenes is not before      # a re-engrave really happened

    eid = note.identity.element_id
    assert window.app_state.selected is not None
    assert window.app_state.selected.element_id == eid
    assert window.selection.highlighted is window._scenes.items[eid]
    assert window.selection.highlighted is not before.items[eid]


def test_fresh_load_clears_the_selection(window) -> None:
    _select_a_notehead(window)
    assert window.app_state.selected is not None
    window.files.open_score(TESTSCORE)
    assert window.app_state.selected is None
    assert window.selection.highlighted is None


def test_opening_a_project_clears_the_selection(window) -> None:
    """reset_document is the project-open hook."""
    _select_a_notehead(window)
    assert window.app_state.selected is not None
    window.app_state.reset_document(ProjectDoc())
    assert window.app_state.selected is None


# -- survives (D2) -------------------------------------------------------

def test_selection_survives_a_page_flip(window) -> None:
    """D2, pinned at window level: flip away and back, and both the
    selection and its highlight are still there. Scenes are per-page and
    retained; show_page is a bare setScene, so nothing is destroyed."""
    note = _select_a_notehead(window)
    held = window.app_state.selected
    lit = window.selection.highlighted
    home = window._scenes.scene_for_page(note.page)
    assert lit is not None and lit.scene() is home

    for page in range(1, window._scenes.page_count + 1):
        window.router.show_page(page)
    window.router.show_page(note.page)

    assert window.app_state.selected == held
    assert window.selection.highlighted is lit
    assert lit.selected is True              # tint never dropped
    assert lit.scene() is home


def test_selection_survives_a_mode_switch(window) -> None:
    """Entering Systems mode masks other systems but destroys nothing;
    a selection on another system stays held, its tint simply
    letterboxed."""
    _select_a_notehead(window)
    held = window.app_state.selected
    lit = window.selection.highlighted
    window.router.show_system(2)
    assert window.app_state.selected == held
    assert window.selection.highlighted is lit
    assert lit.selected is True
    window.view.clear_band()
    assert window.app_state.selected == held


# -- deliberate deselect gestures ---------------------------------------

def test_escape_deselects(window) -> None:
    """D7: view-level, so Esc keeps its normal meaning in dialogs, the
    inspector's fields, and the tempo lane's drag-cancel."""
    _select_a_notehead(window)
    assert window.app_state.selected is not None
    window.view.keyPressEvent(QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape,
        Qt.KeyboardModifier.NoModifier))
    assert window.app_state.selected is None
    assert window.selection.highlighted is None


def test_click_outside_the_band_deselects_in_system_mode(window) -> None:
    """In system mode the scene under the view is the whole PAGE, so ink
    from a neighbouring system is invisible but fully hittable. The view
    gates on the band; the controller stays mode-blind."""
    note = _select_a_notehead(window)
    window.router.show_system(1)
    band = window.view._framing.band
    assert band is not None
    outside = QPointF(band.center().x(), band.bottom() + 500.0)
    assert not window.view.in_band(outside)
    assert window.view.in_band(band.center())

    hits: list = []
    window.view.deselect_requested.connect(lambda: hits.append(1))
    window.view.clicked.connect(lambda pos, scene: hits.append(pos))
    _click_at_scene(window, outside)
    assert hits == [1]                       # deselect, never a hit
    assert window.app_state.selected is None
    assert note is not None


def test_in_band_is_always_true_in_paged_mode(window) -> None:
    window.view.clear_band()
    assert window.view.in_band(QPointF(-5000.0, -5000.0))


# -- gesture separation: a click, versus a drag that is not one ---------

def _mouse(kind, view, pos: QPoint) -> QMouseEvent:
    return QMouseEvent(kind, QPointF(pos), view.mapToGlobal(pos),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _click_at_scene(window, scene_pos: QPointF) -> None:
    view = window.view
    pos = view.mapFromScene(scene_pos)
    view.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, view, pos))
    view.mouseReleaseEvent(
        _mouse(QMouseEvent.Type.MouseButtonRelease, view, pos))


def test_a_short_press_release_is_a_click(window) -> None:
    layout = window.animation_inputs.layout
    note = next(el for el in layout.elements
                if el.identity.kind is ElementKind.NOTEHEAD)
    window.router.show_page(note.page)
    item = window._scenes.items[note.identity.element_id]
    seen: list = []
    window.view.clicked.connect(lambda pos, scene: seen.append(pos))
    _click_at_scene(window, item.bbox.center())
    assert len(seen) == 1


def test_a_drag_beyond_the_threshold_is_not_a_click(window) -> None:
    """The threshold outlived the pan it was built for (2026-07-30: drag
    no longer moves the view). It stays as a guard — a hand that slides
    while pressing must not change the selection."""
    view = window.view
    seen: list = []
    view.clicked.connect(lambda pos, scene: seen.append(pos))
    start = QPoint(200, 200)
    far = QPoint(200 + QApplication.startDragDistance() + 12, 240)
    view.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, view,
                                start))
    view.mouseReleaseEvent(_mouse(QMouseEvent.Type.MouseButtonRelease, view,
                                  far))
    assert seen == []


def test_a_stray_drag_does_not_disturb_an_existing_selection(window) -> None:
    """A drag that starts on empty page (not on the selected element's own
    ink, so `nudge_probe` says no) does nothing whatsoever."""
    _select_a_notehead(window)
    held = window.app_state.selected
    view = window.view
    start = QPoint(200, 200)
    far = QPoint(200 + QApplication.startDragDistance() + 12, 260)
    view.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, view,
                                start))
    view.mouseReleaseEvent(_mouse(QMouseEvent.Type.MouseButtonRelease, view,
                                  far))
    assert window.app_state.selected == held
