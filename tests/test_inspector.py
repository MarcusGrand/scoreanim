"""Inspector dock (M1.4, three tabs since C1), offscreen: the tabs hold
the panels they should, the resync pass never re-executes a command,
the active tab is addressable by a stable key so it can be
persisted, and (C3) the dock follows the stage selection. Systems left for the transport strip in C2
(tests/test_transport.py) and Follow stopped being a control at all.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDockWidget,  # noqa: E402
                               QWidget)

from scoreanim.core.animation import RevealMode  # noqa: E402
from scoreanim.core.score.identity import (ElementId,  # noqa: E402
                                           ElementIdentity, ElementKind,
                                           PartId)
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.inspector import TAB_KEYS, Inspector  # noqa: E402
from scoreanim.ui.panels import (EffectsPanel, PageColorsPanel,  # noqa: E402
                                 SelectionPanel, VideoCanvasPanel)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def inspector(qapp):
    state = AppState()
    return Inspector(state), state


_PANELS = (EffectsPanel, PageColorsPanel, SelectionPanel, VideoCanvasPanel)


def _panels(dock: Inspector, key: str) -> list[type]:
    """The panel classes the named tab holds, top to bottom."""
    page = dock.tabs.widget(TAB_KEYS.index(key)).widget()
    return [type(child) for child in page.findChildren(QWidget)
            if isinstance(child, _PANELS)]


def test_is_a_fixed_right_dock_of_three_tabs(inspector) -> None:
    dock, _ = inspector
    assert dock.objectName() == "Inspector"      # saveState identity (M1.8)
    assert dock.features() \
        == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
    assert dock.allowedAreas() == Qt.DockWidgetArea.RightDockWidgetArea
    assert [dock.tabs.tabText(i) for i in range(dock.tabs.count())] \
        == ["Animate", "Stage", "Selection"]
    assert len(TAB_KEYS) == dock.tabs.count()


def test_each_tab_holds_its_panels(inspector) -> None:
    """C1: Animate is the effects panel, Stage stacks page colours over
    the video canvas, Selection is the selection panel."""
    dock, _ = inspector
    assert _panels(dock, "animate") == [EffectsPanel]
    assert _panels(dock, "stage") == [PageColorsPanel, VideoCanvasPanel]
    assert _panels(dock, "selection") == [SelectionPanel]


def test_only_the_stage_tab_stacks_collapsible_sections(inspector) -> None:
    """A tab with one panel needs no header — the tab label is it."""
    dock, _ = inspector
    assert set(dock.sections) == {"page_colors", "video_canvas"}
    assert all(s.expanded for s in dock.sections.values())


def test_the_active_tab_is_addressed_by_key(inspector) -> None:
    """Persisted by key, never by index, so reordering the tabs cannot
    make a stored value point at the wrong one."""
    dock, _ = inspector
    assert dock.active_tab == "animate"
    dock.set_active_tab("selection")
    assert dock.active_tab == "selection"
    assert dock.tabs.currentIndex() == TAB_KEYS.index("selection")
    dock.set_active_tab("no-such-tab")           # a stale stored value
    assert dock.active_tab == "selection"


def test_no_playback_state_is_left_in_the_dock(inspector) -> None:
    """C2: Systems moved to the transport strip and Follow is gone, so
    the dock holds neither — and needs no playback controller."""
    dock, _ = inspector
    assert not hasattr(dock, "follow_action")
    assert not hasattr(dock, "systems_action")


def test_sync_from_document_never_reexecutes(inspector) -> None:
    dock, state = inspector
    panel = dock.effects_panel
    panel._sweep_box.setChecked(True)
    panel._floor_spin.setValue(0.1)
    panel._floor.commit()
    depth = 0
    while state.can_undo:                        # measure stack depth
        state.undo()
        depth += 1
    for _ in range(depth):
        state.redo()
    dock.sync_from_document(state.doc)           # delegates to the panels
    assert panel._sweep_box.isChecked()
    assert panel._floor_spin.value() == 0.1
    assert state.doc.style.reveal_mode is RevealMode.CONTINUOUS
    for _ in range(depth):                       # resync added no command
        state.undo()
    assert not state.can_undo
    assert depth == 2


# -- C3: the dock follows the selection ---------------------------------------


def _select(state: AppState, eid: str = "P1:m4:s1:v1:note:0") -> None:
    state.set_selection(ElementIdentity(ElementId(eid), ElementKind.NOTEHEAD,
                                        PartId("P1"), "Flute", 1, 1, 12.0))


def test_a_selection_fronts_the_selection_tab(inspector) -> None:
    dock, state = inspector
    assert dock.active_tab == "animate"
    _select(state)
    assert dock.active_tab == "selection"


def test_clearing_the_selection_puts_the_old_tab_back(inspector) -> None:
    dock, state = inspector
    dock.set_active_tab("stage")
    _select(state)
    assert dock.active_tab == "selection"
    state.set_selection(None)
    assert dock.active_tab == "stage"


def test_a_tab_chosen_while_selected_is_respected(inspector) -> None:
    """The user's own click wins: it stays put while the selection is
    up, and clearing does not flip away from it."""
    dock, state = inspector
    _select(state)
    dock.set_active_tab("animate")               # stands in for a click
    _select(state, "P1:m5:s1:v1:note:0")         # another note
    assert dock.active_tab == "animate"
    state.set_selection(None)
    assert dock.active_tab == "animate"


def test_our_own_switch_does_not_count_as_the_users(inspector) -> None:
    """The flip to Selection travels the same currentChanged signal a
    click does; if it read as a choice, nothing would ever flip back."""
    dock, state = inspector
    _select(state)
    state.set_selection(None)
    assert dock.active_tab == "animate"


def test_the_empty_state_says_what_to_do(inspector) -> None:
    dock, _ = inspector
    panel = dock.selection_panel
    assert panel._stack.currentWidget() is panel._empty
    assert panel._empty.text() == "Nothing selected — click a note on the stage."
