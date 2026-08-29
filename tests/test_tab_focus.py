"""The inspector's tab-fronting rule (C3), headless: a selection fronts
the Selection tab, clearing it puts the old tab back, and a tab the user
picked themselves is never taken away from them.
"""
from __future__ import annotations

from scoreanim.ui.tab_focus import TabFocus


def test_a_selection_fronts_the_selection_tab() -> None:
    focus = TabFocus()
    assert focus.selection_changed(True, "animate") == "selection"


def test_clearing_puts_the_old_tab_back() -> None:
    focus = TabFocus()
    focus.selection_changed(True, "animate")
    assert focus.selection_changed(False, "selection") == "animate"


def test_a_second_selection_does_not_front_again() -> None:
    """Clicking another note while one is selected leaves the tab alone —
    otherwise it would yank back a tab the user had just chosen."""
    focus = TabFocus()
    focus.selection_changed(True, "animate")
    assert focus.selection_changed(True, "selection") is None
    assert focus.selection_changed(False, "selection") == "animate"


def test_a_manual_choice_while_selected_is_respected() -> None:
    focus = TabFocus()
    focus.selection_changed(True, "animate")
    focus.tab_chosen("stage")             # the user takes over
    assert focus.selection_changed(True, "stage") is None
    assert focus.selection_changed(False, "stage") is None


def test_the_next_selection_starts_over_after_a_manual_choice() -> None:
    """Taking over ends with the episode: the tab the user is on when
    they select again is the one that comes back."""
    focus = TabFocus()
    focus.selection_changed(True, "animate")
    focus.tab_chosen("stage")
    focus.selection_changed(False, "stage")
    assert focus.selection_changed(True, "stage") == "selection"
    assert focus.selection_changed(False, "selection") == "stage"


def test_already_on_the_selection_tab_changes_nothing() -> None:
    focus = TabFocus()
    assert focus.selection_changed(True, "selection") is None
    assert focus.return_to is None
    assert focus.selection_changed(False, "selection") is None


def test_a_tab_chosen_with_nothing_selected_is_not_an_override() -> None:
    """Only a choice made DURING an episode counts; browsing the tabs
    beforehand must not disable the next flip back."""
    focus = TabFocus()
    focus.tab_chosen("stage")
    assert focus.selection_changed(True, "stage") == "selection"
    assert focus.selection_changed(False, "selection") == "stage"


def test_choosing_the_selection_tab_by_hand_also_takes_over() -> None:
    """They put it there themselves, so clearing leaves it there."""
    focus = TabFocus()
    focus.selection_changed(True, "animate")
    focus.tab_chosen("stage")
    focus.tab_chosen("selection")
    assert focus.selection_changed(False, "selection") is None


def test_a_clear_with_no_selection_is_harmless() -> None:
    """Document reset clears an empty selection; nothing to put back."""
    focus = TabFocus()
    assert focus.selection_changed(False, "stage") is None
