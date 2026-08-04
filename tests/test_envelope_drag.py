"""The envelope editor's pure half: the value↔pixel mapping, which
handle a press takes hold of, and what a drag on each one does.

The one property that has to hold whatever the mouse does: a drag can
never produce a shape `Envelope` refuses. Every drag here is checked
against that, and the last test fuzzes the whole canvas to say so on
positions nobody would think to write down.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation import MIN_GAP, EnvelopeSpec, spec_envelope
from scoreanim.core.editing import (Box, Handle, drag_attack, drag_release,
                                    drag_sustain, drag_swell, frac_of,
                                    handle_at, handle_points, level_of, x_of,
                                    y_of)

BOX = Box(x=10.0, y=8.0, w=230.0, h=100.0)


def spec(**over) -> EnvelopeSpec:
    """The step-1 defaults, with whatever the test wants changed."""
    values = dict(attack=0.10, sustain=1.0, swell_on=False, swell_pos=0.5,
                  swell_level=1.0, release=0.20)
    values.update(over)
    return EnvelopeSpec(**values)


# -- the mapping -------------------------------------------------------------

@pytest.mark.parametrize("frac", [0.0, 0.02, 0.1, 0.333, 0.5, 0.75, 1.0])
def test_time_round_trips_through_the_mapping(frac: float) -> None:
    assert frac_of(x_of(frac, BOX), BOX) == pytest.approx(frac, abs=1e-12)


@pytest.mark.parametrize("level", [0.0, 0.05, 0.25, 0.5, 0.9, 1.0])
def test_level_round_trips_through_the_mapping(level: float) -> None:
    assert level_of(y_of(level, BOX), BOX) == pytest.approx(level, abs=1e-12)


def test_the_box_corners_are_the_extremes() -> None:
    """Time 0 at the left edge, 1 at the right; level 1 at the TOP, 0 at
    the bottom — the screen's y runs the other way from the level's."""
    assert x_of(0.0, BOX) == BOX.x
    assert x_of(1.0, BOX) == BOX.x + BOX.w
    assert y_of(1.0, BOX) == BOX.y
    assert y_of(0.0, BOX) == BOX.y + BOX.h


def test_a_flat_box_maps_to_zero_rather_than_dividing_by_it() -> None:
    """A widget is laid out before it is sized, so a zero-width box
    reaches here — it must not raise."""
    flat = Box(x=0.0, y=0.0, w=0.0, h=0.0)
    assert frac_of(5.0, flat) == 0.0
    assert level_of(5.0, flat) == 0.0


# -- which handle a press takes -----------------------------------------------

def test_press_on_a_corner_takes_that_corner() -> None:
    points = handle_points(spec(), BOX)
    for handle in (Handle.ATTACK, Handle.RELEASE):
        x, y = points[handle]
        assert handle_at(spec(), BOX, x, y, 6.0) is handle


def test_press_along_the_hold_takes_the_sustain() -> None:
    """The held part is grabbed anywhere along its length, not at a
    point — it is a segment, not a corner."""
    shape = spec()
    y = y_of(shape.sustain, BOX)
    middle = x_of(0.5, BOX)
    assert handle_at(shape, BOX, middle, y, 6.0) is Handle.SUSTAIN
    assert handle_at(shape, BOX, middle, y + 40.0, 6.0) is None


def test_the_swell_point_wins_where_it_sits_on_the_hold() -> None:
    """It rides ON the held line, so hit-testing the segment first would
    bury it."""
    shape = spec(swell_on=True, swell_pos=0.5, swell_level=1.0)
    x, y = handle_points(shape, BOX)[Handle.SWELL]
    assert handle_at(shape, BOX, x, y, 6.0) is Handle.SWELL


def test_no_swell_handle_while_the_swell_is_off() -> None:
    shape = spec(swell_on=False)
    assert Handle.SWELL not in handle_points(shape, BOX)
    x, y = x_of(0.5, BOX), y_of(1.0, BOX)
    assert handle_at(shape, BOX, x, y, 6.0) is not Handle.SWELL


# -- the drags ----------------------------------------------------------------

def test_attack_follows_the_mouse() -> None:
    moved = drag_attack(spec(), BOX, x_of(0.35, BOX))
    assert moved.attack == pytest.approx(0.35)
    assert moved.sustain == 1.0 and moved.release == 0.20   # nothing else


def test_attack_stops_at_the_release_corner() -> None:
    """Dragged past the far corner it stops one gap short of it, rather
    than swapping the two round."""
    moved = drag_attack(spec(release=0.20), BOX, x_of(2.0, BOX))
    assert moved.attack == pytest.approx(0.80 - MIN_GAP)
    assert moved.release == pytest.approx(0.20)


def test_attack_stops_at_the_swell_point_when_there_is_one() -> None:
    shape = spec(swell_on=True, swell_pos=0.4)
    moved = drag_attack(shape, BOX, x_of(0.9, BOX))
    assert moved.attack == pytest.approx(0.4 - MIN_GAP)
    assert moved.swell_pos == pytest.approx(0.4)            # it did not move


def test_attack_stops_at_the_left_edge() -> None:
    moved = drag_attack(spec(), BOX, x_of(-0.5, BOX))
    assert moved.attack == 0.0


def test_release_follows_the_mouse_from_its_own_corner() -> None:
    moved = drag_release(spec(), BOX, x_of(0.6, BOX))
    assert moved.release == pytest.approx(0.4)
    assert moved.attack == pytest.approx(0.10)


def test_release_stops_at_the_attack_corner() -> None:
    moved = drag_release(spec(attack=0.30), BOX, x_of(-1.0, BOX))
    assert moved.release == pytest.approx(1.0 - (0.30 + MIN_GAP))
    assert moved.attack == pytest.approx(0.30)


def test_release_stops_at_the_swell_point_when_there_is_one() -> None:
    shape = spec(swell_on=True, swell_pos=0.6)
    moved = drag_release(shape, BOX, x_of(0.0, BOX))
    assert moved.release == pytest.approx(1.0 - (0.6 + MIN_GAP))
    assert moved.swell_pos == pytest.approx(0.6)


def test_release_can_be_dragged_away_to_nothing() -> None:
    moved = drag_release(spec(), BOX, x_of(1.5, BOX))
    assert moved.release == 0.0


def test_sustain_follows_the_mouse_and_clamps_to_the_box() -> None:
    assert drag_sustain(spec(), BOX, y_of(0.4, BOX)).sustain \
        == pytest.approx(0.4)
    assert drag_sustain(spec(), BOX, BOX.y - 50.0).sustain == 1.0
    assert drag_sustain(spec(), BOX, BOX.y + BOX.h + 50.0).sustain == 0.0


def test_sustain_leaves_the_swell_level_alone() -> None:
    """The hump has its own height, so it can sit above the hold or dip
    below it."""
    shape = spec(swell_on=True, swell_level=0.3)
    moved = drag_sustain(shape, BOX, y_of(0.9, BOX))
    assert (moved.sustain, moved.swell_level) == (pytest.approx(0.9),
                                                  pytest.approx(0.3))


def test_the_swell_point_moves_both_ways() -> None:
    shape = spec(swell_on=True)
    moved = drag_swell(shape, BOX, x_of(0.6, BOX), y_of(0.7, BOX))
    assert moved.swell_pos == pytest.approx(0.6)
    assert moved.swell_level == pytest.approx(0.7)


def test_the_swell_point_stays_inside_the_hold() -> None:
    shape = spec(attack=0.10, release=0.20, swell_on=True)
    early = drag_swell(shape, BOX, x_of(0.0, BOX), y_of(1.0, BOX))
    late = drag_swell(shape, BOX, x_of(1.0, BOX), y_of(1.0, BOX))
    assert early.swell_pos == pytest.approx(0.10 + MIN_GAP)
    assert late.swell_pos == pytest.approx(0.80 - MIN_GAP)


def test_dragging_a_swell_that_is_off_changes_nothing() -> None:
    shape = spec(swell_on=False)
    assert drag_swell(shape, BOX, x_of(0.6, BOX), y_of(0.2, BOX)) == shape


# -- the property that has to hold ------------------------------------------

def _plays(shape: EnvelopeSpec) -> None:
    """It builds an Envelope, and the light is out at both ends."""
    env = spec_envelope(shape, 1.0, 1.0)
    assert env.value_at(-0.001) == 0.0
    assert env.value_at(1.0) == 0.0


@pytest.mark.parametrize("start", [
    dict(),
    dict(attack=0.0, sustain=1.0, release=1.0),          # the old pop
    dict(attack=0.0, sustain=0.0, swell_on=True, release=0.0),   # old swell
    dict(attack=0.45, release=0.45, swell_on=True, swell_pos=0.5),
    dict(attack=0.0, release=0.0, swell_on=True),
])
def test_no_drag_anywhere_can_make_an_envelope_that_raises(start) -> None:
    """The canvas is 230 px wide; the fuzz reaches well past both edges,
    because a mouse does."""
    shape = spec(**start)
    for handle, move in ((Handle.ATTACK, drag_attack),
                         (Handle.RELEASE, drag_release)):
        for step in range(-20, 41):
            _plays(move(shape, BOX, BOX.x + step * 10.0))
    for step in range(-20, 41):
        _plays(drag_sustain(shape, BOX, BOX.y + step * 5.0))
        for across in range(-20, 41):
            _plays(drag_swell(shape, BOX, BOX.x + across * 10.0,
                              BOX.y + step * 5.0))
