"""Inspector dock (M1.4, three tabs since C1), offscreen: the tabs hold
the panels they should, the resync pass never re-executes a command,
and the active tab is addressable by a stable key so it can be
persisted. Follow and Systems left for the transport strip in C2 —
tests/test_transport.py.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDockWidget,  # noqa: E402
                               QWidget)

from scoreanim.core.animation import RevealMode  # noqa: E402
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
    """C2: Follow and Systems moved to the transport strip, so the dock
    holds neither — and needs no playback controller to build."""
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
