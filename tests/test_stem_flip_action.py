"""The Flip Stem action on a real MainWindow, offscreen.

The `tests/test_delete_action.py` shape. What is pinned here is the
WIRING, not the policy (`tests/test_stem_flip_policy.py`) and not the
prep pass (`tests/test_stem_directions.py`): pressing F flips the
selected note's stem on the page in one undo step, pressing it again
puts it back, the selection survives the re-engrave, and the action
disables with a reason on ink that has no stem.

The last section pins the shortcut SCOPE. `F` is a BARE LETTER, and Qt
matches shortcuts before the key reaches the focused widget — so
registering it window-level would eat the "f" out of every text field
in the app. That is a real regression with a silent symptom, and it
gets a test.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation.scale_groups import (group_key,  # noqa: E402
                                                   heads_by_group,
                                                   stem_is_up)
from scoreanim.core.editing.stem_flip import (ENABLED_TIP,  # noqa: E402
                                              NO_SELECTION, NO_STEM,
                                              NOT_A_NOTE, SCAFFOLD_INK)
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.core.score.musicxml_stems import StemDirection  # noqa: E402
from scoreanim.ui.main_window import MainWindow  # noqa: E402

from .conftest import TESTSCORE


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(TESTSCORE)          # the real open path
    return win


def _drawn_direction(window, stem_id) -> str:
    """Which way that stem is pointing on the page right now, read off
    the geometry — the same reading the policy makes."""
    layout = window.animation_inputs.layout
    stem = next(el for el in layout.elements
                if el.identity.element_id == stem_id)
    heads = heads_by_group(layout)[group_key(stem.identity)]
    return "up" if stem_is_up(stem, heads) else "down"


def _select_kind(window, kind):
    """Put a selection of `kind` on AppState directly — what is asked
    here is how the ACTION reacts to a selection, not who wins a hit
    (tests/test_hit_priority)."""
    element = next(el for el in window.animation_inputs.layout.elements
                   if el.identity.kind is kind)
    window.app_state.set_selection(element.identity)
    return element


def _select_a_stem(window):
    element = next(el for el in window.animation_inputs.layout.elements
                   if el.identity.kind is ElementKind.STEM)
    window.app_state.set_selection(element.identity)
    return element.identity.element_id


# -- the gesture ------------------------------------------------------------

def test_flipping_turns_the_stem_over_in_one_undo_step(window) -> None:
    stem_id = _select_a_stem(window)
    before = _drawn_direction(window, stem_id)

    window.stem_flip_action.trigger()

    after = _drawn_direction(window, stem_id)
    assert after != before                       # it moved on the PAGE
    assert window.app_state.doc.stem_directions[stem_id] \
        == StemDirection(after)
    assert window.app_state.undo_text() == "flip stem"

    window.app_state.undo()
    assert window.app_state.doc.stem_directions == {}
    assert _drawn_direction(window, stem_id) == before


def test_pressing_f_twice_puts_the_note_back(window) -> None:
    """F cycles up and down only (Marcus, 2026-08-03) — so the second
    press is a flip back, not a reset to automatic. The entry stays in
    the document, naming the direction it now asks for."""
    stem_id = _select_a_stem(window)
    before = _drawn_direction(window, stem_id)

    window.stem_flip_action.trigger()
    flipped = _drawn_direction(window, stem_id)
    window.stem_flip_action.trigger()

    assert _drawn_direction(window, stem_id) == before
    assert flipped != before
    assert window.app_state.doc.stem_directions[stem_id] \
        == StemDirection(before)


def test_the_selection_survives_the_re_engrave(window) -> None:
    """A flip re-engraves the whole score, and `bind_scenes` re-resolves
    the held identity — a flip changes no part of an id, so the same
    note is still selected and F can fire again."""
    stem_id = _select_a_stem(window)
    window.stem_flip_action.trigger()
    assert window.app_state.selected is not None
    assert window.app_state.selected.element_id == stem_id
    assert window.stem_flip_action.action.isEnabled()


def test_flipping_a_notehead_flips_the_stem_it_belongs_to(window) -> None:
    """The user clicks the NOTE; the document keys the STEM."""
    layout = window.animation_inputs.layout
    stem = next(el for el in layout.elements
                if el.identity.kind is ElementKind.STEM)
    head = next(el for el in layout.elements
                if el.identity.kind is ElementKind.NOTEHEAD
                and group_key(el.identity) == group_key(stem.identity))
    window.app_state.set_selection(head.identity)
    before = _drawn_direction(window, stem.identity.element_id)

    window.stem_flip_action.trigger()

    assert set(window.app_state.doc.stem_directions) \
        == {stem.identity.element_id}
    assert _drawn_direction(window, stem.identity.element_id) != before


def test_a_flip_survives_save_and_reopen(window, tmp_path) -> None:
    from scoreanim.core.project import from_dict, to_dict
    stem_id = _select_a_stem(window)
    window.stem_flip_action.trigger()
    wanted = window.app_state.doc.stem_directions[stem_id]
    reopened = from_dict(to_dict(window.app_state.doc))
    assert reopened.stem_directions[stem_id] == wanted


# -- when it may not fire ---------------------------------------------------

def test_disabled_with_no_selection(window) -> None:
    window.selection.clear()
    assert not window.stem_flip_action.action.isEnabled()
    assert window.stem_flip_action.action.statusTip() == NO_SELECTION


@pytest.mark.parametrize("kind,reason", [
    (ElementKind.TEXT, NOT_A_NOTE),
    (ElementKind.DYNAMIC, NOT_A_NOTE),
    (ElementKind.REST, NOT_A_NOTE),
    (ElementKind.BARLINE, SCAFFOLD_INK),
])
def test_disabled_on_ink_with_no_stem(window, kind, reason) -> None:
    _select_kind(window, kind)
    action = window.stem_flip_action.action
    assert not action.isEnabled()
    assert action.statusTip() == reason


def test_enabled_tip_says_what_it_will_do(window) -> None:
    _select_a_stem(window)
    action = window.stem_flip_action.action
    assert action.isEnabled()
    assert action.statusTip() == ENABLED_TIP


def test_triggering_while_disabled_writes_nothing(window) -> None:
    window.selection.clear()
    window.stem_flip_action.trigger()
    assert window.app_state.doc.stem_directions == {}


# -- the shortcut is stage-scoped, not window-scoped ------------------------

def test_f_is_a_stage_shortcut_so_text_fields_keep_their_letter(window):
    action = window.stem_flip_action.action
    assert action.shortcutContext() is \
        Qt.ShortcutContext.WidgetWithChildrenShortcut
    assert action in window.view.actions()
    # the regression this guards: window-level, Qt would match F before
    # the key reached a focused text field, and nobody could type an "f"
    # into a title, a part label or the tempo box
    assert action not in window.actions()


def test_a_real_f_keystroke_flips_the_selected_note(window, qapp) -> None:
    """The structural assertions above say the action is scoped right;
    this one drives the actual key through Qt's shortcut system, which
    is the only way to know it fires at all."""
    from PySide6.QtTest import QTest
    window.show()
    window.activateWindow()
    QTest.qWaitForWindowExposed(window)

    stem_id = _select_a_stem(window)
    before = _drawn_direction(window, stem_id)
    window.view.setFocus()

    QTest.keyClick(window.view, Qt.Key.Key_F)
    qapp.processEvents()
    assert _drawn_direction(window, stem_id) != before

    QTest.keyClick(window.view, Qt.Key.Key_F)
    qapp.processEvents()
    assert _drawn_direction(window, stem_id) == before


def test_f_still_types_an_f_into_a_text_field(window, qapp) -> None:
    """The whole risk of a bare letter. A window-level F would be
    matched by Qt before the key reached the focused widget, and nobody
    could type an "f" into a title, a part label or a text box — so the
    check is empirical, not just a scope assertion."""
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit
    window.show()
    window.activateWindow()
    QTest.qWaitForWindowExposed(window)
    _select_a_stem(window)               # so the action WOULD be enabled
    assert window.stem_flip_action.action.isEnabled()

    for parent in (window, window.view):    # elsewhere, and on the stage
        box = QLineEdit(parent)
        box.show()
        box.setFocus()
        QTest.keyClicks(box, "flute")
        qapp.processEvents()
        assert box.text() == "flute"
        assert window.app_state.doc.stem_directions == {}


def test_the_key_is_a_bare_f(window) -> None:
    keys = {seq[0].key() for seq in
            window.stem_flip_action.action.shortcuts()}
    assert keys == {Qt.Key.Key_F}
    (seq,) = window.stem_flip_action.action.shortcuts()
    assert seq[0].keyboardModifiers() == Qt.KeyboardModifier.NoModifier


def test_the_edit_menu_hosts_the_same_action_object(window) -> None:
    assert window.stem_flip_action.action in window.menus.edit_menu.actions()


def test_f_does_not_collide_with_another_shortcut(window) -> None:
    """F5 (reload tempo) is a different key; nothing else claims a bare
    F. Checked over every action the window and the view carry."""
    others = [a for a in (*window.actions(), *window.view.actions())
              if a is not window.stem_flip_action.action]
    for action in others:
        for seq in action.shortcuts():
            assert not (seq[0].key() == Qt.Key.Key_F
                        and seq[0].keyboardModifiers()
                        == Qt.KeyboardModifier.NoModifier), action.text()
