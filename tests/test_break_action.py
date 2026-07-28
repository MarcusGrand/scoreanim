"""M5.4 — the Score-menu break action on a real MainWindow, offscreen.

The `tests/test_selection_lifecycle.py` shape. What is pinned here is
the wiring, not the policy (`tests/test_break_policy.py`) or the seam
(`tests/test_system_breaks.py`): selecting a barline and triggering the
action re-engraves once and splits the system, undo merges it back, and
the action disables — with a reason on the status tip — in each of the
three cases D1's rider names.
"""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.editing.breaks import (FIRST_SYSTEM,  # noqa: E402
                                           LAST_MEASURE, MOVE_NO_MEASURE,
                                           MOVE_NO_SELECTION, NO_MEASURE,
                                           NO_SELECTION)
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.core.score.musicxml_prep import SystemBreak  # noqa: E402
from scoreanim.ui.break_action import (MOVE_UP_SHORTCUT,  # noqa: E402
                                       PAGE_SHORTCUT, SHORTCUT)
from scoreanim.ui.main_window import MainWindow  # noqa: E402

TESTSCORE = Path(__file__).parent.parent / "testdata" / "testscore.musicxml"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(TESTSCORE)          # the real open path
    return win


def _spans(window) -> dict[int, tuple[int, int]]:
    per: dict[int, list[int]] = defaultdict(list)
    for measure, system in sorted(
            window.break_action._system_of_measure.items()):
        per[system].append(measure)
    return {s: (ms[0], ms[-1]) for s, ms in sorted(per.items())}


def _select(window, predicate):
    """Select the first element matching `predicate`, through the real
    click path."""
    element = next(el for el in window.animation_inputs.layout.elements
                   if predicate(el))
    item = window._scenes.items[element.identity.element_id]
    window.selection.select_at(item.bbox.center(), item.scene())
    return element


def _barline_in(window, measure: int):
    return _select(window, lambda el: (
        el.identity.kind is ElementKind.BARLINE
        and str(el.identity.element_id) == f"score:m{measure}:barline:0"))


def _select_identity(window, element_id: str):
    """Put an identity straight onto AppState, skipping the hit path.

    Needed for the FINAL barline: testscore's `score:m19:barline:0` is a
    heavy double bar and a click at its bbox CENTRE lands in the gap
    between the two rules, outside the 6-unit tolerance, so it resolves
    to nothing. That is an M2 hit-geometry nuance, not an M5 one — and
    harmless here, because D6 disables the action on the last measure
    either way. These tests are about the wiring, so they set the state
    the action reads rather than depending on where the ink is."""
    element = next(el for el in window.animation_inputs.layout.elements
                   if str(el.identity.element_id) == element_id)
    window.app_state.set_selection(element.identity)
    return element


# -- the toggle -------------------------------------------------------------

def test_toggling_a_barline_splits_the_system(window) -> None:
    assert _spans(window) == {1: (1, 4), 2: (5, 8), 3: (9, 12),
                              4: (13, 16), 5: (17, 19)}
    _barline_in(window, 3)
    assert window.break_action.action.isEnabled()
    window.break_action.trigger()

    assert window.app_state.doc.system_break_overrides == {
        4: SystemBreak.FORCE}
    assert _spans(window) == {1: (1, 3), 2: (4, 4), 3: (5, 8), 4: (9, 12),
                              5: (13, 16), 6: (17, 19)}


def test_undo_merges_the_systems_back(window) -> None:
    before = _spans(window)
    _barline_in(window, 3)
    window.break_action.trigger()
    assert _spans(window) != before

    window.app_state.undo()
    assert window.app_state.doc.system_break_overrides == {}
    assert _spans(window) == before
    window.app_state.redo()
    assert _spans(window) != before


def test_one_reengrave_per_toggle(window, monkeypatch) -> None:
    """The break edit rides the loader's applied-input diff, so it must
    trip exactly one re-engrave — not zero (nothing would change) and
    not one per document-changed observer."""
    calls = []
    real = window.loader.load
    monkeypatch.setattr(window.loader, "load",
                        lambda *a, **kw: (calls.append(1), real(*a, **kw))[1])
    _barline_in(window, 3)
    assert not calls                       # selecting re-engraves nothing
    window.break_action.trigger()
    assert len(calls) == 1


