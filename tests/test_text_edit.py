"""In-place text editing (M3.1) on a real MainWindow, offscreen.

The affordance end to end: double-click resolves a text, the field
carries what is on screen, and committing runs the command that already
existed — one undo step, undoable back to where it started.

Also pins the two things the gesture must NOT do: reach for selection
(D5 stands — stage texts stay unselectable while being editable), and
leave an undo entry behind when nothing changed.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.editing import TextRoute  # noqa: E402
from scoreanim.core.project import (OVERLAY_PREFIX,  # noqa: E402
                                    AddCondenseGroup, CondenseGroup)
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
    win.files.open_score(TESTSCORE)
    return win


def _element(window, text_class: str):
    return next(el for el in window.animation_inputs.layout.elements
                if el.text_class == text_class)


def _center(window, eid) -> QPointF:
    return window._scenes.items[eid].sceneBoundingRect().center()


def _scene_of(window, eid):
    return window._scenes.items[eid].scene()


def _open_on(window, eid) -> bool:
    return window.text_edit.edit_at(_center(window, eid),
                                    _scene_of(window, eid))


def _type(window, content: str) -> None:
    window.text_edit._field.setText(content)
    window.text_edit._commit()


def _content(element) -> str:
    return "".join(run.content for text in element.glyph.texts
                   for run in text.runs)


def _left_edge_of_staves(window) -> float:
    """Where the music starts on page 1. The label column re-derives from
    the longest FULL name, so this moves when one grows (the "shifts to
    fit" pin). Page 1 only: later pages carry the short abbreviations."""
    return min(el.bbox.x for el in window.animation_inputs.layout.elements
               if el.identity.kind is ElementKind.STAFF_LINES
               and el.page == 1)


# -- part labels: the M3 exit criterion, paid in M7 ----------------------

def _labels(window, text_class: str = "label"):
    return [el for el in window.animation_inputs.layout.elements
            if el.text_class == text_class]


def test_every_part_label_carries_its_part(window) -> None:
    """The M7 attribution, from the app's side: a label reaches the part
    whose name it draws, so the rename route can be completed at all.
    Until M7 every label had part=None and this fixture opened nothing."""
    labels = _labels(window) + _labels(window, "labelAbbr")
    assert labels                                   # the fixture has them
    assert all(el.identity.part is not None for el in labels)
    for el in _labels(window):
        assert el.identity.part_name == _content(el)


def test_double_click_a_staff_label_renames_the_part(window) -> None:
    """THE M3 exit criterion: rename a staff label by double-clicking it,
    the score shifts to fit, and undo restores it."""
    label = _labels(window)[0]
    part = label.identity.part
    before = _left_edge_of_staves(window)
    assert _open_on(window, label.identity.element_id)
    _type(window, "Renamed Woodwinds Section")

    assert window.app_state.doc.text_overrides[part].name == \
        "Renamed Woodwinds Section"
    assert window.app_state.undo_text() == "set part name"
    # a re-engrave with a changed input: the label column re-derives, so a
    # longer name pushes the staves right (rule 7, Phase 9.3)
    assert _left_edge_of_staves(window) > before
    assert "Renamed Woodwinds Section" in [_content(el)
                                           for el in _labels(window)]

    window.app_state.undo()
    assert part not in window.app_state.doc.text_overrides
    assert _left_edge_of_staves(window) == pytest.approx(before)


def test_double_click_an_abbreviation_writes_only_the_abbreviation(window) \
        -> None:
    """Both label flavours are one document entry with two fields, so
    editing the running label must not clear the full name."""
    abbrev = _labels(window, "labelAbbr")[0]
    part = abbrev.identity.part
    assert _open_on(window, abbrev.identity.element_id)
    _type(window, "Zz.")

    override = window.app_state.doc.text_overrides[part]
    assert override.abbreviation == "Zz."
    assert override.name is None            # untouched: the score's own
    full = next(el for el in _labels(window) if el.identity.part == part)
    assert _content(full) not in ("Zz.", "")


def test_a_condensed_label_edits_the_group_not_the_part(window) -> None:
    """Ruling (2026-07-30): a merged staff's label IS the condense group's
    combined name, so editing it rewrites the group — one name in one
    place, which keeps the score and Score Setup agreeing."""
    order = tuple(p.part_id for p in window.text_edit._parts)
    window.app_state.execute(AddCondenseGroup(
        CondenseGroup(parts=order[:2], name="Merged 1.2",
                      abbreviation="Mgd. 1.2"), order))
    merged = next(el for el in _labels(window)
                  if _content(el) == "Merged 1.2")

    assert _open_on(window, merged.identity.element_id)
    _type(window, "Reeds 1.2")

    assert window.app_state.doc.condense_groups[0].name == "Reeds 1.2"
    assert window.app_state.doc.condense_groups[0].abbreviation == "Mgd. 1.2"
    assert window.app_state.doc.text_overrides == {}     # NOT the part
    assert window.app_state.undo_text() == "edit condense group"
    assert "Reeds 1.2" in [_content(el) for el in _labels(window)]


# -- engraved text -> the generalized overlay ----------------------------

def test_double_click_a_tempo_mark_overlays_it(window) -> None:
    """Phase 9.2's mechanism, reached by pointing at the mark: hide the
    engraved ink and add its replacement, ONE undo step."""
    tempo = _element(window, "tempo")
    eid = tempo.identity.element_id
    assert _open_on(window, eid)
    _type(window, "Fast")

    overlay = next(t for t in window.app_state.doc.stage.texts
                   if t.element_id == OVERLAY_PREFIX + str(eid))
    assert overlay.content == "Fast"
    assert window.app_state.doc.layout_overrides[eid].hidden is True
    assert window.app_state.undo_text() == "replace text"

    window.app_state.undo()                          # ONE step undoes both
    assert not any(t.element_id == OVERLAY_PREFIX + str(eid)
                   for t in window.app_state.doc.stage.texts)
    assert window.app_state.doc.layout_overrides == {}


def test_editing_the_overlay_again_edits_the_stage_text(window) -> None:
    """The seam D5 would have broken: after the first edit the thing on
    screen is a stage text, so a second double-click must route to
    EditStageText — overlaying twice is rejected outright."""
    tempo = _element(window, "tempo")
    eid = tempo.identity.element_id
    _open_on(window, eid)
    _type(window, "Fast")

    overlay_id = OVERLAY_PREFIX + str(eid)
    assert _open_on(window, overlay_id)
    assert window.text_edit._target.route is TextRoute.STAGE_TEXT
    _type(window, "Faster")
    assert window.app_state.undo_text() == "edit stage text"
    assert next(t for t in window.app_state.doc.stage.texts
                if t.element_id == overlay_id).content == "Faster"


@pytest.mark.parametrize("text_class", ["dir", "reh"])
def test_a_system_text_or_rehearsal_mark_edits_in_place(window,
                                                        text_class) -> None:
    """The M3 exit criterion "edit a system text in place", on the two
    engraved text classes that are neither tempo nor furniture. Same
    hide-plus-replace shape, same single undo step, no command edits —
    which is what "the tempo-overlay mechanism generalized" turned out
    to mean in practice."""
    el = _element(window, text_class)
    eid = el.identity.element_id
    assert _open_on(window, eid)
    _type(window, "Edited")

    overlay = next(t for t in window.app_state.doc.stage.texts
                   if t.element_id == OVERLAY_PREFIX + str(eid))
    assert overlay.content == "Edited"
    assert window.app_state.doc.layout_overrides[eid].hidden is True
    window.app_state.undo()
    assert not any(t.element_id == OVERLAY_PREFIX + str(eid)
                   for t in window.app_state.doc.stage.texts)


def test_a_measure_number_is_left_alone(window) -> None:
    """Page furniture is deliberately not editable in place (v1)."""
    el = _element(window, "mNum")
    assert not _open_on(window, el.identity.element_id)


# -- stage texts ---------------------------------------------------------

def test_double_click_a_stage_text_edits_it(window) -> None:
    texts = window.app_state.doc.stage.texts
    if not texts:
        pytest.skip("fixture seeds no stage texts")
    target = texts[0]
    assert _open_on(window, target.element_id)
    assert window.text_edit._field.text() == target.content
    _type(window, "Renamed")
    assert next(t for t in window.app_state.doc.stage.texts
                if t.element_id == target.element_id).content == "Renamed"
    assert window.app_state.undo_text() == "edit stage text"


# -- D5: editing is not selecting ----------------------------------------

def test_editing_a_stage_text_never_selects_it(window) -> None:
    """Ruling 2026-07-27: D5 stands. A stage text has no part, measure
    or onset, so it is not a rule-13 object and must never land in
    AppState.selection — but it is still editable."""
    texts = window.app_state.doc.stage.texts
    if not texts:
        pytest.skip("fixture seeds no stage texts")
    assert _open_on(window, texts[0].element_id)
    assert window.app_state.selected is None
    # and the selection controller still refuses to see it
    pos = _center(window, texts[0].element_id)
    window.selection.select_at(pos, _scene_of(window, texts[0].element_id))
    assert window.app_state.selected is None


# -- what must NOT happen ------------------------------------------------

def test_no_editor_on_a_notehead(window) -> None:
    note = next(el for el in window.animation_inputs.layout.elements
                if el.identity.kind is ElementKind.NOTEHEAD)
    assert not _open_on(window, note.identity.element_id)
    assert not window.text_edit.editing


def test_escape_cancels_without_a_command(window) -> None:
    # the fixture's open auto-imports testscore.tempo as a command, so
    # the stack is never empty — compare its TOP, not its emptiness
    top = window.app_state.undo_text()
    tempo = _element(window, "tempo")
    assert _open_on(window, tempo.identity.element_id)
    window.text_edit._field.setText("Discarded")
    window.text_edit.close()                     # what Esc calls
    assert not window.text_edit.editing
    assert window.app_state.undo_text() == top
    assert window.app_state.doc.layout_overrides == {}


def test_an_unchanged_commit_leaves_no_undo_entry(window) -> None:
    """Rule 8 in the direction people forget: open, commit what was
    already there, and the undo stack must be untouched."""
    top = window.app_state.undo_text()
    tempo = _element(window, "tempo")
    assert _open_on(window, tempo.identity.element_id)
    window.text_edit._commit()                   # same text, Enter
    assert window.app_state.undo_text() == top


def test_a_reengrave_closes_an_open_editor(window) -> None:
    """bind() runs on every load and re-engrave, and the item the field
    is positioned over is destroyed by it."""
    from scoreanim.core.project import SetHideEmptyStaves
    tempo = _element(window, "tempo")
    assert _open_on(window, tempo.identity.element_id)
    window.app_state.execute(SetHideEmptyStaves(
        not window.app_state.doc.hide_empty_staves))
    assert not window.text_edit.editing


# -- the real gesture ----------------------------------------------------

def test_the_view_double_click_reaches_the_editor(window) -> None:
    """Pin the wiring, not just the handler: a real double-click event
    on the view opens the field."""
    tempo = _element(window, "tempo")
    eid = tempo.identity.element_id
    window.router.show_page(tempo.page)
    viewport_pos = window.view.mapFromScene(_center(window, eid))
    window.view.mouseDoubleClickEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick, QPointF(viewport_pos),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier))
    assert window.text_edit.editing
