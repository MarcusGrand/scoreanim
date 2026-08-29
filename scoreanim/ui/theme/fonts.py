"""The one font the app asks for by name: a real fixed-width face.

Digits that change width make a running readout wiggle — the timecode
during playback (D1), the zoom percentage as you pinch (D2) — so both
ask for monospace here rather than each finding it their own way.
"""
from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase


def monospace() -> QFont:
    """The system's monospace face.

    `systemFont(FixedFont)` alone is not enough: on this platform it
    comes back naming a family called "monospace", which no machine
    actually has, so Qt quietly falls back to the proportional UI font
    and the digits wiggle again. The style hint is what makes the
    fallback land on a real fixed-width face.
    """
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    return font
