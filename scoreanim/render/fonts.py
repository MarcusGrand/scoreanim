"""Bravura registration for the one music-glyph text run (the metronome
note in the tempo mark). The verovio pip package ships no OTF/TTF, but
its data/Bravura.css embeds the face as base64 WOFF2; Qt ≥ 6.7 usually
accepts WOFF2 via FreeType. Failure is tolerated: the single glyph falls
back to tofu (upstream deviation, BACKLOG item 3) — timeboxed, per plan.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

from PySide6.QtGui import QFontDatabase

_B64_RE = re.compile(r"base64,([A-Za-z0-9+/=]+)")


def register_bravura() -> bool:
    """Best-effort; returns True if Qt accepted the font."""
    try:
        import verovio
        css = Path(verovio.__file__).parent / "data" / "Bravura.css"
        match = _B64_RE.search(css.read_text())
        if not match:
            return False
        font_id = QFontDatabase.addApplicationFontFromData(
            base64.b64decode(match.group(1)))
        return font_id != -1 and \
            "Bravura" in QFontDatabase.applicationFontFamilies(font_id)
    except Exception:
        return False
