"""The sweep (E2): no control in the app is left with nothing to say.

Two passes over a real window, built offscreen.

- **Every action** in the menus and on the toolbar went through
  `ui/tips.py`. The check is the dynamic property `describe` writes, not
  the tooltip itself: Qt fills a bare action's tooltip in from its own
  label, so a tooltip alone proves nothing, while the property is only
  ever set by a person writing a sentence.
- **Every interactive widget** in the three docks, the welcome pane and
  the zoom overlay has a tooltip. A widget here may legitimately be
  showing a REASON rather than its sentence (Restore all with nothing
  deleted), so this pass asks for text, not for the property.

Then the empty states, which is the other half of the brief: a fresh
launch must not show a blank box anywhere.

The Score menu is not swept: it is empty until a score loads and its
contents are rebuilt per load — `tests/test_parts_menu.py` owns it.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QAbstractButton,  # noqa: E402
                               QAbstractItemView, QAbstractSlider,
                               QAbstractSpinBox, QApplication, QComboBox,
                               QLineEdit, QScrollBar, QTabBar, QToolBar,
                               QWidget, QWidgetAction)

from scoreanim.ui import tips  # noqa: E402
from scoreanim.ui.main_window import MainWindow  # noqa: E402

# Widget classes a person can act on. A label is not here — a readout
# carries its sentence where one helps, but an empty-state line has
# nothing to add to the words it is already showing.
INTERACTIVE = (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit,
               QAbstractSlider, QAbstractItemView)

# Widgets that build their own innards. What is inside one of these is
# Qt's, not ours, so the sweep stops at the composite itself.
_COMPOSITES = (QComboBox, QAbstractSpinBox, QTabBar)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(qapp):
    return MainWindow()


def _own_widget(widget: QWidget) -> bool:
    """Ours to answer for, rather than Qt's own plumbing.

    A spin box and a combo box each build a line edit and a popup list
    inside themselves, a tab bar builds two scroll arrows, and a scroll
    area builds two scrollbars. None of those is a control anybody
    aimed at, and none can be given a tooltip without it showing on the
    control that owns them.
    """
    if isinstance(widget, QScrollBar) or widget.objectName().startswith("qt_"):
        return False
    # only the widget's OWN name is checked above: a scroll area parents
    # its content under a "qt_scrollarea_viewport", and two of the three
    # docks are scrolled — walking the whole chain for that prefix would
    # quietly excuse every control in them.
    node = widget.parentWidget()
    while node is not None:
        if isinstance(node, _COMPOSITES):
            return False
        node = node.parentWidget()
    return True


def _controls(root: QWidget) -> list[QWidget]:
    found = [w for w in root.findChildren(QWidget)
             if isinstance(w, INTERACTIVE) and _own_widget(w)]
    if isinstance(root, INTERACTIVE) and _own_widget(root):
        found.append(root)
    return found


def _sentence_bearing(action) -> bool:
    """An action that should carry a sentence.

    Not a separator, and not a `QWidgetAction` — `toolbar.addWidget`
    wraps a widget in one of those, and the widget beneath is what a
    hover actually lands on, so it is swept as a widget instead.
    """
    return not action.isSeparator() and not isinstance(action, QWidgetAction)


def _actions(window) -> list:
    """Every action a person can reach: the five static menus and the
    toolbar."""
    reachable = []
    for menu in window.menus.all_menus:
        if menu is window.menus.score_menu:
            continue                     # rebuilt per load; see the header
        reachable += [a for a in menu.actions() if _sentence_bearing(a)]
    reachable += [a for a in _toolbar(window).actions()
                  if _sentence_bearing(a)]
    return reachable


def _toolbar(window) -> QToolBar:
    return window.findChild(QToolBar, "MainToolbar")


# -- the sweep --------------------------------------------------------------


def test_every_menu_and_toolbar_action_has_a_sentence(window) -> None:
    silent = [a.text() for a in _actions(window) if not tips.live_tip(a)]
    assert silent == []


def test_every_control_in_the_docks_has_a_tooltip(window) -> None:
    silent = []
    for dock in (window.layout_zone, window.inspector, window.lower_zone,
                 _toolbar(window)):
        silent += [f"{dock.objectName()}: {type(w).__name__} "
                   f"{w.text() if hasattr(w, 'text') else ''}"
                   for w in _controls(dock) if not w.toolTip()]
    assert silent == []


def test_every_control_on_the_stage_has_a_tooltip(window) -> None:
    """The two floating panes over the score: the welcome card (E1) and
    the zoom controls (D2)."""
    silent = [type(w).__name__
              for pane in (window.welcome, window.zoom_overlay)
              for w in _controls(pane) if not w.toolTip()]
    assert silent == []


def test_a_dead_control_says_why_rather_than_what(window) -> None:
    """The whole point of the pass: nothing is loaded here, so the
    controls that need a score are grayed — and each one names what is
    missing instead of describing a gesture that would not run."""
    assert window.menus.export_action.toolTip() == tips.NEEDS_SCORE
    assert window.menus.texts_action.toolTip() == tips.NEEDS_SCORE
    assert window.menus.undo_action.toolTip() == tips.NOTHING_TO_UNDO
    assert window.menus.redo_action.toolTip() == tips.NOTHING_TO_REDO
    for button in window.layout_zone.buttons:
        assert not button.isEnabled()
        assert button.toolTip() and button.toolTip() != button.text()


def test_no_dead_control_anywhere_is_still_describing_a_gesture(
        window) -> None:
    """Swept, not spot-checked: every grayed control in the three docks
    has a tooltip, and it is not the one it shows when it is live."""
    for dock in (window.layout_zone, window.inspector, window.lower_zone):
        for widget in _controls(dock):
            # its OWN flag, not its ancestors': a block switched off as
            # a unit (the style controls with nothing selected) is
            # covered by that panel's empty state, and asking each
            # control in it to repeat the reason would be noise
            if widget.isEnabledTo(widget.parentWidget()):
                continue
            assert widget.toolTip(), f"{type(widget).__name__} in {dock}"
            live = tips.live_tip(widget)
            if live:
                assert widget.toolTip() != live


# -- the empty states -------------------------------------------------------


def test_the_layout_zone_lists_say_what_would_fill_them(window) -> None:
    zone = window.layout_zone
    assert zone.overrides._empty.isVisibleTo(zone)
    assert "select a barline" in zone.overrides._empty.text()
    assert zone.deleted._empty.isVisibleTo(zone)
    assert "whole score is showing" in zone.deleted._empty.text()


def test_the_selection_tab_says_what_to_do(window) -> None:
    panel = window.inspector.selection_panel
    assert panel._stack.currentWidget() is panel._empty
    assert "click a note" in panel._empty.text()


def test_the_welcome_pane_names_an_empty_recents_list(window) -> None:
    from scoreanim.ui import welcome_pane

    pane = window.welcome
    if pane._recents.count() == 0:
        assert pane._empty.text() == welcome_pane.NO_RECENTS
        assert not pane._recents.isVisibleTo(pane)


def test_both_lanes_say_what_they_are_missing() -> None:
    """The waveform has said "No audio" since FIX 2; the tempo lane
    below it was a blank rectangle until E2."""
    from scoreanim.ui import tempo_lane, waveform

    assert "No audio" in waveform._EMPTY
    assert "No score" in tempo_lane._EMPTY


# -- with a score in, and something picked ----------------------------------


def test_nothing_goes_silent_once_a_score_and_a_selection_arrive(
        qapp, tmp_path) -> None:
    """The states the empty window cannot reach: a loaded score fills
    the Selection tab and lights the break actions, and every control
    that stays grayed there still has to say why.

    Its own window, opened last, so nothing above sees a loaded one.
    """
    from pathlib import Path

    from PySide6.QtCore import QSettings

    from scoreanim.core.score.identity import ElementKind

    score = Path(__file__).parent.parent / "testdata" / "testscore.musicxml"
    settings = QSettings(str(tmp_path / "ui.ini"),
                         QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(score)

    note = next(el for el in win.animation_inputs.layout.elements
                if el.identity.kind is ElementKind.NOTEHEAD)
    item = win._scenes.items[note.identity.element_id]
    win.selection.select_at(item.bbox.center(), item.scene())
    assert win.app_state.selection is not None

    for dock in (win.layout_zone, win.inspector, win.lower_zone):
        for widget in _controls(dock):
            assert widget.toolTip(), type(widget).__name__
            if widget.isEnabledTo(widget.parentWidget()):
                continue
            live = tips.live_tip(widget)
            if live:
                assert widget.toolTip() != live, widget.toolTip()
    for action in _actions(win):
        assert tips.live_tip(action), action.text()
