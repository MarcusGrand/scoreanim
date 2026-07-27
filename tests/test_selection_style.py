"""Per-element style from the selection (M3.3) — BACKLOG 9's editing UI.

On a real MainWindow, offscreen. Three things this must get right, all
of them constraints inherited rather than invented here:

  rule 8   one gesture, one undo entry — including the `:seg` fan-out
  rule 13  M3 writes the AUTHORED colour channel and never the transient
           selection tint; the two must stay distinguishable on screen
  F5       per-part effect rules become authorable again (M4 deferred
           them here)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import ElementStyle  # noqa: E402
from scoreanim.core.editing import family_of  # noqa: E402
from scoreanim.core.project import ProjectDoc, SetElementStyle  # noqa: E402
from scoreanim.core.score.identity import (ElementId,  # noqa: E402
                                           ElementKind)
from scoreanim.ui.main_window import MainWindow  # noqa: E402

FIXTURE = (Path(__file__).parent.parent / "testdata"
           / "broken_hairpin_and_slur_test.musicxml")


# -- the widened command (headless) --------------------------------------

def test_segments_are_written_with_the_head_in_one_command() -> None:
    head = ElementId("P1:m4:s1:v0:hairpin:0")
    segs = (ElementId(f"{head}:seg1"), ElementId(f"{head}:seg2"))
    doc = SetElementStyle(head, ElementStyle(color="#ff0000"),
                          segments=segs).apply(ProjectDoc())
    assert set(doc.style.elements) == {head, *segs}
    assert all(v == ElementStyle(color="#ff0000")
               for v in doc.style.elements.values())


def test_clearing_clears_the_whole_family() -> None:
    head = ElementId("P1:m4:s1:v0:hairpin:0")
    segs = (ElementId(f"{head}:seg1"),)
    doc = SetElementStyle(head, ElementStyle(color="#ff0000"),
                          segments=segs).apply(ProjectDoc())
    assert SetElementStyle(head, None, segments=segs).apply(
        doc).style.elements == {}


def test_a_bad_color_is_rejected_before_anything_is_written() -> None:
    from scoreanim.core.project.commands.base import CommandError
    head = ElementId("P1:m4:s1:v0:hairpin:0")
    with pytest.raises(CommandError):
        SetElementStyle(head, ElementStyle(color="red"),
                        segments=(ElementId(f"{head}:seg1"),)
                        ).apply(ProjectDoc())


# -- the panel, on a real window -----------------------------------------

@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    from PySide6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(FIXTURE)
    return win


@pytest.fixture()
def panel(window):
    return window.inspector.selection_panel.style_controls


def _select(window, kind: ElementKind, broken: bool = False):
    for el in window.animation_inputs.layout.elements:
        if el.identity.kind is not kind:
            continue
        if broken and ":seg" not in str(el.identity.element_id):
            continue
        window.app_state.set_selection(el.identity)
        return el
    raise AssertionError(f"no {kind} in the fixture")


def _depth(window) -> int:
    return window.app_state._stack._index


# -- element scope -------------------------------------------------------

def test_color_writes_the_element_override(window, panel) -> None:
    el = _select(window, ElementKind.NOTEHEAD)
    panel._commit_color("#ff0000")
    assert window.app_state.doc.style.elements[el.identity.element_id] == \
        ElementStyle(color="#ff0000")
    assert window.app_state.undo_text() == "set element style"


def test_effect_and_color_do_not_clobber_each_other(window, panel) -> None:
    """Field-wise merge: setting one must not silently clear the other."""
    el = _select(window, ElementKind.NOTEHEAD)
    panel._commit_color("#ff0000")
    panel._effect.setCurrentText("pop")
    panel._commit_effect()
    assert window.app_state.doc.style.elements[el.identity.element_id] == \
        ElementStyle(color="#ff0000", effect="pop")


def test_inherit_removes_the_override_and_the_doc_stays_sparse(
        window, panel) -> None:
    el = _select(window, ElementKind.NOTEHEAD)
    panel._commit_color("#ff0000")
    panel._commit_color(None)
    assert el.identity.element_id not in window.app_state.doc.style.elements


def test_clear_removes_colour_and_effect_in_one_entry(window,
                                                      panel) -> None:
    el = _select(window, ElementKind.NOTEHEAD)
    panel._commit_color("#ff0000")
    panel._effect.setCurrentText("pop")
    panel._commit_effect()
    depth = _depth(window)
    panel._clear_overrides()
    assert el.identity.element_id not in window.app_state.doc.style.elements
    assert _depth(window) == depth + 1


# -- the :seg fan-out ----------------------------------------------------

def test_styling_a_segment_reaches_the_whole_spanner_in_one_entry(
        window, panel) -> None:
    """The ruling, end to end. The fixture's hairpin is broken across
    systems, so the user can only ever click ONE piece of it."""
    seg = _select(window, ElementKind.HAIRPIN, broken=True)
    known = list(window._scenes.items)
    family = family_of(seg.identity.element_id, known)
    assert len(family) > 1, "fixture must have a system-broken spanner"

    depth = _depth(window)
    panel._commit_color("#00ff00")

    elements = window.app_state.doc.style.elements
    assert set(family) <= set(elements)
    assert all(elements[eid] == ElementStyle(color="#00ff00")
               for eid in family)
    assert _depth(window) == depth + 1        # ONE undo entry (rule 8)

    window.app_state.undo()
    assert not any(eid in window.app_state.doc.style.elements
                   for eid in family)


def test_the_panel_still_names_the_segment_it_picked(window) -> None:
    """The fan-out does not make the readout lie: M2 labelled a segment
    'Hairpin (segment 1)' so nothing implies the whole spanner is
    SELECTED — it is the override that spreads, not the selection."""
    seg = _select(window, ElementKind.HAIRPIN, broken=True)
    label = window.inspector.selection_panel._values["Kind"].text()
    assert "segment" in label
    assert window.app_state.selected.element_id == seg.identity.element_id


# -- part scope (closes M4's F5) -----------------------------------------

def test_part_scope_writes_the_part_rule(window, panel) -> None:
    """M4's F5: per-part effect rules were honored and round-tripped but
    unauthorable, waiting on this panel."""
    el = _select(window, ElementKind.NOTEHEAD)
    part = el.identity.part
    panel._part_radio.setChecked(True)
    panel._effect.setCurrentText("pop")
    panel._commit_effect()
    assert window.app_state.doc.style.parts[part] == ElementStyle(effect="pop")
    assert window.app_state.undo_text() == "set part effect"
    assert window.app_state.doc.style.elements == {}   # not the element


def test_part_scope_is_unavailable_for_score_level_ink(window,
                                                       panel) -> None:
    """A barline carries no part (rule 13: score-level ink), so there is
    no part rule to write and the scope falls back."""
    _select(window, ElementKind.BARLINE)
    panel.sync()
    assert not panel._part_radio.isEnabled()
    assert panel._element_radio.isChecked()


def test_the_panel_re_derives_from_the_document(window, panel) -> None:
    """Undo/redo arrive as document_changed; the controls must follow
    rather than remember (the blockSignals resync idiom)."""
    _select(window, ElementKind.NOTEHEAD)
    panel._commit_color("#ff0000")
    assert panel._color_button.text() == "#ff0000"
    window.app_state.undo()
    assert panel._color_button.text() == "(inherit)"
    window.app_state.redo()
    assert panel._color_button.text() == "#ff0000"


# -- rule 13: the authored channel only ----------------------------------

def test_an_authored_colour_and_the_selection_tint_stay_distinguishable(
        window, panel) -> None:
    """The M2.8 inheritance, and the reason M3 could be built at all: a
    user who colours an element the SELECTION's own orange must still be
    able to see that it is selected. M3 writes only the authored
    channel; ElementItem composes the tint on top, falling back to
    SELECTION_ALT_COLOR when the two would collide."""
    from scoreanim.core.selection.highlight import (SELECTION_ALT_COLOR,
                                                    SELECTION_COLOR)

    el = _select(window, ElementKind.NOTEHEAD)
    item = window._scenes.items[el.identity.element_id]
    painted = item._tracked[0][0]

    panel._commit_color(SELECTION_COLOR)
    # the AUTHORED channel really is the selection colour...
    assert item.color.name().lower() == SELECTION_COLOR.lower()
    # ...and the element is still visibly selected, in the fallback
    assert item.selected is True
    assert painted.brush().color().name().lower() == \
        SELECTION_ALT_COLOR.lower()

    # deselecting re-derives the composite: the authored colour, plain
    window.app_state.set_selection(None)
    assert painted.brush().color().name().lower() == SELECTION_COLOR.lower()


def test_the_authored_colour_survives_selecting_and_deselecting(
        window, panel) -> None:
    """DocumentSync.sync_styles is a diff cache; anything that wrote the
    authored colour behind its back would leave it unable to restore."""
    el = _select(window, ElementKind.NOTEHEAD)
    item = window._scenes.items[el.identity.element_id]
    panel._commit_color("#1c4fd6")
    for _ in range(3):
        window.app_state.set_selection(None)
        window.app_state.set_selection(el.identity)
    window.app_state.set_selection(None)
    assert item._tracked[0][0].brush().color().name().lower() == "#1c4fd6"
