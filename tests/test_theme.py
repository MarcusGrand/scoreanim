"""The dark theme: tokens are real colours, and the app-wide QSS is whole.

Headless — it builds the palette and the stylesheet, which is all the
theme is. What it LOOKS like is a job for the eye, not for pytest.
"""
from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from scoreanim.ui.theme import palette as tokens
from scoreanim.ui.theme import apply_theme, build_palette, stylesheet


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _token_names() -> list[str]:
    return [name for name, value in vars(tokens).items()
            if name.isupper() and isinstance(value, str)]


def test_every_token_is_a_colour():
    names = _token_names()
    assert len(names) >= 9
    for name in names:
        assert QColor(getattr(tokens, name)).isValid(), name


def test_stylesheet_has_no_leftover_placeholder(qapp):
    css = stylesheet()
    assert "$" not in css
    assert css.count("{") == css.count("}")


def test_stylesheet_says_nothing_about_check_indicators(qapp):
    # styling those subcontrols would make Qt stop drawing the tick
    assert "::indicator" not in stylesheet()


def test_palette_is_dark_and_readable(qapp):
    pal = build_palette()
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base,
                 QPalette.ColorRole.Button):
        assert pal.color(role).lightness() < 60, role
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        assert pal.color(role).lightness() > 150, role
    disabled = pal.color(QPalette.ColorGroup.Disabled,
                         QPalette.ColorRole.Text)
    assert disabled.lightness() < pal.color(QPalette.ColorRole.Text).lightness()


def test_apply_theme_sets_fusion_and_the_sheet(qapp):
    apply_theme(qapp)
    assert qapp.styleSheet() == stylesheet()
    # while a stylesheet is set, style() is the sheet's own wrapper; drop
    # it for a moment to see the style underneath
    qapp.setStyleSheet("")
    assert qapp.style().metaObject().className() == "QFusionStyle"
    qapp.setStyleSheet(stylesheet())
    assert qapp.palette().color(
        QPalette.ColorRole.Window).name() == tokens.PANEL


def test_painting_views_read_the_tokens(qapp):
    from scoreanim.ui import lane_style, lane_tempo, lane_ticks, stage_view
    from scoreanim.ui import waveform

    assert lane_style.BG.name() == tokens.INSET
    assert lane_style.PLAYHEAD.name() == tokens.PLAYHEAD
    assert waveform._PEAK.name() == tokens.WAVEFORM
    assert waveform._BG.name() == lane_style.BG.name()
    assert lane_ticks._BAR.name() == tokens.BAR_LINE
    assert lane_tempo._LINE.name() == tokens.TEMPO_LINE
    # the letterbox is the app's ground, the same dark as the window
    assert stage_view._LETTERBOX.name() == tokens.WINDOW
