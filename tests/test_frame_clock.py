"""FrameClock: t = n / fps, a pure function of the absolute frame index
(rule 2 — no accumulation, so out-of-order frame walks yield identical
times to in-order ones)."""

import pytest

from scoreanim.core.timing import Clock, FrameClock


def test_is_a_clock() -> None:
    assert isinstance(FrameClock(60), Clock)


@pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
def test_frame_times(fps: int) -> None:
    clock = FrameClock(fps)
    assert clock.now_seconds() == 0.0
    for n in (0, 1, fps, fps * 60, 12345):
        clock.set_frame(n)
        assert clock.now_seconds() == n / fps


def test_out_of_order_walk_matches_in_order() -> None:
    """No hidden state: the time at frame n never depends on the frames
    visited before it."""
    fps = 60
    frames = [0, 5, 3, 2074, 1, 2073, 7]
    walked = []
    clock = FrameClock(fps)
    for n in frames:
        clock.set_frame(n)
        walked.append(clock.now_seconds())
    assert walked == [n / fps for n in frames]


def test_no_drift_at_the_end_of_a_long_piece() -> None:
    """After an hour of frames at 60 fps the time is exact — the
    accumulated-dt failure mode this class exists to preclude."""
    clock = FrameClock(60)
    clock.set_frame(60 * 3600)
    assert clock.now_seconds() == 3600.0


def test_validation() -> None:
    with pytest.raises(ValueError):
        FrameClock(0)
    with pytest.raises(ValueError):
        FrameClock(-30)
    clock = FrameClock(30)
    with pytest.raises(ValueError):
        clock.set_frame(-1)


def test_properties() -> None:
    clock = FrameClock(24)
    assert clock.fps == 24.0
    clock.set_frame(48)
    assert clock.frame == 48
