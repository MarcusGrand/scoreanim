"""WallClock (FIX 2): no-audio playback clock — a pure function of a
wall source since the last anchor, never t += dt (rule 2)."""

from scoreanim.ui.wall_clock import WallClock


class _FakeWall:
    """Deterministic, manually-advanced wall source."""
    def __init__(self) -> None:
        self.t = 100.0            # arbitrary non-zero epoch

    def __call__(self) -> float:
        return self.t


def test_paused_clock_is_frozen_at_zero():
    w = WallClock(now=_FakeWall())
    assert not w.is_playing
    assert w.now_seconds() == 0.0


def test_play_extrapolates_from_wall_source():
    wall = _FakeWall()
    w = WallClock(now=wall)
    w.play()
    assert w.now_seconds() == 0.0
    wall.t += 2.5
    assert w.now_seconds() == 2.5
    wall.t += 1.0
    assert w.now_seconds() == 3.5


def test_pause_freezes_and_resume_does_not_count_paused_time():
    wall = _FakeWall()
    w = WallClock(now=wall)
    w.play()
    wall.t += 2.0
    w.pause()
    assert w.now_seconds() == 2.0
    wall.t += 10.0                # time passes while paused
    assert w.now_seconds() == 2.0
    w.play()                      # resume: paused gap is not counted
    assert w.now_seconds() == 2.0
    wall.t += 0.5
    assert w.now_seconds() == 2.5


def test_seek_reanchors_while_playing_and_paused():
    wall = _FakeWall()
    w = WallClock(now=wall)
    w.play()
    wall.t += 5.0
    w.seek(1.0)
    assert w.now_seconds() == 1.0     # jumps immediately, still playing
    wall.t += 2.0
    assert w.now_seconds() == 3.0
    w.pause()
    w.seek(0.0)
    assert w.now_seconds() == 0.0
    wall.t += 3.0
    assert w.now_seconds() == 0.0     # paused seek stays put


def test_seek_clamps_negative_to_zero():
    w = WallClock(now=_FakeWall())
    w.seek(-5.0)
    assert w.now_seconds() == 0.0


def test_is_a_pure_function_no_accumulation():
    # querying many times between anchors must never drift the value
    wall = _FakeWall()
    w = WallClock(now=wall)
    w.play()
    wall.t += 1.0
    for _ in range(1000):
        assert w.now_seconds() == 1.0
