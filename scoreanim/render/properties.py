"""Animated property → ElementItem: the one place a property name turns
into a write on a scene item.

A fixed map, one entry per animatable property. The evaluator owns the
VALUE; these functions only put it on the item. A property with no entry
here is skipped by the caller, so a preset from a newer build degrades
instead of crashing.
"""
from __future__ import annotations

from typing import Callable, Mapping

from scoreanim.core.animation import OFFSET_X, OFFSET_Y, OPACITY, SCALE
from scoreanim.render.items import ElementItem


def _apply_opacity(item: ElementItem, value: float) -> None:
    # the item composes this with whatever else is applied to it; the
    # evaluator owns the input, never the painted result
    item.set_animated_opacity(value)


def _apply_scale(item: ElementItem, value: float) -> None:
    # No pivot, no scale. Which ink scales, what it turns around and how
    # far it may grow are all decided once, in core (scale_groups.py and
    # stem_caps.py), and carried on the item by ScoreScenes — the applier
    # only applies. The ceiling is what keeps a swelling stem inside its
    # beam.
    if item.scale_pivot is None:
        return
    if item.scale_cap is not None:
        value = min(value, item.scale_cap)
    item.setScale(value)


def _apply_offset_x(item: ElementItem, value: float) -> None:
    # The item, not setPos: the document's own nudge owns the position
    # too, and the item adds the two. Writing setPos here would move a
    # nudged note back off its nudged place.
    item.set_animated_offset_x(value)


def _apply_offset_y(item: ElementItem, value: float) -> None:
    item.set_animated_offset_y(value)


PROPERTY_APPLIERS: Mapping[str, Callable[[ElementItem, float], None]] = {
    OPACITY: _apply_opacity,
    SCALE: _apply_scale,
    OFFSET_X: _apply_offset_x,
    OFFSET_Y: _apply_offset_y,
}
