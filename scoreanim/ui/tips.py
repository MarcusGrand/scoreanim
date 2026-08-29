"""Every control says what it does, and a dead one says why (E2).

Three small mechanisms, so the wording is the only thing a panel has to
think about.

**A tooltip that carries its key.** `describe_action` writes the
sentence and appends the action's own shortcut in the platform's
notation, read off the QAction rather than typed out a second time — so
a rebound key cannot leave a stale tooltip behind. A menu already prints
the key beside the item; this is for the toolbar and strip buttons,
which are icons with nothing else to go on.

**A dead control says why.** `gate` is `setEnabled` plus the tooltip
swap: while a control is live it says what it does, and the moment it
grays out it says the reason instead. The sentence it goes back to is
remembered on the widget itself, so a panel writes its tooltip once at
build time and never again.

**One phrase per reason, written down once.** A handful of them — no
score, no selection, nothing to undo — turn up in several panels, and
two panels wording the same block differently is how a UI starts to
feel careless.

Everything here works on a QAction and on a widget alike: both answer
`isEnabled`, `setToolTip` and `setProperty`, and that is the whole
surface used.

`tests/test_tooltips.py` walks the built window and fails on a control
with nothing to say, so a new button cannot arrive without its
sentence.
"""
from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence

# Where a control's live sentence is parked while a reason is showing in
# its place. A dynamic property, so nothing has to keep a side table of
# widgets — and a name of our own, so it cannot collide with Qt's.
_LIVE_TIP = "scoreanimLiveTip"

# The reasons more than one panel gives. A control that is dead for a
# reason of its own writes it inline; these are the shared ones.
NEEDS_SCORE = "Open a score first"
NEEDS_SELECTION = "Select something on the stage first"
NEEDS_AUDIO = "Load a recording first"
NOTHING_TO_UNDO = "Nothing to undo"
NOTHING_TO_REDO = "Nothing to redo"


def describe(target, text: str) -> None:
    """The sentence a control shows while it is live.

    Call it once, while building. `gate` may cover it with a reason
    later and puts this back when the control comes alive again.
    """
    target.setProperty(_LIVE_TIP, text)
    target.setToolTip(text)


def describe_action(action: QAction, text: str) -> None:
    """`describe`, plus the action's own shortcut in the platform's
    notation — "Save the project (⌘S)".

    Set the shortcut before calling this: the key is read off the action
    here, not remembered.
    """
    key = shortcut_text(action)
    describe(action, f"{text} ({key})" if key else text)


def gate(target, enabled: bool, reason: str) -> None:
    """Enable or disable a control, and say why while it is dead.

    An empty `reason` leaves the live sentence showing, which is right
    for a control that is grayed for a reason already obvious on screen.
    """
    target.setEnabled(enabled)
    live = target.property(_LIVE_TIP) or ""
    target.setToolTip(live if enabled or not reason else reason)


def live_tip(target) -> str:
    """What `gate` would put back — the tests' handle, and a panel's way
    of re-reading its own wording."""
    return target.property(_LIVE_TIP) or ""


def shortcut_text(action: QAction) -> str:
    """An action's first shortcut as the platform writes it, or "" for
    an action that has none.

    The first: an action may carry two keys for one gesture (Delete and
    Backspace are one key to most people), and a tooltip naming both
    reads as two different things to press.
    """
    keys = action.shortcuts()
    if not keys:
        return ""
    return keys[0].toString(QKeySequence.SequenceFormat.NativeText)