def test_a_second_toggle_clears_the_override(window) -> None:
    """D4 step 1: press twice, nothing stored, layout back to baseline."""
    before = _spans(window)
    _barline_in(window, 3)
    window.break_action.trigger()
    # the re-engrave rebuilt every item, so re-select the same barline
    _barline_in(window, 3)
    assert "Clear" in window.break_action.action.text()
    window.break_action.trigger()
    assert window.app_state.doc.system_break_overrides == {}
    assert _spans(window) == before


def test_suppressing_an_encoded_break(window) -> None:
    """m9's break is encoded as new-system="yes", so the barline at the
    end of m8 offers SUPPRESS rather than FORCE."""
    _barline_in(window, 8)
    assert "Remove" in window.break_action.action.text()
    window.break_action.trigger()
    assert window.app_state.doc.system_break_overrides == {
        9: SystemBreak.SUPPRESS}
    assert _spans(window)[2] == (5, 12)


# -- the disabled states, each naming why (D1 rider) ------------------------

def test_disabled_with_nothing_selected(window) -> None:
    action = window.break_action.action
    assert not action.isEnabled()
    assert action.statusTip() == NO_SELECTION


def test_disabled_on_a_system_start_barline(window) -> None:
    """D3: the page-scoped left barline carries no measure."""
    _select(window, lambda el: (
        el.identity.kind is ElementKind.BARLINE
        and str(el.identity.element_id).startswith("score:p")))
    action = window.break_action.action
    assert not action.isEnabled()
    assert action.statusTip() == NO_MEASURE


def test_disabled_on_the_last_measures_barline(window) -> None:
    _select_identity(window, "score:m19:barline:0")
    action = window.break_action.action
    assert not action.isEnabled()
    assert action.statusTip() == LAST_MEASURE


def test_disabled_clears_its_status_tip_when_it_becomes_enabled(window) -> None:
    _select_identity(window, "score:m19:barline:0")
    assert window.break_action.action.statusTip() == LAST_MEASURE
    _barline_in(window, 3)
    assert window.break_action.action.statusTip() == ""


def test_triggering_a_disabled_action_does_nothing(window) -> None:
    """Defense in depth: the shortcut is registered window-level."""
    _select_identity(window, "score:m19:barline:0")
    window.break_action.trigger()
    assert window.app_state.doc.system_break_overrides == {}


# -- chrome -----------------------------------------------------------------

def test_the_action_has_a_shortcut_and_survives_the_per_load_rebuild(
        window) -> None:
    """The Score menu is cleared and repopulated on every load, so the
    action must be re-inserted by the menu builder rather than added
    once (D1 rider: it also carries a keyboard shortcut)."""
    action = window.break_action.action
    assert action.shortcut().toString() == SHORTCUT
    assert action in window.menus.score_menu.actions()
    window.files.open_score(TESTSCORE)          # a second load
    assert action in window.menus.score_menu.actions()


def test_the_action_survives_a_break_triggered_reengrave(window) -> None:
    _barline_in(window, 3)
    window.break_action.trigger()
    assert window.break_action.action in window.menus.score_menu.actions()


# -- D10 --------------------------------------------------------------------

def test_a_stale_override_warns_at_load(window) -> None:
    """D10: an ordinal past the end of the score had no effect, and the
    app says so through the same counted load-warning path as every
    other anomaly (flag-and-continue)."""
    from scoreanim.core.project import SetSystemBreak

    window.app_state.execute(SetSystemBreak(400, SystemBreak.FORCE))
    codes = [w.code for w in window.loader.load(
        TESTSCORE, window.app_state.doc.engraving, None,
        window.app_state.doc.style,
        system_breaks=window.app_state.doc.system_break_overrides).warnings]
    assert "break-override-inert" in codes


# -- M5.5: position and selection across the re-engrave ---------------------

