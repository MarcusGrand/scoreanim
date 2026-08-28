"""The icon system: the vendored files, the tint, and the exact sizes.

Headless — what an icon LOOKS like is a job for the eye, but three
things can be checked without one: that every vendored drawing still
carries the `currentColor` the tint depends on, that the three states
come out in the three tokens, and that a 1x and a 2x screen each get a
pixmap rendered at that size rather than a resampled one.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from scoreanim.ui.theme import icons
from scoreanim.ui.theme import palette as tokens


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _ink_colour(pixmap) -> str:
    """The colour of the most opaque pixel — the stroke itself."""
    image = pixmap.toImage()
    pixels = ((image.pixelColor(x, y), image.pixelColor(x, y).alpha())
              for x in range(image.width()) for y in range(image.height()))
    colour, alpha = max(pixels, key=lambda pair: pair[1])
    assert alpha > 0, "the icon drew nothing"
    return colour.name()


def test_something_is_vendored():
    assert len(icons.names()) >= 10


def test_every_vendored_file_can_be_tinted():
    # `currentColor` is the whole tinting mechanism: a file that lost it
    # would silently render in Lucide's own black
    for name in icons.names():
        text = (icons.ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")
        assert "currentColor" in text, name


def test_every_vendored_file_draws(qapp):
    for name in icons.names():
        assert not icons.icon(name).pixmap(24, 24).isNull(), name


def test_an_unknown_name_says_so(qapp):
    with pytest.raises(FileNotFoundError):
        icons.icon("no-such-icon")


def test_the_three_states_are_the_three_tokens(qapp):
    icon = icons.icon("play")
    size = QSize(24, 24)
    assert _ink_colour(icon.pixmap(
        size, QIcon.Mode.Normal, QIcon.State.Off)) == tokens.TEXT
    assert _ink_colour(icon.pixmap(
        size, QIcon.Mode.Normal, QIcon.State.On)) == tokens.ACCENT
    assert _ink_colour(icon.pixmap(
        size, QIcon.Mode.Disabled, QIcon.State.Off)) == tokens.DISABLED


@pytest.mark.parametrize("logical", [icons.TOOLBAR_SIZE, icons.BUTTON_SIZE])
@pytest.mark.parametrize("ratio", [1.0, 2.0])
def test_both_screens_get_a_rendered_pixmap(qapp, logical, ratio):
    # a Retina window asks for size x 2 real pixels; if we had not
    # rendered that size, Qt would hand back a resampled — soft — one
    pixmap = icons.icon("play").pixmap(logical, ratio)
    assert pixmap.size() == logical * ratio
    assert pixmap.devicePixelRatio() == ratio


def test_the_same_icon_is_handed_out_once(qapp):
    assert icons.icon("play") is icons.icon("play")
