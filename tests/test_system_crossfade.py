"""The crossfade over a system switch, offscreen (2026-08-30,
docs/SYSTEMS_MODE_REWORK.md stage 5).

The dissolve is one frozen picture painted over the live view, so what
these pin is the picture: mid-fade the viewport is the blend of the two
systems, at the end it is the new system to the pixel, and with the
toggle off it is the hard cut it has always been. Plus the two rules
that keep it honest — the camera never moves under a fade, and anything
that moves the camera drops the snapshot rather than smearing it.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.engraving.systems import (  # noqa: E402
    neighbour_bounds, system_bands, systems_frame)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.render.scene import ScoreScenes  # noqa: E402
from scoreanim.ui.stage_frame import frame_offset  # noqa: E402
from scoreanim.ui.stage_transition import CROSSFADE_MS  # noqa: E402
from scoreanim.ui.stage_view import StageView  # noqa: E402
from scoreanim.ui.window_state import FADE_SYSTEM_SWITCHES  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def scenes(qapp, engraved) -> ScoreScenes:
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    return ScoreScenes(engraved.layout, stage)


@pytest.fixture(scope="module")
def bands(engraved) -> dict:
    return {b.system: b for b in system_bands(engraved.layout)}


@pytest.fixture(scope="module")
def frame(bands):
    return systems_frame(tuple(bands.values()))


@pytest.fixture(scope="module")
def bounds(bands):
    return neighbour_bounds(tuple(bands.values()))


def _qrect(rect) -> QRectF:
    return QRectF(rect.x, rect.y, rect.w, rect.h)


def _view(frame, fade: bool = True, size=(600, 850)) -> StageView:
    view = StageView()
    view.resize(*size)
    view.viewport().grab()               # force offscreen layout/resize
    view.set_systems_frame(frame)        # what ViewRouter.bind does
    view.crossfade.set_enabled(fade)     # what the View menu's toggle does
    return view


def _switch(view, scenes, bands, bounds, system, smooth=False) -> None:
    """One system switch the way ViewRouter.show_system runs it — the
    capture FIRST, then the item filter, then the swap."""
    band = bands[system]
    if smooth:
        view.crossfade.capture()
    scenes.set_visible_system(system)
    view.show_system_band(scenes.scene_for_page(band.page),
                          _qrect(band.rect),
                          bounds.get(system, (None, None)), smooth=smooth)


def _image(view):
    return view.viewport().grab().toImage()


def _hold(view, ms: float):
    """The fade stopped dead at `ms`, so a grab reads one exact moment
    of it (nothing sleeps, and nothing depends on how fast the machine
    is)."""
    view.crossfade.animation.pause()
    view.crossfade.animation.setCurrentTime(int(ms))
    return _image(view)


def _differing(old, new) -> list[tuple[int, int]]:
    """Viewport pixels the two systems do not agree on — where a
    dissolve is visible at all. Sampled on a coarse grid; the music
    covers plenty of it."""
    return [(x, y)
            for y in range(0, old.height(), 7)
            for x in range(0, old.width(), 7)
            if old.pixelColor(x, y) != new.pixelColor(x, y)]


# -- the dissolve ---------------------------------------------------------

def test_mid_fade_the_viewport_is_the_two_systems_blended(
        qapp, scenes, bands, frame, bounds) -> None:
    """Half way through, every pixel is half the outgoing system and
    half the incoming one. That is the whole feature: the old picture
    is glued to the screen and thinned out over the live view."""
    view = _view(frame)
    _switch(view, scenes, bands, bounds, 1)
    old = _image(view)
    _switch(view, scenes, bands, bounds, 2)          # hard cut, for the
    new = _image(view)                               # picture it lands on
    _switch(view, scenes, bands, bounds, 1)
    _switch(view, scenes, bands, bounds, 2, smooth=True)
    mid = _hold(view, CROSSFADE_MS / 2)

    points = _differing(old, new)
    assert len(points) > 100, "the two systems look too alike to test"
    for x, y in points:
        a, b, m = (old.pixelColor(x, y), new.pixelColor(x, y),
                   mid.pixelColor(x, y))
        for got, want in ((m.red(), (a.red() + b.red()) / 2),
                          (m.green(), (a.green() + b.green()) / 2),
                          (m.blue(), (a.blue() + b.blue()) / 2)):
            assert got == pytest.approx(want, abs=3), (x, y)


def test_the_fade_ends_on_the_new_system_exactly(
        qapp, scenes, bands, frame, bounds) -> None:
    """When it is over it is over: the snapshot is gone and the viewport
    is the same picture a hard cut would have left."""
    view = _view(frame)
    _switch(view, scenes, bands, bounds, 1)
    _switch(view, scenes, bands, bounds, 2)
    cut = _image(view)
    _switch(view, scenes, bands, bounds, 1)
    _switch(view, scenes, bands, bounds, 2, smooth=True)
    assert view.crossfade.is_running()
    _hold(view, CROSSFADE_MS)
    view.crossfade.animation.stop()       # what the finished signal does
    assert not view.crossfade.is_running()
    assert _image(view) == cut


def test_the_toggle_off_is_the_hard_cut_it_always_was(
        qapp, scenes, bands, frame, bounds) -> None:
    """With the fade off nothing is captured and nothing is painted, so
    a followed switch is bit-for-bit the switch of stages 1-4."""
    view = _view(frame, fade=False)
    _switch(view, scenes, bands, bounds, 1)
    _switch(view, scenes, bands, bounds, 2)
    cut = _image(view)
    _switch(view, scenes, bands, bounds, 1)
    _switch(view, scenes, bands, bounds, 2, smooth=True)
    assert not view.crossfade.is_running()
    assert _image(view) == cut


def test_turning_it_off_mid_fade_ends_the_fade(
        qapp, scenes, bands, frame, bounds) -> None:
    view = _view(frame)
    _switch(view, scenes, bands, bounds, 1)
    _switch(view, scenes, bands, bounds, 2, smooth=True)
    _hold(view, CROSSFADE_MS / 2)
    view.crossfade.set_enabled(False)
    assert not view.crossfade.is_running()


def test_a_switch_mid_fade_freezes_what_is_on_screen(
        qapp, scenes, bands, frame, bounds) -> None:
    """Systems can pass faster than 150 ms. A second switch takes its
    own snapshot — of the half-faded view, which is what the user is
    actually looking at — and starts again from full."""
    view = _view(frame)
    _switch(view, scenes, bands, bounds, 1)
    _switch(view, scenes, bands, bounds, 2, smooth=True)
    _hold(view, CROSSFADE_MS / 2)
    view.crossfade.animation.resume()
    _switch(view, scenes, bands, bounds, 3, smooth=True)
    assert view.crossfade.is_running()
    assert view.crossfade.opacity == pytest.approx(1.0)


# -- the camera is not part of it -----------------------------------------

def test_the_camera_does_not_move_under_a_fade(
        qapp, scenes, bands, frame, bounds) -> None:
    """Stage 2's promise, with the polish on: a smooth switch is the
    same camera move as a hard one, to the bit. The fade is paint and
    nothing else."""
    def camera(smooth):
        view = _view(frame, fade=smooth)
        _switch(view, scenes, bands, bounds, 1)
        view.zoom_by(2.0)
        view.scroll_by(300.0, 0.0)
        _switch(view, scenes, bands, bounds, 2, smooth=smooth)
        return view.transform().m11(), view.mapToScene(0, 0).toTuple()

    assert camera(True) == camera(False)


def test_the_glass_stays_where_it_was_through_a_fade(
        qapp, scenes, bands, frame, bounds) -> None:
    """Why the snapshot lines up at all: the frame is in the same place
    on screen before and after the switch, so the frozen picture sits
    exactly over the live one. (One device pixel of tolerance, the
    quarter-pixel snap, as in test_stage_system_mode.)"""
    view = _view(frame)
    _switch(view, scenes, bands, bounds, 1)
    view.zoom_by(2.0)
    view.scroll_by(300.0, 0.0)

    def glass(system):
        placed = frame.rect_for(bands[system].rect)
        return frame_offset(_qrect(placed), view.mapToScene(0, 0),
                            view.transform().m11()).toTuple()

    was = glass(1)
    _switch(view, scenes, bands, bounds, 2, smooth=True)
    at = glass(2)
    assert at[0] == pytest.approx(was[0], abs=1.0)
    assert at[1] == pytest.approx(was[1], abs=1.0)


@pytest.mark.parametrize("move", [
    lambda view: view.zoom_by(1.5),
    lambda view: view.scroll_by(40.0, 0.0),
    lambda view: view.fit(),
    lambda view: view.resize(500, 700),
])
def test_moving_the_camera_drops_the_snapshot(
        qapp, scenes, bands, frame, bounds, move) -> None:
    """The snapshot is glued to the screen, so it is only true while the
    view holds still. Anything that moves the camera ends the fade at
    the next paint instead of smearing a stale picture across it."""
    view = _view(frame)
    _switch(view, scenes, bands, bounds, 1)
    view.zoom_by(2.0)                     # leave fit mode, so fit() moves
    _switch(view, scenes, bands, bounds, 2, smooth=True)
    assert view.crossfade.is_running()
    move(view)
    _image(view)                          # the paint that notices
    assert not view.crossfade.is_running()


def test_a_page_flip_drops_the_snapshot(qapp, scenes, bands, frame,
                                        bounds) -> None:
    """Leaving system mode altogether is the same story."""
    view = _view(frame)
    _switch(view, scenes, bands, bounds, 1)
    _switch(view, scenes, bands, bounds, 2, smooth=True)
    scenes.set_visible_system(None)
    view.show_scene(scenes.scene_for_page(1))
    _image(view)
    assert not view.crossfade.is_running()


def test_the_switch_itself_does_not_cancel_the_fade(
        qapp, scenes, bands, frame, bounds) -> None:
    """The trap behind that rule: a switch MOVES the camera — it refits
    or translates to put the new band in the frame. So the camera the
    snapshot is judged against is the one the switch finished on, not
    the one it started from, or a fitted switch (the common case) would
    kill its own fade."""
    view = _view(frame)
    _switch(view, scenes, bands, bounds, 1)
    _switch(view, scenes, bands, bounds, 2, smooth=True)
    assert view.crossfade.is_running()


# -- the View menu's toggle -----------------------------------------------

def _window(qapp, tmp_path):
    from scoreanim.ui.main_window import MainWindow
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    return MainWindow(settings=settings), settings


def test_the_toggle_drives_the_stage_and_is_remembered(qapp,
                                                       tmp_path) -> None:
    """View state, like the overlay preview: QSettings, never the
    document, so it cannot reach a project file or an exported frame."""
    window, settings = _window(qapp, tmp_path)
    action = window.menus.fade_systems_action
    assert action.isCheckable() and not action.isChecked()
    assert not window.view.crossfade.enabled       # hard cuts by default

    action.setChecked(True)
    assert window.view.crossfade.enabled
    assert settings.value(FADE_SYSTEM_SWITCHES, type=bool) is True

    action.setChecked(False)
    assert not window.view.crossfade.enabled
    assert settings.value(FADE_SYSTEM_SWITCHES, type=bool) is False


def test_a_fresh_window_opens_the_way_it_was_left(qapp, tmp_path) -> None:
    first, settings = _window(qapp, tmp_path)
    first.menus.fade_systems_action.setChecked(True)
    from scoreanim.ui.main_window import MainWindow
    second = MainWindow(settings=settings)
    assert second.menus.fade_systems_action.isChecked()
    assert second.view.crossfade.enabled