def test_the_selection_survives_a_break_toggle(window) -> None:
    """D9: the barline you clicked is still selected afterwards, so
    toggling back needs no fresh click on ink that has just moved. The
    spike measured all 19 measure-scoped barline ids byte-identical
    across both edits, which is what makes this possible."""
    barline = _barline_in(window, 3)
    eid = barline.identity.element_id
    before = window._scenes
    window.break_action.trigger()

    assert window._scenes is not before        # it really re-engraved
    assert window.app_state.selected is not None
    assert window.app_state.selected.element_id == eid
    # the tint moved to the NEW item, not the destroyed one
    assert window.selection.highlighted is window._scenes.items[eid]
    # and the action is immediately ready to toggle back
    assert window.break_action.action.isEnabled()
    assert "Clear" in window.break_action.action.text()


def test_the_view_re_anchors_to_the_edited_measure(window) -> None:
    """D8: `show_current` would re-show the same INDEX, which after a
    break is different music. In system mode that jumps away from the
    edit; anchoring by measure keeps the stage where you were working."""
    from scoreanim.core.project import PresentationMode, SetPresentationMode

    window.app_state.execute(SetPresentationMode(PresentationMode.SYSTEM))
    _barline_in(window, 16)                    # last bar of system 4
    window.router.show_system(4)
    window.break_action.trigger()              # m17's break is encoded
    # systems 4 and 5 merged, so the edited measure is in system 4 —
    # and the router is looking at it rather than at a clamped index
    assert window.router.system == \
        window.break_action._system_of_measure[17]


def test_an_unrelated_reengrave_keeps_the_position(window) -> None:
    """Only a break edit re-anchors; everything else re-shows where it
    was (the anchor is diffed from the override map, so a change that
    touches no ordinal yields None)."""
    from scoreanim.core.project import SetHideEmptyStaves

    window.router.show_page(2)
    doc = window.app_state.doc
    window.app_state.execute(SetHideEmptyStaves(not doc.hide_empty_staves))
    assert window.router.page == 2


def test_undo_re_anchors_too(window) -> None:
    """The anchor is diffed against the loader's applied inputs rather
    than passed down from the action, so undo travels the same path."""
    _barline_in(window, 3)
    window.break_action.trigger()
    window.router.show_page(3)
    window.app_state.undo()
    assert window.router.page == 1             # back at the edited measure


# -- M5.7: move to previous system ------------------------------------------

def _notehead_in(window, measure: int):
    """Selected through the real click path, like the barline helper —
    the move-up action reads ANY object's implicit measure (rule 13)."""
    return _select(window, lambda el: (
        el.identity.kind is ElementKind.NOTEHEAD
        and f":m{measure}:" in str(el.identity.element_id)))


def test_move_up_joins_the_previous_system(window) -> None:
    """The gesture, end to end on the real window: m5-6 join system 1
    and the remainder m7-8 stays a system of its own."""
    assert _spans(window)[2] == (5, 8)
    _notehead_in(window, 6)
    assert window.break_action.move_up_action.isEnabled()
    window.break_action.trigger_move_up()

    assert window.app_state.doc.system_break_overrides == {
        5: SystemBreak.SUPPRESS, 7: SystemBreak.FORCE}
    assert _spans(window)[1] == (1, 6)
    assert _spans(window)[2] == (7, 8)


def test_move_up_is_one_undo_entry(window) -> None:
    """Rule 8 counts gestures, not documents touched: two ordinals, one
    step back to the original layout."""
    before = _spans(window)
    underneath = window.app_state.undo_text()   # whatever the load left
    _notehead_in(window, 6)
    window.break_action.trigger_move_up()
    assert _spans(window) != before

    assert window.app_state.undo_text() == "change system breaks"
    window.app_state.undo()
    assert window.app_state.doc.system_break_overrides == {}
    assert _spans(window) == before
    # ONE step back, not two: the stack is where the load left it
    assert window.app_state.undo_text() == underneath


def test_move_up_costs_one_reengrave(window, monkeypatch) -> None:
    calls = []
    real = window.loader.load
    monkeypatch.setattr(window.loader, "load",
                        lambda *a, **kw: (calls.append(1), real(*a, **kw))[1])
    _notehead_in(window, 6)
    window.break_action.trigger_move_up()
    assert len(calls) == 1


