"""Which files this app can open, and which opener a path wants.

Pure and tiny, so the rule lives in one place: the File menu's dialogs,
the Open Recent list and the window's drag-and-drop all ask here rather
than each spelling out a suffix of its own.

A score is a MusicXML export (`.musicxml`, and `.xml` because Dorico
still writes that); a project is our own `.scoreanim` file. Anything
else is not ours, and `kind_of` says so with None rather than guessing.
"""
from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from pathlib import Path

from scoreanim.core.project.serialize import SUFFIX

SCORE_SUFFIXES = (".musicxml", ".xml")


class FileKind(Enum):
    """What a path is, as far as opening it goes."""

    SCORE = "score"
    PROJECT = "project"


def kind_of(path: Path) -> FileKind | None:
    """The opener this path wants, or None for a file we cannot open.

    The suffix is matched without case: a file dialog on macOS hands
    back what the disk holds, and an export named `.XML` is still a
    score.
    """
    suffix = path.suffix.lower()
    if suffix == SUFFIX:
        return FileKind.PROJECT
    if suffix in SCORE_SUFFIXES:
        return FileKind.SCORE
    return None


def first_openable(paths: Iterable[Path]) -> Path | None:
    """The first path we can open out of a drop, or None.

    A drop can carry several files, and one window shows one score, so
    taking the first openable one is the whole policy — a drop of ten
    files is not ten windows, and a drop of a score beside its PDF
    should still open the score.
    """
    for path in paths:
        if kind_of(path) is not None:
            return path
    return None
