"""How a selection looks (M2.8) — pure, no Qt.

The tint color and the collision handler that keeps a selection visible
on an element the user has already colored. The threshold is a judgment,
not a measurement, so the distance table it was read off is pinned here:
that table IS the argument, and if the constant moves it should move
because these numbers say so.
"""
from __future__ import annotations

import pytest

from scoreanim.core.selection.highlight import (SELECTION_ALT_COLOR,
                                                SELECTION_COLOR,
                                                SELECTION_MIN_OPACITY,
                                                color_distance,
                                                selection_color_for)

# Redmean distance from SELECTION_COLOR. The cut sits in the gap between
# "another orange" (<= 118) and "another hue" (>= 175).
_DISTANCES = {
    "#ff6a00": 0.0,        # the selection color itself
    "#f26a10": 31.9,       # muted orange
    "#ff7a18": 46.6,       # a near orange
    "#e07000": 54.5,       # dark orange
    "#ff8800": 60.0,       # brighter orange
    "#ff4500": 74.0,       # orangered
    "#ffa500": 118.0,      # css orange
    "#cc2222": 175.2,      # the suite's usual test tint
    "#ffcc00": 196.0,      # amber
    "#ff0000": 212.0,      # red
    "#800080": 355.1,      # purple
    "#008000": 405.4,      # green
    "#000000": 455.4,      # black — the default ink
}


@pytest.mark.parametrize("color,expected", sorted(_DISTANCES.items()))
def test_distance_table(color: str, expected: float) -> None:
    assert color_distance(color, SELECTION_COLOR) == pytest.approx(
        expected, abs=0.1)


def test_the_threshold_separates_oranges_from_other_hues() -> None:
    """The judgment, stated as the property it has to have."""
    oranges = [c for c, d in _DISTANCES.items() if d <= 118.0]
    others = [c for c, d in _DISTANCES.items() if d >= 175.0]
    assert all(selection_color_for(c) == SELECTION_ALT_COLOR
               for c in oranges), "an orange must not tint orange"
    assert all(selection_color_for(c) == SELECTION_COLOR
               for c in others), "a different hue tints with the constant"


def test_default_ink_gets_the_selection_color() -> None:
    assert selection_color_for(None) == SELECTION_COLOR
    assert selection_color_for("#000000") == SELECTION_COLOR


def test_the_fallback_cannot_itself_collide() -> None:
    """Only near-oranges ever reach the fallback, so the fallback only
    has to be far from those — pinned so a future retune of either
    constant cannot quietly break the property."""
    assert color_distance(SELECTION_ALT_COLOR, SELECTION_COLOR) > 400.0
    assert selection_color_for(SELECTION_ALT_COLOR) == SELECTION_COLOR


def test_distance_is_symmetric_and_zero_on_identity() -> None:
    assert color_distance("#123456", "#123456") == 0.0
    assert color_distance("#123456", "#654321") == pytest.approx(
        color_distance("#654321", "#123456"))


def test_shorthand_and_bad_input() -> None:
    assert color_distance("#fff", "#ffffff") == 0.0
    with pytest.raises(ValueError):
        color_distance("nonsense", SELECTION_COLOR)


def test_min_opacity_is_high_enough_to_read_over_an_empty_ghost_score() -> None:
    """The floor exists because floor_opacity may be 0 (an invisible
    ghost score), where a tint would otherwise be a tint on nothing."""
    assert SELECTION_MIN_OPACITY > 0.5


# -- on a recoloured page ------------------------------------------------------

def test_the_tint_survives_a_white_ink_page() -> None:
    """Page colours (2026-08-02) let the user make the score white on
    black, and the selection has to stay obvious on it. `_paint_color`
    asks about the EFFECTIVE colour, so on such a page the question is
    whether the tint is tellable apart from white — not from a black
    nobody can see.

    It is, comfortably: white sits further from the orange than the
    black default does. So nothing here had to change, and this test is
    what says so rather than an assumption in a commit message."""
    assert color_distance("#ffffff", SELECTION_COLOR) \
        > color_distance("#000000", SELECTION_COLOR)
    assert selection_color_for("#ffffff") == SELECTION_COLOR
    assert selection_color_for("#000000") == SELECTION_COLOR


@pytest.mark.parametrize("paper", ["#000000", "#101014", "#ffffff"])
def test_both_tints_stay_visible_against_any_paper(paper: str) -> None:
    """A tint is no use if it vanishes into the page behind it. Both
    constants clear the same threshold the collision handler uses,
    against black paper, near-black paper and white."""
    for tint in (SELECTION_COLOR, SELECTION_ALT_COLOR):
        assert color_distance(tint, paper) > 120.0, (tint, paper)
