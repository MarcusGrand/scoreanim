"""The Delete action on a real MainWindow, offscreen.

The `tests/test_break_action.py` shape. What is pinned here is the
WIRING, not the policy (`tests/test_deletion_policy.py`) and not what
hiding does to the ink (`tests/test_render_scene.py`): a selected
object deletes in one undo step, a broken spanner goes as one object,
the selection clears, undo brings it back, and the action disables with
a reason on ink that may not be deleted.

The last section pins the shortcut SCOPE. It is stage-scoped rather
than window-scoped on purpose — the tempo lane already owns
Delete/Backspace for its points, and Qt matches shortcuts before the
key reaches the focused widget — so "someone registers it on the
window" is a real regression with a silent symptom, and it gets a test.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.editing.deletion import (ENABLED_TIP,  # noqa: E402
                                             MUSIC_INK, NO_SELECTION,
                                             SCAFFOLD_INK)
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.ui.main_window import MainWindow  # noqa: E402

# the nudge fixture: real hairpins, a hairpin AND a slur broken across
# systems, plus texts, dynamics, notes, rests and barlines — every case
# this module needs in one load
FIXTURE = (Path(__file__).parent.parent / "testdata"
           / "broken_hairpin_and_slur_test.musicxml")


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(FIXTURE)            # the real open path
    return win


def _select(window, predicate):
    """Select the first element matching `predicate`, through the real
    click path."""
    element = next(el for el in window.animation_inputs.layout.elements
                   if predicate(el))
    item = window._scenes.items[element.identity.element_id]
    window.selection.select_at(item.bbox.center(), item.scene())
    return element


def _of_kind(window, kind):
    return _select(window, lambda el: el.identity.kind is kind)


def _select_kind_directly(window, kind):
    """Put a selection of `kind` on AppState without going through the
    click path — a click at a notehead's centre can legitimately land on
    the slur above it, and what is being asked here is how the ACTION
    reacts to a selection, not who wins a hit (tests/test_hit_priority)."""
    element = next(el for el in window.animation_inputs.layout.elements
                   if el.identity.kind is kind)
    window.app_state.set_selection(element.identity)
    return element


def _visible(window, eid) -> bool:
    return window._scenes.items[eid].isVisible()


# -- the gesture ------------------------------------------------------------

def test_deleting_a_text_hides_it_in_one_undo_step(window) -> None:
    element = _of_kind(window, ElementKind.TEXT)
    eid = element.identity.element_id
    assert _visible(window, eid)

    window.delete_action.trigger()

    assert not _visible(window, eid)
    assert window.app_state.doc.layout_overrides[eid].hidden is True
    assert window.app_state.undo_text() == "delete element"
    window.app_state.undo()
    assert _visible(window, eid)
    assert window.app_state.doc.layout_overrides == {}


def test_the_selection_clears_when_its_object_goes(window) -> None:
    """Hidden ink is neither visible nor clickable, so a surviving
    selection would point at something nobody can reach."""
    _of_kind(window, ElementKind.DYNAMIC)
    assert window.app_state.selected is not None
    window.delete_action.trigger()
    assert window.app_state.selected is None
    assert window.selection.highlighted is None
    # and the action goes back to asking for a selection
    assert not window.delete_action.action.isEnabled()
    assert window.delete_action.action.statusTip() == NO_SELECTION


def test_a_broken_spanner_goes_as_one_object(window) -> None:
    """Every id of the `:seg` family, in the one undo entry."""
    family = [el.identity.element_id
              for el in window.animation_inputs.layout.elements
              if ":seg" in str(el.identity.element_id)
              and el.identity.kind in (ElementKind.SLUR, ElementKind.HAIRPIN)]
    assert family                             # the fixture's whole point
    source = str(family[0]).split(":seg")[0]
    ids = [eid for eid in window._scenes.items
           if str(eid) == source or str(eid).startswith(source + ":seg")]
    assert len(ids) > 1                       # non-vacuous: really broken

    _select(window, lambda el: str(el.identity.element_id) == source)
    window.delete_action.trigger()

    assert all(not _visible(window, eid) for eid in ids)
    assert set(window.app_state.doc.layout_overrides) == set(ids)
    window.app_state.undo()                   # ONE entry for all of them
    assert all(_visible(window, eid) for eid in ids)


def test_deleting_leaves_every_other_element_alone(window) -> None:
    element = _of_kind(window, ElementKind.HAIRPIN)
    source = str(element.identity.element_id)
    others = [eid for eid in window._scenes.items
              if not str(eid).startswith(source)]   # not its own :seg family
    window.delete_action.trigger()
    assert all(_visible(window, eid) for eid in others)


# -- when it may not fire ---------------------------------------------------

def test_disabled_with_no_selection(window) -> None:
    window.selection.clear()
    assert not window.delete_action.action.isEnabled()
    assert window.delete_action.action.statusTip() == NO_SELECTION


@pytest.mark.parametrize("kind,reason", [
    (ElementKind.NOTEHEAD, MUSIC_INK),
    (ElementKind.STEM, MUSIC_INK),
    (ElementKind.REST, MUSIC_INK),
    (ElementKind.BARLINE, SCAFFOLD_INK),
    # STAFF_LINES is not in this list because it cannot be SELECTED at
    # all (it is the backdrop tier, M2) — the policy covers it instead.
])
def test_disabled_on_ink_that_may_not_be_deleted(window, kind, reason) -> None:
    _select_kind_directly(window, kind)
    action = window.delete_action.action
    assert not action.isEnabled()
    assert action.statusTip() == reason


def test_enabled_tip_says_the_music_is_unchanged(window) -> None:
    _of_kind(window, ElementKind.TEXT)
    action = window.delete_action.action
    assert action.isEnabled()
    assert action.statusTip() == ENABLED_TIP
    assert "restore" in action.statusTip().lower()


# -- the shortcut is stage-scoped, not window-scoped ------------------------

def test_delete_is_a_stage_shortcut_so_the_tempo_lane_keeps_its_own(window):
    action = window.delete_action.action
    assert action.shortcutContext() is \
        Qt.ShortcutContext.WidgetWithChildrenShortcut
    assert action in window.view.actions()
    # the regression this guards: registering it window-level (the break
    # actions' idiom) would eat the tempo lane's point deletion
    assert action not in window.actions()


def test_both_delete_keys_are_bound(window) -> None:
    """The Mac laptop key labelled "delete" sends Backspace."""
    keys = {seq[0].key() for seq in window.delete_action.action.shortcuts()}
    assert keys == {Qt.Key.Key_Backspace, Qt.Key.Key_Delete}


def test_the_edit_menu_hosts_the_same_action_object(window) -> None:
    assert window.delete_action.action in window.menus.edit_menu.actions()


# -- export parity ----------------------------------------------------------
#
# The live stage and an exported frame must agree about a deletion, and
# they take different paths to it: the stage diffs the override onto its
# scenes, export applies the whole override map to private scenes it
# built itself. The M3 nudge harness, one field over.

def _digest(image) -> str:
    import hashlib
    rgba = image.convertToFormat(image.format())
    return hashlib.sha256(bytes(rgba.constBits())).hexdigest()


def _render(window):
    """One export frame at t=0 through the real FrameRenderer, carrying
    the document's overrides exactly as FileActions passes them."""
    from scoreanim.core.animation import StyleRules
    from scoreanim.core.timing import TempoMap
    from scoreanim.render.export import ExportFormat, ExportSpec, FrameRenderer

    doc = window.app_state.doc
    spec = ExportSpec(fps=30, height=360, start_seconds=0.0,
                      end_seconds=0.1, offset_seconds=0.0,
                      format=ExportFormat.PNG_SEQUENCE, out_path=Path("x"))
    return FrameRenderer(window.animation_inputs, doc.style or StyleRules(),
                         TempoMap(list(doc.timing.tempo_events)), (), spec,
                         overrides=dict(doc.layout_overrides))