def test_move_up_from_a_systems_first_measure(window) -> None:
    """Not a disable case — the commonest use. m5 goes up alone."""
    _notehead_in(window, 5)
    window.break_action.trigger_move_up()
    assert _spans(window)[1] == (1, 5)
    assert _spans(window)[2] == (6, 8)


def test_move_up_of_a_last_measure_writes_only_the_merge(window) -> None:
    """No remainder to split off, so one entry — and no D10 warning for
    a gesture that worked (brief §M5.7.2 M1)."""
    _notehead_in(window, 8)
    window.break_action.trigger_move_up()
    assert window.app_state.doc.system_break_overrides == {
        5: SystemBreak.SUPPRESS}
    assert _spans(window)[1] == (1, 8)


def test_move_up_reverses_by_the_plain_toggle(window) -> None:
    """The composed gesture leaves a document the primitives still read
    correctly: toggling m4's barline afterwards clears the suppression
    rather than writing a second override on top of it."""
    _notehead_in(window, 6)
    window.break_action.trigger_move_up()
    _barline_in(window, 4)                     # targets ordinal 5
    assert "Clear" in window.break_action.action.text()
    window.break_action.trigger()
    assert window.app_state.doc.system_break_overrides == {
        7: SystemBreak.FORCE}


# -- the disabled states, each naming why -----------------------------------

def test_move_up_disabled_in_the_first_system(window) -> None:
    _notehead_in(window, 2)
    action = window.break_action.move_up_action
    assert not action.isEnabled()
    assert action.statusTip() == FIRST_SYSTEM


def test_move_up_disabled_with_nothing_selected(window) -> None:
    action = window.break_action.move_up_action
    assert not action.isEnabled()
    assert action.statusTip() == MOVE_NO_SELECTION


def test_move_up_disabled_for_an_object_carrying_no_measure(window) -> None:
    _select(window, lambda el: (
        el.identity.kind is ElementKind.BARLINE
        and str(el.identity.element_id).startswith("score:p")))
    action = window.break_action.move_up_action
    assert not action.isEnabled()
    assert action.statusTip() == MOVE_NO_MEASURE


def test_triggering_the_disabled_move_up_does_nothing(window) -> None:
    _notehead_in(window, 2)
    window.break_action.trigger_move_up()
    assert window.app_state.doc.system_break_overrides == {}


# -- chrome, position, selection --------------------------------------------

def test_move_up_has_a_shortcut_and_sits_in_the_score_menu(window) -> None:
    action = window.break_action.move_up_action
    assert action.shortcut().toString() == MOVE_UP_SHORTCUT
    assert action in window.menus.score_menu.actions()
    window.files.open_score(TESTSCORE)          # a second load
    assert action in window.menus.score_menu.actions()


def test_move_up_re_anchors_the_view_to_the_moved_music(window) -> None:
    """D14: the gesture changes TWO ordinals, and the anchor is the
    lower one — the merge half, which is where the moved music now is."""
    from scoreanim.core.project import PresentationMode, SetPresentationMode

    window.app_state.execute(SetPresentationMode(PresentationMode.SYSTEM))
    _notehead_in(window, 6)
    window.router.show_system(2)
    window.break_action.trigger_move_up()
    assert window.router.system == \
        window.break_action._system_of_measure[6] == 1


def test_the_selection_survives_a_move_up(window) -> None:
    """D9, unchanged: the object you selected is still selected, on the
    system it just moved to."""
    note = _notehead_in(window, 6)
    eid = note.identity.element_id
    window.break_action.trigger_move_up()

    assert window.app_state.selected is not None
    assert window.app_state.selected.element_id == eid
    assert window.selection.highlighted is window._scenes.items[eid]
    assert window.break_action._system_of_measure[6] == 1


# -- M6.5: the page toggle, on the same spine -------------------------------

def _pages(window) -> dict[int, int]:
    return dict(window.break_action._page_of_measure)


def _page_starts(window) -> tuple[int, ...]:
    first: dict[int, int] = {}
    for measure, page in _pages(window).items():
        first[page] = min(first.get(page, 1 << 30), measure)
    return tuple(v for _, v in sorted(first.items()))


