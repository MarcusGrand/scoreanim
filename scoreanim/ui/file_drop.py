"""Drag and drop over the whole window (E1).

A score or a project dropped anywhere on the window opens, whether the
welcome pane is showing or a score already is. What counts as openable
is the pure rule in `core/project/file_kinds.py`, so the drop, the
Open Recent list and the file dialogs all agree.

The window keeps the two Qt handlers — that is the only route Qt
offers, and a drag reaches the window because `StageView` has drops
turned off here: QGraphicsView switches them on in its own
constructor, and a drag that stops at a widget which ignores it is not
then offered to the parent. Accepting the ENTER is enough; Qt carries
that answer to the moves that follow.

Dropping onto a score that is already open ASKS first. Opening is not
undoable (ruling 2026-07-11), so a mis-aimed drag would otherwise throw
away the session's work with no way back.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QMessageBox

from scoreanim.core.project import first_openable

if TYPE_CHECKING:
    from scoreanim.ui.main_window import MainWindow


class FileDrops:
    """Takes the window's drag events: what to accept, and what a drop
    does once it lands."""

    def __init__(self, window: MainWindow) -> None:
        self._window = window
        window.setAcceptDrops(True)
        window.view.setAcceptDrops(False)   # see the module docstring

    def offer(self, event: QDragEnterEvent) -> None:
        """A drag arrived. Accept it only if it carries something we can
        open, so the pointer says 'no' over anything else rather than
        promising an open that would not happen."""
        if dropped_path(event) is not None:
            event.acceptProposedAction()

    def drop(self, event: QDropEvent) -> None:
        """It landed."""
        path = dropped_path(event)
        if path is None:
            return
        event.acceptProposedAction()
        if self._replaces_a_score() and not self._confirm(path):
            return
        self._window.files.open_file(path)

    def _replaces_a_score(self) -> bool:
        return self._window.app_state.doc.score is not None

    def _confirm(self, path: Path) -> bool:
        """Ask before an open throws the current session away."""
        lost = ("\n\nUnsaved changes will be lost."
                if self._window.app_state.is_dirty else "")
        answer = QMessageBox.question(
            self._window, "Open dropped file",
            f"Replace the score now open with {path.name}?{lost}",
            QMessageBox.StandardButton.Open
            | QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Open


def dropped_path(event: QDropEvent) -> Path | None:
    """The one file this drag carries that we can open, or None.

    Typed as the DROP event because that is the base class of all three
    drag events, so one reader serves the enter, the move and the drop.
    Only local files count: a URL dragged out of a browser has no path
    on this machine, and there is nothing to engrave.
    """
    data = event.mimeData()
    if not data.hasUrls():
        return None
    return first_openable(Path(url.toLocalFile()) for url in data.urls()
                          if url.isLocalFile())
