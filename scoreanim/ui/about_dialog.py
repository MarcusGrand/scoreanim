"""The About box (B3): what this is, and the four facts a bug report
needs.

No app version number, on purpose — there is no version constant in
this project to read, and `pyproject.toml`'s 0.0.1 has never matched
the build tags. Rather than print a number that is wrong, the box
prints what is true and checkable: the project file format this build
writes, and the Python and Qt it is running on. Add a version line here
the day the project keeps a version somewhere real.
"""
from __future__ import annotations

import platform

from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QMessageBox, QWidget

from scoreanim.core.project import PROJECT_VERSION

TITLE = "About ScoreAnim"

_TAGLINE = ("Animates an already-engraved score in time with a recorded "
            "performance, for overlay on video.")

_CREDITS = ("Built with PySide6 (Qt, LGPL), Verovio for the engraving, "
            "and music21 for reading MusicXML.")


def about_text() -> str:
    """The body of the box. Pure text, so a test can read it."""
    return (f"<h3>ScoreAnim</h3>"
            f"<p>{_TAGLINE}</p>"
            f"<p>Project file format v{PROJECT_VERSION}<br>"
            f"Python {platform.python_version()} · Qt {qVersion()}</p>"
            f"<p>{_CREDITS}</p>")


def show_about(parent: QWidget | None = None) -> None:
    QMessageBox.about(parent, TITLE, about_text())
