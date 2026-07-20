"""No-audio playback (FIX 2): the PlaybackController drives the WallClock
and the score-derived timeline when no recording is loaded, and the
AudioClock stays master once audio is present."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing import TempoMap
from scoreanim.core.timing.tempo_map import TempoEvent
from scoreanim.ui.playback import PlaybackController
from scoreanim.ui.wall_clock import WallClock


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeApplier:
    """Records the times it is driven with; current page/system fixed."""
    def __init__(self):
        self.applied = []
        self.refreshed = []
    def set_timing(self, tempo_map, swing):
        pass
    def set_style(self, style):
        pass
    def refresh(self, t):
        self.refreshed.append(t)
    def apply_at(self, t):
        self.applied.append(t)
        return 0
    def current_page(self):
        return 1
    def current_system(self):
        return 1


def _measures(n=4, ql=4.0):
    # n bars of ql quarters each, starting at 0
    return tuple(MeasureInfo(number=i + 1, start=i * ql, quarter_length=ql)
                 for i in range(n))


def _controller(qapp):
    c = PlaybackController()
    c.set_animation(_FakeApplier(), _measures())
    # 120 bpm => 0.5 s/quarter; 16 quarters => 8.0 s
    c.set_timing_config(0.0, TempoMap([TempoEvent(0.0, 120.0)]))
    return c


def test_no_media_uses_the_wall_clock(qapp):
    c = _controller(qapp)
    assert not c.transport.has_media()
    assert isinstance(c._clock, WallClock)


def test_score_duration_from_tempo_map_and_measures(qapp):
    c = _controller(qapp)
    assert c._duration() == pytest.approx(8.0)          # 16 quarters @120bpm


def test_toggle_play_starts_and_stops_no_audio_playback(qapp):
    c = _controller(qapp)
    states = []
    c.playing_changed.connect(states.append)
    c.toggle_play()
    assert c._wall.is_playing
    assert states == [True]
    c.toggle_play()
    assert not c._wall.is_playing
    assert states == [True, False]


def test_toggle_play_noops_without_a_score(qapp):
    c = PlaybackController()          # no applier, no timing
    c.toggle_play()
    assert not c._wall.is_playing


def test_seek_moves_the_wall_clock_and_refreshes(qapp):
    c = _controller(qapp)
    applier = c._applier
    before = len(applier.refreshed)
    c.seek(2.0)
    assert c._wall.now_seconds() == 2.0
    # refresh drove the applier at score time = audio time - offset(0)
    assert applier.refreshed[-1] == pytest.approx(2.0)
    assert len(applier.refreshed) > before


def test_tick_drives_the_applier_off_the_wall_clock(qapp):
    c = _controller(qapp)
    applier = c._applier
    c.toggle_play()                  # anchors the wall clock at ~now
    times = []
    c.time_changed.connect(lambda t, d: times.append((t, d)))
    c._tick()                        # simulate one timer fire
    assert applier.applied           # apply_at was called
    assert applier.applied[-1] >= 0.0
    assert times and times[-1][1] == pytest.approx(8.0)   # duration reported
    c.toggle_play()                  # stop


def test_duration_changed_emitted_for_the_no_audio_timeline(qapp):
    c = PlaybackController()
    seen = []
    c.duration_changed.connect(seen.append)
    c.set_animation(_FakeApplier(), _measures())
    c.set_timing_config(0.0, TempoMap([TempoEvent(0.0, 120.0)]))
    assert seen and seen[-1] == pytest.approx(8.0)
