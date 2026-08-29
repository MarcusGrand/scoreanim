"""Arrow-key seeking (D1): move the playhead without touching a control.

The seek bar is gone — the waveform and ticks lanes are the seek
surface now — so the keyboard seeking that used to come free with a
QSlider is built here instead, on its own actions.

**Window-level, so it works wherever you are.** The old slider only
seeked while it had focus, which in practice meant almost never: the
stage keeps the focus. These actions are registered on the window with
`ui/menus.py`'s other window-level shortcuts, so an arrow seeks whether
you are looking at the score, the lanes, or the inspector.

**Two things get the arrows first, and Qt hands them over by itself.**
A key that matches a window shortcut normally never reaches the focused
widget — Qt sends the shortcut instead. The way out is the
ShortcutOverride event: a widget that answers it keeps the key.

- Text fields already do. `QLineEdit` and every spin box built on one
  claim Left, Right and Home for their own cursor, so typing in the
  Tempo box moves the caret and seeks nothing. Nothing here has to
  check for that, and nothing here should — a focus test would be a
  second list of "widgets that count as a text field", going quietly
  out of date.
- The stage claims them when something nudgeable is selected
  (`ui/stage_view.py`), because arrow keys have nudged the selection
  since M3.2 and that is the more specific meaning. Select a note and
  the arrows move it; select nothing and they move the playhead.

The amounts are the ordinary ones: one second for a plain arrow, five
for Shift. Both go through `PlaybackController.seek_by`, which clamps
to the timeline and leaves the play state alone.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QKeySequence

from scoreanim.ui.playback import PlaybackController

# One arrow press, and one arrow press with Shift, in seconds.
STEP_SECONDS = 1.0
JUMP_SECONDS = 5.0

_SHIFT = Qt.KeyboardModifier.ShiftModifier


class SeekKeys(QObject):
    """The four seek actions, in menu order.

    Held as `actions`: the Playback menu shows them (which is also how
    the shortcut sheet finds them — it harvests the menus) and the
    window registers those same objects window-level.

    Go to Start is deliberately NOT here. It is the transport strip's
    own action and already carries Home; giving it a second action here
    would put two objects behind one key.
    """

    def __init__(self, playback: PlaybackController,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._playback = playback
        self.actions = tuple(
            self._action(label, key, delta) for label, key, delta in (
                ("Back 1 Second", Qt.Key.Key_Left, -STEP_SECONDS),
                ("Forward 1 Second", Qt.Key.Key_Right, +STEP_SECONDS),
                ("Back 5 Seconds", _SHIFT | Qt.Key.Key_Left, -JUMP_SECONDS),
                ("Forward 5 Seconds", _SHIFT | Qt.Key.Key_Right,
                 +JUMP_SECONDS),
            ))

    def _action(self, label: str, key, delta: float) -> QAction:
        action = QAction(label, self)
        action.setShortcut(QKeySequence(key))
        action.triggered.connect(
            lambda _checked=False, d=delta: self._playback.seek_by(d))
        return action
