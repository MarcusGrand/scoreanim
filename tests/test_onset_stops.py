"""Onset stops: the places a re-timed element may be moved to
(core/animation/onset_stops.py)."""
from __future__ import annotations

from scoreanim.core.animation import (OnsetStop, quantize_beats, step_from,
                                      stops_for_system)
from scoreanim.core.engraving.types import (Layout, PageGeometry, Point, Rect,
                                            RenderedElement, RenderPrimitive)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)


def _el(eid: str, kind: ElementKind, onset: float | None, system: int,
        x: float, part: str = "P1") -> RenderedElement:
    ident = ElementIdentity(ElementId(eid), kind, PartId(part), part,
                            1, 1, onset)
    return RenderedElement(ident, 1, x, 0.0, Rect(x, 0.0, 10.0, 10.0),
                           Point(x, 0.0), RenderPrimitive(paths=()),
                           system=system)


def _layout(*elements: RenderedElement) -> Layout:
    return Layout(pages=(PageGeometry(1, 600.0, 600.0),), elements=elements)


def test_stops_of_every_real_system_are_sorted_distinct_x_monotone(
        engraved) -> None:
    """The real fixture: every system's stops are sorted by beat,
    distinct at quantized resolution, and x never decreases."""
    systems = sorted({el.system for el in engraved.layout.elements
                      if el.system is not None})
    assert systems, "fixture has no systems"
    checked = 0
    for system in systems:
        stops = stops_for_system(engraved.layout, system)
        assert stops, f"system {system} has no stops"
        beats = [quantize_beats(s.beats) for s in stops]
        assert beats == sorted(beats), f"system {system} not sorted"
        assert len(beats) == len(set(beats)), f"system {system} not distinct"
        xs = [s.x for s in stops]
        assert xs == sorted(xs), f"system {system} x not monotone"
        checked += 1
    assert checked == len(systems)


def test_stop_keeps_the_leftmost_ink_across_parts() -> None:
    """Two parts share beat 1; the stop takes the leftmost ink. A rest
    keys by its NOTATED onset (its place on the page), a dynamic and
    another system's note contribute nothing."""
    layout = _layout(
        _el("n0", ElementKind.NOTEHEAD, 0.0, 1, 100.0),
        _el("n1", ElementKind.NOTEHEAD, 1.0, 1, 200.0),
        _el("r1", ElementKind.REST, 1.0, 1, 195.0, part="P2"),
        _el("d0", ElementKind.DYNAMIC, 0.5, 1, 150.0),
        _el("other", ElementKind.NOTEHEAD, 2.0, 2, 40.0),
    )
    assert stops_for_system(layout, 1) == (OnsetStop(0.0, 100.0),
                                           OnsetStop(1.0, 195.0))


def test_step_from_walks_the_neighbours() -> None:
    stops = (OnsetStop(0.0, 10.0), OnsetStop(1.0, 20.0), OnsetStop(4.0, 30.0))
    assert step_from(stops, 1.0, -1) == 0.0
    assert step_from(stops, 1.0, +1) == 4.0
    # off-stop: the first press goes to the nearest stop in the pressed
    # direction
    assert step_from(stops, 2.5, -1) == 1.0
    assert step_from(stops, 2.5, +1) == 4.0
    # past either end: nothing
    assert step_from(stops, 0.0, -1) is None
    assert step_from(stops, 4.0, +1) is None
    assert step_from((), 1.0, -1) is None
    assert step_from((), 1.0, +1) is None
