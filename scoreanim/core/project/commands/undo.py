"""The linear undo stack over (command, doc_before, doc_after) triples."""
from __future__ import annotations

from dataclasses import dataclass

from scoreanim.core.project.commands.base import Command, CommandError
from scoreanim.core.project.document import ProjectDoc


@dataclass(frozen=True)
class _Entry:
    command: Command
    before: ProjectDoc
    after: ProjectDoc


class UndoStack:
    """Linear undo. ``execute`` truncates the redo tail; ``mark_saved``
    pins the current position so ``is_dirty`` can drive the title-bar
    star. Undo/redo return stored document values — ``apply`` never
    re-runs."""

    _NEVER = -1                  # saved position lost to truncation

    def __init__(self) -> None:
        self._entries: list[_Entry] = []
        self._index = 0          # number of applied commands
        self._saved = 0

    def execute(self, command: Command, doc: ProjectDoc) -> ProjectDoc:
        after = command.apply(doc)
        del self._entries[self._index:]
        if self._saved > self._index:
            self._saved = self._NEVER
        self._entries.append(_Entry(command, doc, after))
        self._index += 1
        return after

    def undo(self) -> ProjectDoc:
        if not self.can_undo:
            raise CommandError("nothing to undo")
        self._index -= 1
        return self._entries[self._index].before

    def redo(self) -> ProjectDoc:
        if not self.can_redo:
            raise CommandError("nothing to redo")
        entry = self._entries[self._index]
        self._index += 1
        return entry.after

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._entries)

    def undo_text(self) -> str | None:
        return (self._entries[self._index - 1].command.describe()
                if self.can_undo else None)

    def redo_text(self) -> str | None:
        return (self._entries[self._index].command.describe()
                if self.can_redo else None)

    def mark_saved(self) -> None:
        self._saved = self._index

    @property
    def is_dirty(self) -> bool:
        return self._index != self._saved
