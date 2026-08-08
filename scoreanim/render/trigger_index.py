"""The schedule's rows, materialized against a scene.

Split out of `render/animate.py` on 2026-08-06, when that module reached
the size ceiling. Pure move, no behaviour change.

A `TriggerSchedule` is a list of beats, each naming element ids. The
applier needs those rows four ways at once, and works them out once:

- `items` — the scene item per id, in the schedule's own
  [trigger][item] shape. An id with no item on this page set drops out,
  so the rows are never ragged against the scene.
- `ids` — the SAME rows as ids, for the pure timing arithmetic in core
  (`core/animation/windows.py`), which must never see a Qt item. An
  item with no identity contributes None, which every duration lookup
  reads as "no engraved duration".
- `page_at` / `system_at` — which page and system the view follows once
  the cursor has crossed that many triggers.

The GainIndex precedent (`render/gain_index.py`): the applier holds the
object, not four parallel tuples.
"""
from __future__ import annotations

from itertools import accumulate
from typing import Mapping

from scoreanim.core.animation import TriggerSchedule
from scoreanim.core.score.identity import ElementId
from scoreanim.render.items import ElementItem


class TriggerIndex:
    """One row per trigger: its items, its ids, and the page and system
    the view follows there."""

    def __init__(self, items: Mapping[ElementId, ElementItem],
                 schedule: TriggerSchedule) -> None:
        self.items: tuple[tuple[ElementItem, ...], ...] = tuple(
            tuple(items[eid] for eid in trig.element_ids if eid in items)
            for trig in schedule.triggers)
        self.ids: tuple[tuple[ElementId | None, ...], ...] = tuple(
            tuple(None if item.identity is None else item.identity.element_id
                  for item in row)
            for row in self.items)
        # Followed page/system is monotonic non-decreasing over the
        # time-ordered triggers (prefix-max): the view must never turn
        # backward while the clock advances. A per-trigger page/system is
        # only a hint — schedule.py aggregates each beat bucket with min(),
        # and tie/rest/group retiming plus sub-beat bucket-merging across a
        # system break can make a single trigger's value dip N, N-1, N.
        # bisect_right(trigger_seconds, t) is monotone in t, so forward play
        # only grows the cursor → the followed unit only advances; a genuine
        # backward seek moves the cursor earlier and returns the prefix-max
        # up to that time (exactly what a forward playthrough showed there).
        # v1 playback is a linear sweep of a through-composed timeline, so a
        # legitimate backward turn (repeats/D.S.) does not arise.
        self._pages = tuple(accumulate(
            (trig.page for trig in schedule.triggers), max))
        self._systems = tuple(accumulate(
            (trig.system for trig in schedule.triggers), max))

    def __len__(self) -> int:
        return len(self.items)

    def page_at(self, cursor: int) -> int:
        """Page of the last crossed trigger (1 before anything fires)."""
        return self._pages[cursor - 1] if cursor else 1

    def system_at(self, cursor: int) -> int:
        """System of the last crossed trigger (1 before anything fires)
        — the page_at idiom on the same cursor, consumed identically by
        live follow and export (Phase 7)."""
        return self._systems[cursor - 1] if cursor else 1
