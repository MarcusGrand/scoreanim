"""Shared look of the timeline lane: the colours and paddings the host
widget and every lane mode draw with.

Its own module on purpose: the host imports its modes, so a mode cannot
import the host back for a colour without a circular import.
"""
from __future__ import annotations

from PySide6.QtGui import QColor

BG = QColor("#1d1f24")
GRID = QColor("#33363d")
GRID_TEXT = QColor("#8a8f99")
PLAYHEAD = QColor("#e8b34a")
# a locked grid line: warmer and stronger than the playhead's
# amber, which it sits next to
LOCK = QColor("#f2761f")

TOP_PAD = 16                     # measure-number strip
BOTTOM_PAD = 6
HIT_PX = 7.0                     # pointer hit radius
BPM_MIN, BPM_MAX = 20.0, 400.0
