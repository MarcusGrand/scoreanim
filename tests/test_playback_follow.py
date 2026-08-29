"""Following the playhead is not an option (ruling 2026-08-29): playing
music always shows the music.

The controller reports position off the applier's cursor with no flag to
consult, and pressing play snaps the stage back to that cursor — paging
around while paused is browsing, and play ends it. Headless: a fake
applier stands in for the render side, and the assertions are on the two
signals the window routes.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                            # noqa: E402
from PySide6.QtWidgets import QApplication               # noqa: E402

from scoreanim.core.score.model import MeasureInfo       # noqa: E402
from scoreanim.core.timing import TempoMap               # noqa: E402
from scoreanim.core.timing.tempo_map import TempoEvent   # noqa: E402
from scoreanim.ui.playback import PlaybackController     # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeApplier:
    """A cursor the test moves by hand."""
    def __init__(self):
        self.page = 1
        self.system = 1

    def set_timing(self, tempo_map, swing):
        pass

    def set_audio(self, peaks, offset_seconds):
        pass

    def set_style(self, style):
        pass

    def refresh(self, t):
        pass

    def apply_at(self, t):
        return 0

    def current_page(self):
        return self.page

    def current_system(self):
        return self.system


@pytest.fixture
def controller(qapp):
    c = PlaybackController()
    applier = _FakeApplier()
    measures = tuple(MeasureInfo(number=i + 1, start=i * 4.0,
                                 quarter_length=4.0) for i in range(4))
    c.set_animation(applier, measures)
    c.set_timing_config(0.0, TempoMap([TempoEvent(0.0, 120.0)]))
    pages, systems = [], []
    c.page_changed.connect(pages.append)
    c.system_changed.connect(systems.append)
    return c, applier, pages, systems


def test_there_is_no_follow_switch(controller) -> None:
    c, _, _, _ = controller
    assert not hasattr(c, "set_follow")


def test_a_moved_cursor_is_always_reported(controller) -> None:
    c, applier, pages, systems = controller
    applier.page, applier.system = 2, 3
    c._refresh()                                  # a seek does this
    assert pages == [2] and systems == [3]


def test_the_same_position_is_not_re_reported(controller) -> None:
    """Only a cursor that LEFT its unit says anything — the guard is
    about noise, never about whether following is wanted."""
    c, _, pages, systems = controller
    c._refresh()
    c._refresh()
    assert pages == [] and systems == []


def test_play_snaps_the_stage_back_to_the_music(controller) -> None:
    """The user paged away while paused: the cursor never moved, so
    nothing was emitted — and play has to put the stage back."""
    c, applier, pages, systems = controller
    applier.page, applier.system = 1, 1           # cursor still at the top
    c.toggle_play()
    try:
        assert pages == [1] and systems == [1]
    finally:
        c.toggle_play()                           # stop the tick timer
