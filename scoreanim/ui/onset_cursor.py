"""The on-page onset cursor (2026-08-08, re-timing's second half).

A vertical line in the selected element's system marks where it fires
right now; grab it and drag, and it snaps to the onset stops — the
SAME list the panel's Earlier/Later walk (core/animation/onset_stops),
which is why the stops carry x. Release commits ONE SetTriggerBeat
(rule 8). An off-stop automatic time draws between its neighbouring
stops (x_at's straight-line rule) and snaps onto the grid on the
first drag.

The gesture is view-level through the DragRouter — probe, start, move,
finish, the nudge's shape — so the item handles no mouse events, and a
bare click on the line changes nothing (a claimed press never turns
into a selection click; stage_view returns early on release). The
window calls sync_from_document AFTER its reschedule pass, the stepper
widget's staleness rule.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject

from scoreanim.core.animation import (TriggerSchedule, is_retimeable,
                                      nearest_stop_to_x, quantize_beats,
                                      stops_for_system, x_at)
from scoreanim.core.project import ProjectDoc, SetTriggerBeat
from scoreanim.render.onset_cursor import OnsetCursorItem
from scoreanim.ui.app_state import AppState


class OnsetCursorController(QObject):
    def __init__(self, app_state: AppState,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = app_state
        self._scenes = None
        self._layout = None
        self._bands: dict = {}
        self._schedule: Callable[[], TriggerSchedule | None] = lambda: None
        self._by_id: dict = {}
        self._item: OnsetCursorItem | None = None
        self._page: int | None = None
        self._origin_x: float | None = None
        self._drag_stop = None
        app_state.selection_changed.connect(self.sync)

    def bind(self, scenes, layout, band_by_system,
             schedule: Callable[[], TriggerSchedule | None]) -> None:
        """Per load. The scenes are fresh, so the old item died with
        them — forget it rather than removing it."""
        self._item = None
        self._page = None
        self._scenes = scenes
        self._layout = layout
        self._bands = dict(band_by_system)
        self._schedule = schedule
        self._by_id = {} if layout is None else {
            el.identity.element_id: el for el in layout.elements}
        self.sync()

    def sync_from_document(self, doc: ProjectDoc | None = None) -> None:
        """Window-called after its reschedule pass, so the line reads
        the rebuilt schedule (execute, undo and redo all land here)."""
        self.sync()

    # -- state -------------------------------------------------------------

    def _context(self):
        """(element, effective beat) for a re-timeable selection — the
        stepper widget's gate, for the same reasons."""
        selection = self._state.selection
        schedule = self._schedule()
        if selection is None or schedule is None:
            return None
        if not is_retimeable(selection.obj):
            return None
        el = self._by_id.get(selection.element_id)
        if el is None or el.system is None:
            return None
        beat = schedule.beats_by_element.get(selection.element_id)
        if beat is None:
            return None
        return el, beat

    def sync(self) -> None:
        ctx = self._context()
        band = None if ctx is None else self._bands.get(ctx[0].system)
        if ctx is None or band is None or self._scenes is None:
            self._hide()
            return
        el, beat = ctx
        x = x_at(stops_for_system(self._layout, el.system), beat)
        if x is None:
            self._hide()
            return
        self._show(band.page, x, band.rect)

    def _show(self, page: int, x: float, rect) -> None:
        if self._item is None or self._page != page:
            self._hide()
            item = OnsetCursorItem()
            self._scenes.scene_for_page(page).addItem(item)
            self._item, self._page = item, page
        self._item.set_span(x, rect.y, rect.y + rect.h)

    def _hide(self) -> None:
        if self._item is not None and self._item.scene() is not None:
            self._item.scene().removeItem(self._item)
        self._item = None
        self._page = None

    # -- the drag (DragRouter handler surface) -----------------------------

    def probe(self, scene_pos, scene=None) -> bool:
        return (self._item is not None
                and (scene is None or scene is self._item.scene())
                and self._item.grabs(scene_pos))

    def start(self, scene_pos, scene=None) -> None:
        self._origin_x = scene_pos.x()
        self._drag_stop = None

    def move(self, delta) -> None:
        ctx = self._context()
        if ctx is None or self._item is None or self._origin_x is None:
            return
        el, _ = ctx
        stops = stops_for_system(self._layout, el.system)
        stop = nearest_stop_to_x(stops, self._origin_x + delta.x())
        if stop is not None:
            # live snap: the line jumps stop to stop under the hand
            self._drag_stop = stop
            line = self._item.line()
            self._item.set_span(stop.x, line.y1(), line.y2())

    def finish(self, delta) -> None:
        self.move(delta)
        stop, self._drag_stop = self._drag_stop, None
        self._origin_x = None
        ctx = self._context()
        if ctx is None or stop is None:
            self.sync()
            return
        el, beat = ctx
        if quantize_beats(stop.beats) != quantize_beats(beat):
            # one gesture, one command, one undo entry (rule 8); the
            # document pass re-syncs the line onto the rebuilt schedule
            self._state.execute(
                SetTriggerBeat(el.identity.element_id, stop.beats))
        else:
            self.sync()          # released where it was: snap back
