"""LiveField: a number field that previews as you type.

The default for any spinbox that edits the document: every keystroke
shows the result everywhere at once, and the whole typing session still
lands as ONE undo entry when the edit ends. It runs the same
preview/commit pair the lane drags use, so a typed edit and a dragged
one behave the same way.

The owner supplies `edit(value) -> Command | None` — the one function
both the preview and the commit call, so the two can never ask for
different edits. It must read `AppState.committed`, not `doc`: once a
preview is live, `doc` hands the field back its own preview, and a
no-op guard reading it would compare the value with itself and never
let anything commit. `None` means "this changes nothing", which drops
any preview already showing.

Three things the owner still does:

- call `resync(value)` from its `sync_from_document`, instead of
  writing `setValue` itself. A preview emits `document_changed` and
  comes straight back as a resync; `resync` skips the write while the
  edit is live, because it would rewrite the number under the cursor
  (`blockSignals` stops a re-commit, not that).
- call `set_enabled` rather than `spin.setEnabled`, so a resync can
  never gray out the box being typed in. Disabling drops focus, and
  focus-out commits — the resync would commit from inside itself.
- keep the field out of anything that re-engraves. Re-engraving
  commands run through `execute`, never `preview` — a re-engrave costs
  0.25-1.3 s, so it cannot happen per keystroke.

Every host keeps its fields in a `live_fields` tuple. That is what
holds them alive, and `tests/test_live_field.py` scans it: a spinbox
added without one fails the suite.

One field previews at a time. Moving focus to another spinbox ends the
first edit (Qt sends `editingFinished` on focus-out), and `AppState`
holds one preview slot anyway, so a second live field would silently
replace the first one's edit. Tests that drive fields directly should
finish one before starting the next.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox

from scoreanim.core.project import Command
from scoreanim.ui.app_state import AppState

SpinBox = QDoubleSpinBox | QSpinBox


class LiveField:
    """Wires one spinbox to preview on every keystroke and commit at the
    end of the edit. Held by the widget that owns the spinbox — that is
    what keeps the signal connections alive."""

    def __init__(self, spin: SpinBox, state: AppState,
                 edit: Callable[[float], Command | None],
                 on_change: Callable[[], None] | None = None) -> None:
        self.spin = spin                 # public: the enforcement test reads it
        self._state = state
        self._edit = edit
        self._on_change = on_change      # the host's own display state
        self._live = False               # this field owns a live preview
        # Keyboard tracking ON is what makes valueChanged fire per
        # keystroke. Qt only emits it for text that already validates in
        # the spinbox's range, so a half-typed number never previews.
        spin.setKeyboardTracking(True)
        spin.valueChanged.connect(self._preview)
        spin.editingFinished.connect(self.commit)

    def previewing(self) -> bool:
        """This field has an unfinished edit showing. Self-healing on
        purpose: an undo or a project load drops the preview out from
        under us, and the field goes back to following the document
        instead of sitting on a number nothing is showing."""
        return self._live and self._state.doc is not self._state.committed

    def resync(self, value: float) -> None:
        """Show what the document says — unless an edit is live, which
        owns the field until it ends. An int box takes an int (the
        document keeps seconds where the box shows whole ms)."""
        if self.previewing():
            return
        if isinstance(self.spin, QSpinBox):
            value = int(round(value))
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        self.spin.blockSignals(False)

    def set_enabled(self, enabled: bool) -> None:
        """Gray the field out — but never while it is being typed in.
        Disabling drops focus, and focus-out commits, so a resync that
        grayed a live field would commit from inside itself. The next
        resync after the edit ends puts it right."""
        if enabled or not self.previewing():
            self.spin.setEnabled(enabled)

    def drop(self) -> None:
        """Let go of a preview: the value is back where it started, or
        there is nothing to commit."""
        live, self._live = self.previewing(), False
        if live:
            self._state.cancel_preview()

    def commit(self) -> None:
        """Enter or focus-out ends the edit: one undo entry for the whole
        typing session, whatever the preview did along the way."""
        command = self._edit(self.spin.value())
        if command is None:
            self.drop()
        else:
            self._live = False           # clear first: commit lands back
            self._state.commit(command)  # here as a resync
        self._changed()

    def _preview(self, value: float) -> None:
        command = self._edit(value)
        if command is None:              # typed back to where it started
            self.drop()
        else:
            self._live = True
            self._state.preview(command)
        self._changed()

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change()
