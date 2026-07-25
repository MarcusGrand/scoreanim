"""Selection panel (M2.5), offscreen: the readout tracks
AppState.selection_changed, reports the measure ORDINAL parsed out of
the id (with the printed number when they differ), and returns to its
empty state when the selection clears.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.score.identity import (ElementId,  # noqa: E402
                                           ElementIdentity, ElementKind,
                                           PartId)
from scoreanim.core.score.model import MeasureInfo  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.panels import SelectionPanel  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def panel(qapp):
    state = AppState()
    return SelectionPanel(state), state


def _note(eid: str = "P1:m4:s1:v2:note:0") -> ElementIdentity:
    return ElementIdentity(ElementId(eid), ElementKind.NOTEHEAD,
                           PartId("P1"), "Flute", 1, 2, 12.0)


def _row(panel: SelectionPanel, name: str) -> str:
    return panel._values[name].text()


def test_starts_empty(panel) -> None:
    p, _ = panel
    assert p._stack.currentWidget() is p._empty


def test_selecting_a_notehead_fills_the_readout(panel) -> None:
    p, state = panel
    state.set_selection(_note())
    assert p._stack.currentWidget() is not p._empty
    assert _row(p, "Kind") == "Notehead"
    assert _row(p, "Part") == "Flute"
    assert _row(p, "Staff") == "1"
    assert _row(p, "Voice") == "2"
    assert _row(p, "Measure") == "4"
    assert _row(p, "Onset") == "12"
    assert _row(p, "Extent") == "—"
    assert p._eid.text() == "P1:m4:s1:v2:note:0"


def test_part_falls_back_to_the_part_id(panel) -> None:
    p, state = panel
    ident = ElementIdentity(ElementId("P7:m1:s1:v1:note:0"),
                            ElementKind.NOTEHEAD, PartId("P7"), None,
                            1, 1, 0.0)
    state.set_selection(ident)
    assert _row(p, "Part") == "P7"


def test_a_spanner_reports_its_extent(panel) -> None:
    p, state = panel
    ident = ElementIdentity(ElementId("P1:m8:s1:v1:slur:0"),
                            ElementKind.SLUR, PartId("P1"), "Flute",
                            1, 1, 28.0, (28.0, 32.0))
    state.set_selection(ident)
    assert _row(p, "Kind") == "Slur"
    assert _row(p, "Extent") == "28 – 32"


def test_a_broken_spanner_names_the_segment(panel) -> None:
    """An override targets ONE :seg, so the panel must not imply the
    whole slur is selected."""
    p, state = panel
    ident = ElementIdentity(ElementId("P1:m8:s1:v1:slur:0:seg1"),
                            ElementKind.SLUR, PartId("P1"), "Flute",
                            1, 1, 28.0, (28.0, 32.0))
    state.set_selection(ident)
    assert _row(p, "Kind") == "Slur (segment 1)"
    assert _row(p, "Measure") == "8"        # the START measure


def test_scaffold_shows_its_measure_and_no_onset(panel) -> None:
    p, state = panel
    ident = ElementIdentity(ElementId("score:m3:barline:0"),
                            ElementKind.BARLINE, None, None,
                            None, None, None)
    state.set_selection(ident)
    assert _row(p, "Kind") == "Barline"
    assert _row(p, "Part") == "—"
    assert _row(p, "Measure") == "3"
    assert _row(p, "Onset") == "—"


def test_page_furniture_has_no_measure(panel) -> None:
    """A part label is identity-bearing TEXT — it selects, but its id
    carries no measure and it is minted onset-less."""
    p, state = panel
    ident = ElementIdentity(ElementId("score:p1:text:0"),
                            ElementKind.TEXT, None, None, None, None, None)
    state.set_selection(ident)
    assert _row(p, "Kind") == "Text"
    assert _row(p, "Measure") == "—"
    assert _row(p, "Onset") == "—"


def test_printed_number_shown_when_it_differs_from_the_ordinal(panel) -> None:
    """A Dorico "X0" pickup makes ordinal and printed number differ for
    the whole score (adapter item 12)."""
    p, state = panel
    state.set_measures([MeasureInfo(0, 0.0, 1.0),      # the X0 pickup
                        MeasureInfo(1, 1.0, 4.0),
                        MeasureInfo(2, 5.0, 4.0)])
    state.set_selection(_note("P1:m2:s1:v1:note:0"))
    assert _row(p, "Measure") == "2  (printed 1)"


def test_no_printed_suffix_when_they_agree(panel) -> None:
    p, state = panel
    state.set_measures([MeasureInfo(1, 0.0, 4.0), MeasureInfo(2, 4.0, 4.0)])
    state.set_selection(_note("P1:m2:s1:v1:note:0"))
    assert _row(p, "Measure") == "2"


def test_clearing_returns_the_empty_state(panel) -> None:
    p, state = panel
    state.set_selection(_note())
    assert p._stack.currentWidget() is not p._empty
    state.set_selection(None)
    assert p._stack.currentWidget() is p._empty


def test_panel_never_touches_the_document(panel) -> None:
    """M2 introduces no document semantics: selecting is not an edit."""
    p, state = panel
    state.set_selection(_note())
    state.set_selection(None)
    assert not state.can_undo
    assert not state.is_dirty
