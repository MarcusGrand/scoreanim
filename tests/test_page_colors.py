"""Light mode and dark mode, read from the sparse style entry.

The whole point of `read_colors` is that it cannot fail: a hand-edited
project file must never be able to produce a score nobody can see. So
most of this file is nonsense in, light out.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation.page_colors import (DARK, DARK_BACKGROUND,
                                                  DARK_INK, LIGHT,
                                                  LIGHT_BACKGROUND, LIGHT_INK,
                                                  colors_for, read_colors)


def test_nothing_stored_is_the_look_the_app_has_always_had() -> None:
    for raw in (None, {}):
        colors = read_colors(raw)
        assert colors.mode == LIGHT
        assert colors.background == LIGHT_BACKGROUND == "#ffffff"
        assert colors.ink == LIGHT_INK == "#000000"
        assert colors.is_default
        assert not colors.is_dark


def test_dark_is_white_notation_on_a_dark_blue_grey() -> None:
    """Not on black: a white staff on pure black is harsh, and this is
    the tone the app's own dark chrome already uses."""
    colors = read_colors({"mode": "dark"})
    assert colors.mode == DARK
    assert (colors.background, colors.ink) == (DARK_BACKGROUND, DARK_INK)
    assert colors.background == "#1d1f24" and colors.ink == "#ffffff"
    assert colors.is_dark
    assert not colors.is_default
    # a blue-grey, not a neutral one: more blue than red
    r, b = int(DARK_BACKGROUND[1:3], 16), int(DARK_BACKGROUND[5:7], 16)
    assert b > r


def test_the_two_modes_are_the_reverse_of_each_other() -> None:
    """Each mode's ink is legible on its own paper, which is the only
    thing a mode has to guarantee."""
    for mode in (LIGHT, DARK):
        colors = colors_for(mode)
        assert colors.background != colors.ink


@pytest.mark.parametrize("stored", ["dark", "DARK", " Dark "])
def test_the_mode_is_read_case_and_space_insensitively(stored) -> None:
    assert read_colors({"mode": stored}).mode == DARK


@pytest.mark.parametrize("bad", [
    "midnight",       # a mode from a newer build
    "", "  ", "#000000", "black",
    42, 1.0, None, True, ["dark"], {"mode": "dark"},
])
def test_anything_unreadable_is_light(bad) -> None:
    """Light, not "the last thing that parsed": the fallback has to be
    the look every file has always had."""
    colors = read_colors({"mode": bad})
    assert colors.mode == LIGHT
    assert colors.is_default


def test_keys_this_build_does_not_consume_are_simply_ignored() -> None:
    """Per-colour fine-tuning may join this map later, and a project
    from a build that has it must not break this one."""
    colors = read_colors({"mode": "dark", "background": "#001122"})
    assert colors.mode == DARK
    assert colors.background == DARK_BACKGROUND     # the mode still rules


def test_light_stored_explicitly_still_reads_as_default() -> None:
    """Which is what lets the recolour pass skip the sweep safely."""
    assert read_colors({"mode": "light"}).is_default
