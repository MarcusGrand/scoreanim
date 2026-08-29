"""Which inspector tab shows while something is selected (C3).

Selecting a note on the stage is a question — what did I just click? —
and the answer is in the Selection tab. So a selection brings that tab
to the front, and clearing it puts back the tab the user was on.

The rule that makes it feel right is the third one: **the user's own
choice always wins.** If they switch tabs while a note is selected, the
tab stays where they put it, and clearing the selection leaves it
there.

Qt-free on purpose, so the whole rule is headless-testable
(tests/test_tab_focus.py). It is a small state machine over one
episode — the stretch from "nothing selected" to "nothing selected
again" — and it holds two things:

- `_episode`: a selection is up. Fronting happens once, at the start of
  an episode, never again inside it. Without this, clicking a second
  note would yank a tab the user had just chosen.
- `_return_to`: the tab to put back when the episode ends, or None for
  "leave the tab alone". It is None from the start when the Selection
  tab was already showing, and a manual tab choice clears it — which is
  how one field expresses both "nothing to go back to" and "the user
  has taken over".
"""
from __future__ import annotations

SELECTION_TAB = "selection"


class TabFocus:
    """The policy. `selection_changed` and `tab_chosen` are the two
    events; both return (or leave) the tab that should show."""

    def __init__(self, selection_tab: str = SELECTION_TAB) -> None:
        self._selection_tab = selection_tab
        self._episode = False
        self._return_to: str | None = None

    @property
    def return_to(self) -> str | None:
        """The tab a clear would put back right now — for tests and for
        anyone debugging why a flip did or did not happen."""
        return self._return_to

    def selection_changed(self, has_selection: bool,
                          active: str) -> str | None:
        """The stage selection changed. Returns the tab to switch to, or
        None to leave the tab where it is."""
        if has_selection:
            if self._episode:
                return None              # already inside one; hands off
            self._episode = True
            if active == self._selection_tab:
                self._return_to = None   # already there, nothing to undo
                return None
            self._return_to = active
            return self._selection_tab
        back = self._return_to
        self._episode = False
        self._return_to = None
        return back

    def tab_chosen(self, key: str) -> None:
        """The USER picked a tab (not us). Inside an episode that means
        they have taken over: no flip back when the selection clears."""
        if self._episode:
            self._return_to = None
