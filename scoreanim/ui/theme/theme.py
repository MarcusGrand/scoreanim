"""Applies the one dark theme: Fusion, a QPalette, and one QSS string.

Called once from `scoreanim/app.py`, before any window exists, so every
widget is born dark. Nothing else in the app sets a colour on a widget —
if something looks wrong, it is fixed here or in `palette.py`.

Two jobs, because Qt needs both:

- The **palette** is what widgets ask for when they draw themselves. It
  reaches most of a Fusion widget: backgrounds, text, fields, selection.
- The **stylesheet** covers what a palette cannot say — dock title bars,
  the toolbar, our section headers, field padding, scrollbars, the flat
  look of a menu bar. It lives next door, in `stylesheet.py`.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from scoreanim.ui.theme import palette as tokens
from scoreanim.ui.theme.stylesheet import stylesheet


def apply_theme(app: QApplication) -> None:
    """Make `app` dark. Call before creating the main window."""
    style = QStyleFactory.create("Fusion")
    if style is not None:            # Fusion ships with Qt; belt and braces
        app.setStyle(style)
    app.setPalette(build_palette())
    app.setStyleSheet(stylesheet())


def build_palette() -> QPalette:
    """The token set as a QPalette, for the roles Fusion draws with."""
    panel = QColor(tokens.PANEL)
    inset = QColor(tokens.INSET)
    border = QColor(tokens.BORDER)
    text = QColor(tokens.TEXT)
    dim = QColor(tokens.DIM)
    disabled = QColor(tokens.DISABLED)

    pal = QPalette()
    # Window is the role a plain widget paints with, so it carries the
    # RAISED surface: docks, dialogs, the toolbar. The window's own
    # ground (`WINDOW`) is darker and is painted by the stylesheet, on
    # the few widgets that are actually the ground.
    pal.setColor(QPalette.ColorRole.Window, panel)
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Base, inset)
    pal.setColor(QPalette.ColorRole.AlternateBase, panel)
    pal.setColor(QPalette.ColorRole.Text, text)
    pal.setColor(QPalette.ColorRole.PlaceholderText, dim)
    pal.setColor(QPalette.ColorRole.Button, panel)
    pal.setColor(QPalette.ColorRole.ButtonText, text)
    pal.setColor(QPalette.ColorRole.BrightText, QColor(tokens.ACCENT))
    # the one light surface in the app — the QSS says the same thing,
    # and these two are what a tooltip Qt draws without the stylesheet
    # would use
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(tokens.TIP))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(tokens.TIP_TEXT))
    pal.setColor(QPalette.ColorRole.Link, QColor(tokens.ACCENT))
    pal.setColor(QPalette.ColorRole.LinkVisited, dim)
    pal.setColor(QPalette.ColorRole.Highlight, QColor(tokens.HIGHLIGHT))
    pal.setColor(QPalette.ColorRole.HighlightedText, text)
    # the shades Fusion draws frames and bevels from
    pal.setColor(QPalette.ColorRole.Light, QColor(tokens.HOVER))
    pal.setColor(QPalette.ColorRole.Midlight, QColor(tokens.HOVER))
    pal.setColor(QPalette.ColorRole.Mid, border)
    pal.setColor(QPalette.ColorRole.Dark, border)
    pal.setColor(QPalette.ColorRole.Shadow, QColor(tokens.INSET))

    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    pal.setColor(QPalette.ColorGroup.Disabled,
                 QPalette.ColorRole.Highlight, border)
    pal.setColor(QPalette.ColorGroup.Disabled,
                 QPalette.ColorRole.HighlightedText, dim)
    return pal
