"""The document's two page colours, read from the sparse style entry.

The whole point of `read_colors` is that it cannot fail: a hand-edited
project file must never be able to produce a score nobody can see. So
most of this file is nonsense in, defaults out — one key at a time, so a
bad ink cannot take the background down with it.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation.page_colors import (DEFAULT_BACKGROUND,
                                                  DEFAULT_INK, PageColors,
                                                  read_colors)


def test_nothing_stored_is_the_look_the_app_has_always_had() -> None:
    for raw in (None, {}):
        colors = read_colors(raw)
        assert colors.background == DEFAULT_BACKGROUND == "#ffffff"
        assert colors.ink == DEFAULT_INK == "#000000"
        assert colors.is_default


def test_both_keys_are_read() -> None:
    colors = read_colors({"background": "#101014", "ink": "#f4f4f4"})
    assert (colors.background, colors.ink) == ("#101014", "#f4f4f4")
    assert not colors.is_default


def test_one_key_alone_leaves_the_other_at_its_default() -> None:
    """Sparse means sparse: setting the ink says nothing about paper."""
    assert read_colors({"ink": "#ffffff"}) == PageColors(
        background=DEFAULT_BACKGROUND, ink="#ffffff")
    assert read_colors({"background": "#000000"}) == PageColors(
        background="#000000", ink=DEFAULT_INK)


@pytest.mark.parametrize("stored,expected", [
    ("#ABC", "#aabbcc"),          # shorthand, expanded
    ("#abc", "#aabbcc"),
    ("#FF6A00", "#ff6a00"),       # normalized to lowercase
    ("  #ff6a00  ", "#ff6a00"),   # stray whitespace
])
def test_readable_colors_come_back_normalized(stored, expected) -> None:
    """Always lowercase "#rrggbb", so a caller can hand it straight to
    QColor without checking anything first."""
    assert read_colors({"ink": stored}).ink == expected


@pytest.mark.parametrize("bad", [
    "red",            # a colour NAME — not what this codebase stores
    "",
    "#",
    "#12345",         # wrong length
    "#1234567",
    "ffffff",         # no hash
    "#gggggg",        # not hex digits
    "#12 456",
    42, 1.0, None, True, ["#ffffff"], {"r": 1},
])
def test_an_unreadable_value_falls_back_to_its_own_default(bad) -> None:
    assert read_colors({"ink": bad}).ink == DEFAULT_INK
    assert read_colors({"background": bad}).background == DEFAULT_BACKGROUND


def test_a_bad_value_does_not_take_the_other_colour_down_with_it() -> None:
    """Per-field fallback: one broken key costs one colour, not the
    page. Without this a typo in the ink would silently restore white
    paper too, and the user would think both settings were lost."""
    colors = read_colors({"background": "#000000", "ink": "not a colour"})
    assert colors.background == "#000000"
    assert colors.ink == DEFAULT_INK


def test_keys_this_build_does_not_consume_are_simply_ignored() -> None:
    """A project from a newer build must not break this one — the
    effect_params guarantee, from the reading side."""
    colors = read_colors({"ink": "#ffffff", "staff_lines": "#888888"})
    assert colors.ink == "#ffffff"
    assert colors.background == DEFAULT_BACKGROUND


def test_is_default_is_about_the_value_not_the_key() -> None:
    """Storing the defaults explicitly still reads as default — which
    is what lets the recolour pass skip the sweep safely."""
    assert read_colors({"background": "#FFFFFF", "ink": "#000"}).is_default
