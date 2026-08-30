"""Page/system presentation routing (M3.0, BACKLOG 9b): which unit of
the score the stage is showing, and how prev/next/follow move it.

Lifted verbatim out of the window, which had carried both the routing
state (`page`, `system`, the band table, the applied presentation mode)
and the six methods that read it. The window is a composition root; this
is a component with one job, bound per load the way `DocumentSync` and
`SelectionController` are (`bind()` from `MainWindow._install`).

Two collaborators, both narrow: the `StageView` it drives
(`show_scene` / `show_system_band` / `clear_band`) and the chrome's
`set_position`, since the readout widgets belong to `MainMenus`. The
router never reaches for a widget it does not own.

Paged is the default mode; system mode (Phase 7.4) frames one system's
band, and the page flip is implied by the band's page.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF

from scoreanim.core.engraving.systems import (SystemsFrame,
                                              neighbour_bounds)
from scoreanim.core.project import PresentationMode, VideoCanvas

if TYPE_CHECKING:
    from scoreanim.render.animate import AnimationApplier
    from scoreanim.render.scene import ScoreScenes
    from scoreanim.ui.menus import MainMenus
    from scoreanim.ui.stage_view import StageView


class ViewRouter:
    """Presentation-unit state + routing for the stage.

    Owns no document state: the presentation MODE is document intent,
    diffed onto the view by `sync_presentation_mode` on every document
    change (the `_applied_*` idiom), and page/system position is
    transient view state that never reaches the document (rule 5).
    """

    def __init__(self, view: StageView, menus: MainMenus) -> None:
        self._view = view
        self._menus = menus
        self._scenes: ScoreScenes | None = None
        self._band_by_system: dict = {}          # derived, never saved
        self._bounds_by_system: dict = {}        # ditto — how far each
                                                 # system may show
        self._system_of_measure: dict = {}       # ditto (M5.5, D8)
        self._applier: AnimationApplier | None = None
        self._page = 1
        self._system = 1
        self._applied_mode = PresentationMode.PAGED   # what the view shows
        self._applied_canvas: VideoCanvas | None = None

    # -- per-load binding ------------------------------------------------------

    def bind(self, scenes: ScoreScenes, band_by_system: dict,
             applier: AnimationApplier,
             system_of_measure: dict | None = None,
             systems_frame: SystemsFrame | None = None) -> None:
        """Adopt one load's derived world (`MainWindow._install`).

        The systems frame goes to the view once, here, because it is the
        same frame for every system in this load (2026-08-30) — a switch
        only moves the band inside it."""
        self._scenes = scenes
        self._band_by_system = band_by_system
        self._bounds_by_system = neighbour_bounds(
            tuple(band_by_system.values()))
        self._applier = applier
        self._system_of_measure = dict(system_of_measure or {})
        self._view.set_systems_frame(systems_frame)

    def reset(self) -> None:
        """Back to the first unit — a FRESH load only; a re-engrave
        preserves the position (no view.fit, no position reset)."""
        self._page = 1
        self._system = 1

    @property
    def page(self) -> int:
        return self._page

    @property
    def system(self) -> int:
        return self._system

    # -- routing ---------------------------------------------------------------

    def show_page(self, page: int) -> None:
        if self._scenes is None:
            return
        self._page = max(1, min(page, self._scenes.page_count))
        # paged shows the whole paper again
        self._scenes.set_visible_system(None)
        self._view.show_scene(self._scenes.scene_for_page(self._page))
        self._menus.set_position(
            f" {self._page}/{self._scenes.page_count} ",
            self._page > 1,
            self._page < self._scenes.page_count)

    def show_system(self, system: int, smooth: bool = False) -> None:
        """Place one system in the constant frame (Phase 7.4, reworked
        2026-08-30): the band's page scene, the band centred in the
        load's frame, every other system's ink hidden — the page flip
        is implied by the band's page.

        `smooth` dissolves out of the outgoing system instead of cutting
        (stage 5). Only the playback tick's own crossing sets it: the
        default here is what keeps prev/next, a seek, a scrub, the mode
        toggle, a re-engrave and a load hard cuts."""
        if self._scenes is None or not self._band_by_system:
            return
        self._system = max(1, min(system, len(self._band_by_system)))
        band = self._band_by_system[self._system]
        self._page = band.page                   # keep page state coherent
        rect = band.rect
        # Freeze the outgoing frame FIRST — before the filter below
        # takes the departing system's ink off the page, which is the
        # picture the dissolve is made of. No-op unless the user has
        # the fade on and this switch asked for one.
        if smooth:
            self._view.crossfade.capture()
        # Only this system's ink is on show. Set BEFORE the swap, so the
        # first paint after a switch is already filtered, and set here
        # because show_system and show_page are the only two routes into
        # the stage — a fresh load, a re-engrave, the mode toggle,
        # prev/next and follow all come through one of them.
        self._scenes.set_visible_system(self._system)
        self._view.show_system_band(
            self._scenes.scene_for_page(band.page),
            QRectF(rect.x, rect.y, rect.w, rect.h),
            self._bounds_by_system.get(self._system, (None, None)),
            smooth=smooth)
        self._menus.set_position(
            f" sys {self._system}/{len(self._band_by_system)} ",
            self._system > 1,
            self._system < len(self._band_by_system))

    def step(self, delta: int) -> None:
        """Prev/next in the current presentation unit."""
        if self._applied_mode is PresentationMode.SYSTEM:
            self.show_system(self._system + delta)
        else:
            self.show_page(self._page + delta)

    def show_current(self) -> None:
        """(Re-)show the current position in the current mode — the
        mode-aware version of the old show_page(1) after a load."""
        if self._applied_mode is PresentationMode.SYSTEM:
            self.show_system(self._system)
        else:
            self.show_page(self._page)

    def show_measure(self, ordinal: int) -> None:
        """Re-anchor to the unit HOLDING a measure (M5.5, D8).

        `show_current` re-shows the same page/system INDEX, which both
        accessors clamp — so nothing goes out of range after a break
        edit, but the same index is different music: forcing a break
        takes testscore from 5 systems to 6 and suppressing one takes it
        to 4. In system mode the stage would jump away from the edit.
        Anchoring by measure is what every notation editor does, and it
        reads off the same measure→system map the toggle policy needs.

        Falls back to `show_current` for a measure the fresh layout does
        not have — a shortened score, or an unbound router.
        """
        system = self._system_of_measure.get(ordinal)
        if system is None:
            self.show_current()
            return
        if self._applied_mode is PresentationMode.SYSTEM:
            self.show_system(system)
            return
        band = self._band_by_system.get(system)
        self.show_page(band.page if band is not None else self._page)

    # -- follow ----------------------------------------------------------------

    def on_page_followed(self, page: int) -> None:
        if self._applied_mode is PresentationMode.PAGED:
            self.show_page(page)

    def on_system_followed(self, system: int,
                           smooth: bool = False) -> None:
        """`smooth` is the controller saying this crossing came from the
        tick loop rather than a seek (ui/playback.py) — the one case
        stage 5's dissolve runs on."""
        if self._applied_mode is PresentationMode.SYSTEM:
            self.show_system(system, smooth=smooth)

    # -- document intent -------------------------------------------------------

    def sync_canvas(self, canvas: VideoCanvas | None) -> None:
        """Diff the document's video canvas onto the view (called on
        every document change, beside sync_presentation_mode)."""
        if canvas == self._applied_canvas:
            return
        self._applied_canvas = canvas
        self._view.set_canvas(canvas)

    def sync_presentation_mode(self, mode: PresentationMode) -> None:
        """Diff the document's mode onto the view (called on every
        document change — commands, undo, project load)."""
        if mode is self._applied_mode:
            return
        self._applied_mode = mode
        if self._scenes is None:
            return
        if mode is PresentationMode.SYSTEM:
            self.show_system(self._applier.current_system()
                             if self._applier is not None else 1)
        else:
            self._view.clear_band()
            self.show_page(self._applier.current_page()
                           if self._applier is not None else self._page)