def test_the_page_map_reaches_the_controller(window) -> None:
    """Derived per load and handed to the same bind() as the system map
    (§1.2 — no adapter change, no new EngravedScore field)."""
    assert _page_starts(window) == (1, 5, 13)
    assert _pages(window)[19] == 3


def test_toggling_a_barline_splits_the_page(window) -> None:
    from scoreanim.core.project import PageBreak

    _barline_in(window, 2)
    assert window.break_action.page_action.isEnabled()
    assert "Force" in window.break_action.page_action.text()
    window.break_action.trigger_page()

    assert window.app_state.doc.page_break_overrides == {3: PageBreak.FORCE}
    assert _page_starts(window) == (1, 3, 5, 13)
    assert window.app_state.doc.system_break_overrides == {}


def test_undo_merges_the_pages_back(window) -> None:
    before = _page_starts(window)
    _barline_in(window, 2)
    window.break_action.trigger_page()
    assert _page_starts(window) != before

    window.app_state.undo()
    assert window.app_state.doc.page_break_overrides == {}
    assert _page_starts(window) == before
    window.app_state.redo()
    assert _page_starts(window) != before


def test_one_reengrave_per_page_toggle(window, monkeypatch) -> None:
    calls = []
    real = window.loader.load
    monkeypatch.setattr(window.loader, "load",
                        lambda *a, **kw: (calls.append(1), real(*a, **kw))[1])
    _barline_in(window, 2)
    assert not calls
    window.break_action.trigger_page()
    assert len(calls) == 1


def test_a_second_page_toggle_clears_the_override(window) -> None:
    before = _page_starts(window)
    _barline_in(window, 2)
    window.break_action.trigger_page()
    _barline_in(window, 2)                     # the re-engrave rebuilt items
    assert "Clear" in window.break_action.page_action.text()
    window.break_action.trigger_page()
    assert window.app_state.doc.page_break_overrides == {}
    assert _page_starts(window) == before


def test_suppressing_an_encoded_page_break(window) -> None:
    """m5's break is encoded as new-page="yes", so the barline at the end
    of m4 offers SUPPRESS — and the systems must NOT merge with it (the
    §3.1 A3/A4 fix, all the way through the UI)."""
    from scoreanim.core.project import PageBreak

    _barline_in(window, 4)
    assert "Remove" in window.break_action.page_action.text()
    window.break_action.trigger_page()
    assert window.app_state.doc.page_break_overrides == {
        5: PageBreak.SUPPRESS}
    assert 5 not in _page_starts(window)
    assert _spans(window) == {1: (1, 4), 2: (5, 8), 3: (9, 12),
                              4: (13, 16), 5: (17, 19)}


def test_the_page_action_disables_with_each_reason(window) -> None:
    from scoreanim.core.editing.page_breaks import (LAST_MEASURE as PG_LAST,
                                                    NO_MEASURE as PG_NO_MEAS,
                                                    NOT_A_BARLINE as PG_NOT_BL)
    from scoreanim.core.editing.page_breaks import (
        NO_SELECTION as PG_NO_SEL)

    action = window.break_action.page_action
    assert not action.isEnabled() and action.statusTip() == PG_NO_SEL

    _select(window, lambda el: (
        el.identity.kind is ElementKind.BARLINE
        and str(el.identity.element_id).startswith("score:p")))
    assert not action.isEnabled() and action.statusTip() == PG_NO_MEAS

    _select(window, lambda el: el.identity.kind is ElementKind.NOTEHEAD)
    assert not action.isEnabled() and action.statusTip() == PG_NOT_BL

    _select_identity(window, "score:m19:barline:0")
    assert not action.isEnabled() and action.statusTip() == PG_LAST

    _barline_in(window, 2)                     # …and it clears when enabled
    assert action.isEnabled() and action.statusTip() == ""


def test_triggering_the_disabled_page_action_does_nothing(window) -> None:
    _select_identity(window, "score:m19:barline:0")
    window.break_action.trigger_page()
    assert window.app_state.doc.page_break_overrides == {}


