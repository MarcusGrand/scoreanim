"""The command contract: pure transforms over the immutable ProjectDoc
(CLAUDE.md rule 8). Shared validation bits live here too."""
from __future__ import annotations

import abc
import re

from scoreanim.core.project.document import ProjectDoc

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")


class CommandError(ValueError):
    """Invalid command input for the current document."""


class Command(abc.ABC):
    @abc.abstractmethod
    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        """Pure transform; raises CommandError; never mutates ``doc``."""

    @abc.abstractmethod
    def describe(self) -> str:
        """Short lowercase phrase for Edit-menu text ("undo <this>")."""
