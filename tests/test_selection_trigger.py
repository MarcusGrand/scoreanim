"""The re-timing stepper (2026-08-08), on a real MainWindow offscreen:
the Fires row, the earlier/later walk over the system's onset stops,
Reset, and the live rebuild the window runs behind a press — the
schedule the export inputs carry must follow every move."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import (step_from,  # noqa: E402
                                      stops_for_system)
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.core.score.model import MeasureInfo  # noqa: E402
from scoreanim.ui.main_window import MainWindow  # noqa: E402
from scoreanim.ui.panels.selection_trigger import bar_beat_label  # noqa: E402

FIXTURE = Path(__file__).parent.parent / "testdata" / "testscore.musicxml"


# -- the label (pure) ----------------------------------------------------

_MEASURES = (MeasureInfo(number=1, start=0.0, quarter_length=4.0),
             MeasureInfo(number=2, start=4.0, quarter_length=4.0))
_PICKUP = (MeasureInfo(number=0, start=0.0, quarter_length=1.0),
           MeasureInfo(number=1, start=1.0, quarter_length=4.0))


def test_bar_beat_label_plain_and_fractional() -> None:
    assert bar_beat_label(0.0, _MEASURES) == "1 · beat 1"
    assert bar_beat_label(5.5, _MEASURES) == "2 · beat 2.5"


def test_bar_beat_label_shows_the_printed_number_when_it_differs() -> None:
    """The Measure row's habit: a Dorico pickup shifts every printed
    number off the document ordinal."""
    assert bar_beat_label(0.5, _PICKUP) == "1 (printed 0) · beat 1.5"
    assert bar_beat_label(2.0, _PICKUP) == "2 (printed 1) · beat 2"


def test_bar_beat_label_falls_back_to_raw_beats() -> None:
    assert bar_beat_label(3.0, ()) == "3"
    assert bar_beat_label(100.0, _MEASURES) == "100"


# -- the widget, on a real window ----------------------------------------

@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    from PySide6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "ui.ini"),
                         QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(FIXTURE)
    return win


@pytest.fixture()
def widget(window):
    return window.inspector.selection_panel.trigger_controls


def _select(window, kind: ElementKind):
    for el in window.animation_inputs.layout.elements:
        if el.identity.kind is kind and el.identity.onset is not None:
            window.app_state.set_selection(el.identity)
            return el
    raise AssertionError(f"no {kind} in the fixture")


def test_blank_and_disabled_without_a_retimeable_selection(
        window, widget) -> None:
    assert widget._fires.text() == "—"
    for button in (widget._earlier, widget._later, widget._reset):
        assert not button.isEnabled()
    # a notehead is a reveal anchor — never re-timeable
    _select(window, ElementKind.NOTEHEAD)
    assert widget._fires.text() == "—"
    assert not widget._later.isEnabled()
    assert widget._moved.isHidden()


def test_a_dynamic_shows_its_fire_time(window, widget) -> None:
    el = _select(window, ElementKind.DYNAMIC)
    assert widget._fires.text() not in ("", "—")
    assert widget._moved.isHidden()                # automatic: no marker
    schedule = window.animation_inputs.schedule
    assert schedule.beats_by_element[el.identity.element_id] is not None


def test_a_press_moves_the_element_one_stop(window, widget) -> None:
    """One press = one SetTriggerBeat = one undo entry, and the export
    inputs' schedule follows the move (the window's live rebuild)."""
    el = _select(window, ElementKind.DYNAMIC)
    eid = el.identity.element_id
    schedule = window.animation_inputs.schedule
    before = schedule.beats_by_element[eid]
    stops = stops_for_system(window.animation_inputs.layout, el.system)
    expected = step_from(stops, before, +1)
    assert expected is not None

    widget._step(+1)
    assert dict(window.app_state.doc.trigger_overrides) == {eid: expected}
    assert window.app_state.undo_text() == "move onset"
    # the retained inputs carry the REBUILT schedule — the export path
    assert window.animation_inputs.schedule.beats_by_element[eid] \
        == expected
    assert not widget._moved.isHidden()            # the quiet marker
    assert widget._reset.isEnabled()


def test_undo_restores_the_automatic_time(window, widget) -> None:
    el = _select(window, ElementKind.DYNAMIC)
    eid = el.identity.element_id
    before = window.animation_inputs.schedule.beats_by_element[eid]
    widget._step(+1)
    assert window.animation_inputs.schedule.beats_by_element[eid] != before
    window.app_state.undo()
    assert window.animation_inputs.schedule.beats_by_element[eid] == before
    assert widget._moved.isHidden()
    window.app_state.redo()
    assert window.animation_inputs.schedule.beats_by_element[eid] != before


def test_reset_hands_the_element_back(window, widget) -> None:
    el = _select(window, ElementKind.DYNAMIC)
    eid = el.identity.element_id
    before = window.animation_inputs.schedule.beats_by_element[eid]
    widget._step(+1)
    widget._clear()
    assert window.app_state.doc.trigger_overrides == {}
    assert window.app_state.undo_text() == "reset onset"
    assert window.animation_inputs.schedule.beats_by_element[eid] == before
    assert widget._moved.isHidden()
    assert not widget._reset.isEnabled()


def test_stepping_past_the_system_end_does_nothing(window, widget) -> None:
    """Walk Later until the button disables: every press lands on a
    stop of the element's own system, and past the last stop the walk
    stops rather than wrapping or leaving the system."""
    el = _select(window, ElementKind.DYNAMIC)
    eid = el.identity.element_id
    stops = stops_for_system(window.animation_inputs.layout, el.system)
    for _ in range(len(stops) + 1):
        if not widget._later.isEnabled():
            break
        widget._step(+1)
    assert not widget._later.isEnabled()
    last = window.app_state.doc.trigger_overrides[eid]
    assert last == stops[-1].beats
    depth_before = window.app_state.doc
    widget._step(+1)                               # past the end: no-op
    assert window.app_state.doc is depth_before
