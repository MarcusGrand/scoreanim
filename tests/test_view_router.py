"""Presentation routing (M3.0, BACKLOG 9b), on stubs.

The router was lifted out of `MainWindow` verbatim, and its behaviour
was only ever covered incidentally — through the window, by tests about
selection. It has two collaborators and both are narrow (a view it
drives, a chrome readout it calls), so the routing decisions pin
headlessly on stubs: clamping, mode dispatch, follow gating, and the
page/system coherence rule. No QApplication, no window.
"""
from __future__ import annotations

from dataclasses import dataclass

from scoreanim.core.project import PresentationMode
from scoreanim.ui.view_router import ViewRouter


@dataclass(frozen=True)
class _Rect:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class _Band:
    page: int
    rect: _Rect


class _Scenes:
    def __init__(self, page_count: int) -> None:
        self.page_count = page_count

    def scene_for_page(self, page: int) -> str:
        return f"scene{page}"


class _View:
    def __init__(self) -> None:
        self.calls: list = []

    def show_scene(self, scene) -> None:
        self.calls.append(("scene", scene))

    def show_system_band(self, scene, band) -> None:
        self.calls.append(("band", scene, round(band.y())))

    def clear_band(self) -> None:
        self.calls.append(("clear",))


class _Menus:
    def __init__(self) -> None:
        self.position: tuple | None = None

    def set_position(self, text: str, can_prev: bool, can_next: bool) -> None:
        self.position = (text, can_prev, can_next)


class _Applier:
    def __init__(self, page: int = 1, system: int = 1) -> None:
        self._page, self._system = page, system

    def current_page(self) -> int:
        return self._page

    def current_system(self) -> int:
        return self._system


BANDS = {1: _Band(1, _Rect(0.0, 0.0, 100.0, 40.0)),
         2: _Band(1, _Rect(0.0, 50.0, 100.0, 40.0)),
         3: _Band(2, _Rect(0.0, 0.0, 100.0, 40.0))}


def _router(pages: int = 2, applier=None) -> tuple:
    view, menus = _View(), _Menus()
    router = ViewRouter(view, menus)
    router.bind(_Scenes(pages), dict(BANDS), applier or _Applier())
    return router, view, menus


# -- unbound -------------------------------------------------------------

def test_unbound_router_routes_nowhere() -> None:
    """Before the first load there is nothing to show — every entry
    point is a no-op rather than an AttributeError."""
    view, menus = _View(), _Menus()
    router = ViewRouter(view, menus)
    router.show_page(2)
    router.show_system(2)
    router.step(+1)
    router.show_current()
    router.on_page_followed(2)
    assert view.calls == [] and menus.position is None


# -- paged ---------------------------------------------------------------

def test_show_page_clamps_and_reports() -> None:
    router, view, menus = _router(pages=3)
    router.show_page(99)
    assert router.page == 3
    assert view.calls == [("scene", "scene3")]
    assert menus.position == (" 3/3 ", True, False)
    router.show_page(0)
    assert router.page == 1
    assert menus.position == (" 1/3 ", False, True)


def test_step_moves_pages_in_paged_mode() -> None:
    router, _, _ = _router(pages=3)
    router.show_page(1)
    router.step(+1)
    assert router.page == 2
    router.step(-1)
    assert router.page == 1


# -- system mode ---------------------------------------------------------

def test_show_system_frames_the_band_and_keeps_page_coherent() -> None:
    """The page flip is implied by the band's page: framing system 3
    leaves `page` on 2, so a later switch back to paged mode does not
    jump the user somewhere else."""
    router, view, menus = _router()
    router.show_system(3)
    assert router.system == 3 and router.page == 2
    assert view.calls == [("band", "scene2", 0)]
    assert menus.position == (" sys 3/3 ", True, False)


def test_show_system_clamps_to_the_band_table() -> None:
    router, _, menus = _router()
    router.show_system(99)
    assert router.system == 3
    router.show_system(-5)
    assert router.system == 1
    assert menus.position == (" sys 1/3 ", False, True)


def test_step_moves_systems_in_system_mode() -> None:
    router, _, _ = _router()
    router.sync_presentation_mode(PresentationMode.SYSTEM)
    router.step(+1)
    assert router.system == 2
    assert router.page == 1


# -- follow --------------------------------------------------------------

def test_follow_is_gated_by_the_applied_mode() -> None:
    """Playback emits page AND system on every move; the router takes
    exactly the one its mode is showing."""
    router, _, _ = _router()
    router.on_page_followed(2)
    router.on_system_followed(3)
    assert router.page == 2 and router.system == 1   # paged: system ignored

    router.sync_presentation_mode(PresentationMode.SYSTEM)
    router.on_page_followed(1)
    router.on_system_followed(3)
    assert router.system == 3 and router.page == 2   # band 3 lives on page 2


# -- mode diff -----------------------------------------------------------

def test_mode_diff_is_idempotent() -> None:
    router, view, _ = _router()
    router.sync_presentation_mode(PresentationMode.PAGED)   # already applied
    assert view.calls == []


def test_entering_system_mode_frames_the_playhead_system() -> None:
    router, view, _ = _router(applier=_Applier(page=2, system=3))
    router.sync_presentation_mode(PresentationMode.SYSTEM)
    assert router.system == 3
    assert view.calls == [("band", "scene2", 0)]


def test_leaving_system_mode_clears_the_band_before_showing_the_page() -> None:
    """Order matters: the mask must come off before the page is shown,
    or the fresh page is painted under the old band's letterbox."""
    router, view, _ = _router(applier=_Applier(page=2, system=3))
    router.sync_presentation_mode(PresentationMode.SYSTEM)
    view.calls.clear()
    router.sync_presentation_mode(PresentationMode.PAGED)
    assert view.calls == [("clear",), ("scene", "scene2")]


# -- load lifecycle ------------------------------------------------------

def test_reset_returns_to_the_first_unit() -> None:
    """A FRESH load resets; a re-engrave calls show_current() instead
    and must keep the user where they were."""
    router, _, _ = _router()
    router.show_page(2)
    router.show_system(3)
    router.reset()
    assert router.page == 1 and router.system == 1


def test_show_current_repaints_without_moving() -> None:
    router, view, _ = _router()
    router.show_page(2)
    view.calls.clear()
    router.show_current()
    assert router.page == 2
    assert view.calls == [("scene", "scene2")]
