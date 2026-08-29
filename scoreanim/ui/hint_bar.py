"""The status bar becomes a hint bar (D3).

The bar has two jobs and they do not fight, because Qt already
separates them: the hint lives in a normal widget, and a status message
is a TEMPORARY message, which hides the normal widgets while it shows
and puts them back when it times out. So an export line or a re-engrave
failure covers the hint for a few seconds and the hint returns on its
own — nothing here has to remember what it was saying.

That is also why every status message in the app now goes through
`HintBar.message` instead of `statusBar().showMessage`: a message with
no timeout never expires, and the hint would never come back.

What the bar SAYS is `core/editing/hints.py`, pure and headless-tested.
This class only gathers the answers, and it gathers each one from the
controller that owns that gesture — the delete and flip QActions'
enabled state, the break policy's resolve, the onset cursor's own "is
the line up", the nudge policy's kind test, the text editor's route. No
second opinion about what is possible can form here.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QFontMetrics, QKeySequence
from PySide6.QtWidgets import QLabel, QSizePolicy

from scoreanim.core.editing import is_nudgeable
from scoreanim.core.editing.hints import Gestures, hint_for, idle_hint

# How long a status message covers the hint. Long enough to read a
# failure, short enough that the bar goes back to being useful.
MESSAGE_MS = 6000


class HintLabel(QLabel):
    """A label that elides rather than widening the window.

    A hint runs to a sentence, and a QLabel asks for its whole text as a
    minimum width — which would make the app's minimum width depend on
    which note you clicked. So the full text is held here and only an
    elided copy is ever set on the widget."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("HintBar")
        self.setSizePolicy(QSizePolicy.Policy.Ignored,
                           QSizePolicy.Policy.Preferred)
        self._full = ""

    def full_text(self) -> str:
        return self._full

    def set_hint(self, text: str) -> None:
        self._full = text
        self._elide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        metrics = QFontMetrics(self.font())
        super().setText(metrics.elidedText(self._full,
                                           Qt.TextElideMode.ElideRight,
                                           max(0, self.width() - 2)))


class HintBar(QObject):
    """Owns the status bar's resting text. Built by the window once the
    controllers it reads exist."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._w = window
        self._label = HintLabel()
        self._label.setContentsMargins(4, 0, 4, 0)
        window.statusBar().addWidget(self._label, 1)
        # the selection is the hint's subject, so this one is direct;
        # a DOCUMENT change also moves what a gesture would do (the
        # break toggle flips between force and remove, a delete
        # disables itself), and the window calls sync() at the end of
        # its document pass rather than this class subscribing — the
        # pass must finish before the hint reads what it left behind
        window.app_state.selection_changed.connect(self.sync)
        self.sync()

    # -- the two states ----------------------------------------------------

    @property
    def text(self) -> str:
        """The hint as written (unelided) — the tests' handle."""
        return self._label.full_text()

    def sync(self) -> None:
        selection = self._w.app_state.selection
        if selection is None:
            self._label.set_hint(idle_hint(self._recording()))
            return
        self._label.set_hint(hint_for(selection, self._gestures(selection),
                                      self._w.app_state.measures))

    def message(self, text: str) -> None:
        """A transient status message, which the hint outlives."""
        self._w.statusBar().showMessage(text, MESSAGE_MS)

    # -- gathering ---------------------------------------------------------

    def _recording(self) -> str | None:
        audio = self._w.app_state.doc.audio
        return Path(audio.path).name if audio is not None else None

    def _gestures(self, selection) -> Gestures:
        """One question per gesture, asked of its owner.

        The three policy answers are PULLED (`current()`), not read off
        the QActions' enabled state, so this does not depend on whose
        selection_changed slot Qt happens to run first. The onset line
        is the exception and has to be: whether it can be grabbed is
        whether it is drawn, which is state. This class is built after
        the cursor, so the line is up or down before the hint asks."""
        w = self._w
        breaks = w.break_action.current()
        return Gestures(
            move=is_nudgeable(selection.kind),
            retime=w.onset_cursor.showing,
            edit_text=w.text_edit.can_edit(selection.element_id),
            flip_stem=w.stem_flip_action.current().enabled,
            delete=w.delete_action.current().enabled,
            break_offered=breaks.enabled,
            break_mode=breaks.mode,
            break_keys=w.break_action.action.shortcut().toString(
                QKeySequence.SequenceFormat.NativeText))