def test_the_page_action_has_a_shortcut_and_sits_in_the_score_menu(
        window) -> None:
    action = window.break_action.page_action
    assert action.shortcut().toString() == PAGE_SHORTCUT
    assert action in window.menus.score_menu.actions()
    window.files.open_score(TESTSCORE)          # a second load
    assert action in window.menus.score_menu.actions()


def test_the_selection_survives_a_page_toggle(window) -> None:
    """D9 unchanged for pages: §3.3 measured measure-scoped ids surviving
    a page edit for the same reason they survive a system edit."""
    barline = _barline_in(window, 2)
    eid = barline.identity.element_id
    before = window._scenes
    window.break_action.trigger_page()

    assert window._scenes is not before        # it really re-engraved
    assert window.app_state.selected is not None
    assert window.app_state.selected.element_id == eid
    assert window.selection.highlighted is window._scenes.items[eid]
    assert window.break_action.page_action.isEnabled()
    assert "Clear" in window.break_action.page_action.text()


def test_the_view_re_anchors_after_a_page_edit(window) -> None:
    """D11: the anchor diff now reads BOTH maps, so a page gesture
    re-anchors on exactly the path a system gesture does."""
    window.router.show_page(3)
    _barline_in(window, 2)
    window.break_action.trigger_page()
    assert window.router.page == _pages(window)[3]


def test_undo_of_a_page_edit_re_anchors_too(window) -> None:
    _barline_in(window, 2)
    window.break_action.trigger_page()
    window.router.show_page(4)
    window.app_state.undo()
    assert window.router.page == 1


def test_a_page_force_clears_a_contradicting_system_suppress(window) -> None:
    """D3's prevention half through the UI, in ONE undo entry (rule 8):
    the document never ends up holding a pair that argues with itself."""
    from scoreanim.core.project import PageBreak, SystemBreak

    _barline_in(window, 8)
    window.break_action.trigger()              # system SUPPRESS at m9
    assert window.app_state.doc.system_break_overrides == {
        9: SystemBreak.SUPPRESS}

    # re-selected by identity, not by click: the merge moved m8's barline
    # into the middle of a system where the hit policy prefers other ink.
    # An M2 hit-geometry nuance, not an M6 one (the `_select_identity`
    # precedent above).
    _select_identity(window, "score:m8:barline:0")
    window.break_action.trigger_page()         # page FORCE at m9
    doc = window.app_state.doc
    assert doc.page_break_overrides == {9: PageBreak.FORCE}
    assert doc.system_break_overrides == {}    # cleared with it
    assert 9 in _page_starts(window)

    window.app_state.undo()                    # ONE entry restores both
    restored = window.app_state.doc
    assert restored.page_break_overrides == {}
    assert restored.system_break_overrides == {9: SystemBreak.SUPPRESS}


def test_a_system_suppress_clears_a_contradicting_page_force(window) -> None:
    """The mirror, also one entry."""
    from scoreanim.core.project import PageBreak, SystemBreak

    _barline_in(window, 8)
    window.break_action.trigger_page()         # page FORCE at m9
    assert window.app_state.doc.page_break_overrides == {9: PageBreak.FORCE}

    _select_identity(window, "score:m8:barline:0")
    window.break_action.trigger()              # system SUPPRESS at m9
    doc = window.app_state.doc
    assert doc.system_break_overrides == {9: SystemBreak.SUPPRESS}
    assert doc.page_break_overrides == {}

    window.app_state.undo()
    assert window.app_state.doc.page_break_overrides == {9: PageBreak.FORCE}


def test_a_stale_page_override_warns_at_load(window) -> None:
    """D8's inert code, through the same counted load-warning path as
    every other anomaly (flag-and-continue)."""
    from scoreanim.core.project import PageBreak, SetPageBreak

    window.app_state.execute(SetPageBreak(9999, PageBreak.FORCE))
    codes = [w.code for w in window.loader.load(
        TESTSCORE, window.app_state.doc.engraving, None,
        window.app_state.doc.style,
        page_breaks={9999: PageBreak.FORCE}).warnings]
    assert "page-break-override-inert" in codes
