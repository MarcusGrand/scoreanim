"""The app's icons: Lucide SVGs, tinted to the theme.

The drawings are vendored next door in `icons/`, exactly as Lucide
ships them: a 24×24 stroke drawing that paints itself in
`currentColor`. That one word is the whole tinting mechanism — we swap
it for a colour token before handing the file to Qt, so an icon is
never a fixed colour and never needs a second file for a second state.

One call, `icon("play")`, returns a QIcon that already knows the three
looks a control needs, so no caller ever picks a colour:

- off and enabled — the theme's text colour
- on (a checked button or action) — the accent
- disabled — the same dim grey the rest of the app uses

A stroke drawing goes soft the moment Qt resamples it, so the QIcon
carries a pixmap rendered at every size the app asks for, at 1× and
2×. A Retina window and a plain one then both get an exact hit instead
of a scaled one.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from scoreanim.ui.theme import palette as tokens

ICON_DIR = Path(__file__).parent / "icons"

# The two sizes the app asks for: the toolbar reads a little bigger
# than a button inside a panel.
TOOLBAR_SIZE = QSize(18, 18)
BUTTON_SIZE = QSize(16, 16)

# Every size we render, in real pixels: the logical ones above and a
# couple of neighbours, each doubled for a 2× screen.
_LOGICAL = (16, 18, 20, 24)
_SIZES = tuple(sorted({size * scale for size in _LOGICAL
                       for scale in (1, 2)}))


@lru_cache(maxsize=None)
def icon(name: str) -> QIcon:
    """The named vendored icon, tinted for every state a control has.

    Cached, so the same QIcon is handed to every caller — treat it as
    read-only and never add pixmaps of your own to it.
    """
    result = QIcon()
    for state, on_colour in ((QIcon.State.Off, tokens.TEXT),
                             (QIcon.State.On, tokens.ACCENT)):
        for mode, colour in ((QIcon.Mode.Normal, on_colour),
                             (QIcon.Mode.Disabled, tokens.DISABLED)):
            for pixmap in _render(name, colour):
                result.addPixmap(pixmap, mode, state)
    return result


def names() -> tuple[str, ...]:
    """Every icon vendored under `icons/`, sorted."""
    return tuple(sorted(path.stem for path in ICON_DIR.glob("*.svg")))


@lru_cache(maxsize=None)
def _render(name: str, colour: str) -> tuple[QPixmap, ...]:
    """One drawing in one colour, at every size we render."""
    renderer = QSvgRenderer(QByteArray(_svg(name, colour).encode("utf-8")))
    if not renderer.isValid():
        raise ValueError(f"icon {name!r} is not an SVG Qt can draw")
    pixmaps = []
    for size in _SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter)
        painter.end()
        pixmaps.append(pixmap)
    return tuple(pixmaps)


def _svg(name: str, colour: str) -> str:
    """The vendored file, with its `currentColor` swapped for a token."""
    path = ICON_DIR / f"{name}.svg"
    if not path.is_file():
        raise FileNotFoundError(f"no icon vendored under the name {name!r}")
    return path.read_text(encoding="utf-8").replace("currentColor", colour)
