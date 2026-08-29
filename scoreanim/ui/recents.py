"""The Open Recent list: the last few scores and projects the user
opened (B1).

UI state, not document intent — it rides QSettings next to the window
geometry (rule 5), and nothing here is undoable. The store keeps
absolute paths, most recent first, no duplicates, capped at
`MAX_RECENTS`. The list-building itself is the pure `pushed` function,
so the ordering rule is testable without a settings store.

`RecentsMenu` is the submenu that shows the list. It rebuilds itself
every time it opens, so an entry added by an open in this session is
there without anyone having to tell the menu.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMenu, QWidget

MAX_RECENTS = 8

_KEY = "recent/files"


def pushed(paths: Sequence[str], entry: str,
           limit: int = MAX_RECENTS) -> list[str]:
    """The list with `entry` at the front: no duplicates, capped."""
    return [entry, *(p for p in paths if p != entry)][:limit]


class RecentFiles:
    """QSettings-backed list of recently opened scores and projects."""

    def __init__(self, settings: QSettings) -> None:
        self._settings = settings

    def paths(self) -> list[Path]:
        stored = self._settings.value(_KEY, [])
        if isinstance(stored, str):      # a one-entry list can come back
            stored = [stored]            # as a bare string
        return [Path(p) for p in (stored or []) if p]

    def add(self, path: Path) -> None:
        self._write(pushed([str(p) for p in self.paths()],
                           str(path.resolve())))

    def remove(self, path: Path) -> None:
        target = str(path)
        self._write([str(p) for p in self.paths() if str(p) != target])

    def clear(self) -> None:
        self._write([])

    def _write(self, paths: list[str]) -> None:
        self._settings.setValue(_KEY, paths)
        self._settings.sync()            # survive a restart, not just a
                                         # clean shutdown


class RecentsMenu(QMenu):
    """The File → Open Recent submenu.

    Rebuilt on every open from the store; `open_path` gets the path the
    user picked and decides what kind of file it is.
    """

    def __init__(self, recents: RecentFiles,
                 open_path: Callable[[Path], None],
                 parent: QWidget | None = None) -> None:
        super().__init__("Open Recent", parent)
        self._recents = recents
        self._open_path = open_path
        self.aboutToShow.connect(self.rebuild)
        self.rebuild()

    def rebuild(self) -> None:
        self.clear()
        paths = self._recents.paths()
        if not paths:
            empty = self.addAction("No Recent Files")
            empty.setEnabled(False)
            return
        for path in paths:
            action = self.addAction(path.name)
            action.setToolTip(str(path))
            action.triggered.connect(
                lambda checked=False, p=path: self._open_path(p))