def test_a_deleted_spanner_is_absent_from_an_exported_frame(window) -> None:
    home = _digest(_render(window).render_frame(0))

    eid = _delete_via_selection(window, ElementKind.HAIRPIN)

    after = _render(window)
    assert not after._scenes.items[eid].isVisible()   # export's own scenes
    assert _digest(after.render_frame(0)) != home     # and it shows

    window.app_state.undo()
    # byte round trip: hiding is the ONLY thing the override contributed
    assert _digest(_render(window).render_frame(0)) == home


def test_a_deleted_slur_is_absent_from_an_exported_frame(window) -> None:
    home = _digest(_render(window).render_frame(0))
    eid = _delete_via_selection(window, ElementKind.SLUR)
    after = _render(window)
    assert not after._scenes.items[eid].isVisible()
    assert _digest(after.render_frame(0)) != home


def _delete_via_selection(window, kind):
    element = _select_kind_directly(window, kind)
    window.delete_action.trigger()
    return element.identity.element_id


def test_a_deleted_text_is_no_longer_reachable_by_a_double_click(
        window) -> None:
    """Hidden ink is out of every hit path, not just the selection's —
    otherwise a double-click would open an editor over ink nobody can
    see. The layout zone is the way back."""
    # the first TEXT that the editor actually opens on — page furniture
    # and part labels route differently (tests/test_text_edit.py)
    for el in window.animation_inputs.layout.elements:
        if el.identity.kind is not ElementKind.TEXT:
            continue
        item = window._scenes.items[el.identity.element_id]
        centre, scene = item.bbox.center(), item.scene()
        if window.text_edit.edit_at(centre, scene):
            break
    else:
        pytest.fail("no editable text in this fixture")
    window.text_edit.close()

    window.app_state.set_selection(el.identity)
    window.delete_action.trigger()

    assert not window.text_edit.edit_at(centre, scene)
