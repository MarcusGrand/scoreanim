"""Phase 5.1b: reveal_x per system — both modes, sentinels, simultaneity.

Synthetic geometry (page units are arbitrary): two systems whose staff
scaffolds span x 50..400, noteheads as marked. TempoMap at 60 bpm makes
seconds == beats, so time expectations read directly.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation.reveal import (RevealMode, SystemRevealTrack,
                                             build_reveal_tracks, reveal_x)
from scoreanim.core.engraving.types import (Layout, PageGeometry, Point,
                                            Rect, RenderedElement,
                                            RenderPrimitive)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)
from scoreanim.core.timing.swing import SwingRegion
from scoreanim.core.timing.tempo_map import TempoEvent, TempoMap

BPM60 = TempoMap([TempoEvent(0.0, 60.0)])


def _el(eid: str, kind: ElementKind, onset: float | None, system: int,
        x: float, w: float, staff: int = 1) -> RenderedElement:
    ident = ElementIdentity(ElementId(eid), kind, PartId("P1"), "Part",
                            staff, 1, onset)
    bbox = Rect(x, 0.0, w, 10.0)
    return RenderedElement(ident, 1, x, 0.0, bbox, Point(x, 0.0),
                           RenderPrimitive(paths=()), system=system)


def _layout(*elements: RenderedElement) -> Layout:
    return Layout(pages=(PageGeometry(1, 500.0, 500.0),), elements=elements)


@pytest.fixture()
def two_systems():
    layout = _layout(
        _el("scaffold1", ElementKind.STAFF_LINES, None, 1, 50, 350),
        # two staves, SAME beat, different engraved x — one anchor
        _el("n0a", ElementKind.NOTEHEAD, 0.0, 1, 100, 10, staff=1),
        _el("n0b", ElementKind.NOTEHEAD, 0.0, 1, 95, 17, staff=2),
        _el("n1", ElementKind.NOTEHEAD, 1.0, 1, 200, 10),
        _el("n2", ElementKind.NOTEHEAD, 2.0, 1, 300, 10),
        _el("scaffold2", ElementKind.STAFF_LINES, None, 2, 50, 350),
        _el("m0", ElementKind.NOTEHEAD, 4.0, 2, 80, 10),
        _el("m1", ElementKind.NOTEHEAD, 6.0, 2, 200, 10),
    )
    return build_reveal_tracks(layout, score_end=8.0)


def test_track_shape_and_simultaneity(two_systems) -> None:
    """Simultaneous onsets across staves collapse to ONE anchor at the
    rightmost ink — the step lands on the musical onset, never on
    per-staff engraving-x differences."""
    t1, t2 = two_systems
    assert t1.system == 1 and t2.system == 2
    assert t1.beats == (-1.0, 0.0, 1.0, 2.0, 4.0)
    assert t1.xs == (50.0, 112.0, 210.0, 310.0, 400.0)
    assert t2.beats == (2.0, 4.0, 6.0, 8.0)
    assert t2.xs == (50.0, 90.0, 210.0, 400.0)


def test_stepped_exact_values(two_systems) -> None:
    c1, c2 = (t.resolve(BPM60) for t in two_systems)
    S = RevealMode.STEPPED
    assert reveal_x(c1, -2.0, S) == 50.0          # before everything
    assert reveal_x(c1, 0.0, S) == 112.0          # at-onset inclusive
    assert reveal_x(c1, 0.99, S) == 112.0         # holds between onsets
    assert reveal_x(c1, 1.0, S) == 210.0
    assert reveal_x(c1, 3.9, S) == 310.0
    assert reveal_x(c1, 4.0, S) == 400.0          # completes at next system
    assert reveal_x(c1, 99.0, S) == 400.0
    assert reveal_x(c2, 3.9, S) == 50.0           # next system still reveal 0
    assert reveal_x(c2, 4.0, S) == 90.0


def test_continuous_exact_values(two_systems) -> None:
    c1, c2 = (t.resolve(BPM60) for t in two_systems)
    C = RevealMode.CONTINUOUS
    assert reveal_x(c1, 0.5, C) == pytest.approx(161.0)   # 112→210 midpoint
    assert reveal_x(c1, 3.0, C) == pytest.approx(355.0)   # 310→400 midpoint
    assert reveal_x(c1, 4.0, C) == 400.0
    # the next system sweeps left-edge → first-note over the same interval
    assert reveal_x(c2, 2.0, C) == 50.0
    assert reveal_x(c2, 3.0, C) == pytest.approx(70.0)    # 50→90 midpoint
    assert reveal_x(c2, 4.0, C) == 90.0


def test_continuous_is_continuous_within_a_system(two_systems) -> None:
    """No jumps: fine sampling changes the edge by a bounded amount."""
    for track in two_systems:
        curve = track.resolve(BPM60)
        ts = [i * 0.001 - 2.0 for i in range(12000)]
        xs = [reveal_x(curve, t, RevealMode.CONTINUOUS) for t in ts]
        max_step = max(abs(b - a) for a, b in zip(xs, xs[1:]))
        assert max_step < 0.5
        assert all(b >= a for a, b in zip(xs, xs[1:]))    # monotone in t


def test_empty_system_still_sweeps() -> None:
    """A system with no onsets (all-rest) keeps its two sentinels so
    spanners crossing it grow: lead = previous system's last onset,
    end = next system's first onset."""
    layout = _layout(
        _el("s1", ElementKind.STAFF_LINES, None, 1, 50, 350),
        _el("n0", ElementKind.NOTEHEAD, 0.0, 1, 100, 10),
        _el("s2", ElementKind.STAFF_LINES, None, 2, 50, 350),
        _el("s3", ElementKind.STAFF_LINES, None, 3, 50, 350),
        _el("k0", ElementKind.NOTEHEAD, 8.0, 3, 100, 10),
    )
    t1, t2, t3 = build_reveal_tracks(layout, score_end=12.0)
    assert t2.beats == (0.0, 8.0)
    assert t2.xs == (50.0, 400.0)
    c2 = t2.resolve(BPM60)
    assert reveal_x(c2, 4.0, RevealMode.CONTINUOUS) == pytest.approx(225.0)
    # system 1's end sentinel skips the empty system to the next onset
    assert t1.beats[-1] == 8.0


def test_grace_anchor_and_cummax() -> None:
    """A grace at a fractional beat is an anchor; an engraving-x accident
    (anchor left of an earlier one) is clamped monotone, never a
    backward step."""
    layout = _layout(
        _el("s1", ElementKind.STAFF_LINES, None, 1, 50, 350),
        _el("n0", ElementKind.NOTEHEAD, 0.0, 1, 100, 10),
        _el("n1", ElementKind.NOTEHEAD, 1.0, 1, 220, 10),
        _el("g", ElementKind.NOTEHEAD, 1.875, 1, 205, 10),   # grace, x left
        _el("n2", ElementKind.NOTEHEAD, 2.0, 1, 300, 10),
    )
    (track,) = build_reveal_tracks(layout, score_end=4.0)
    assert 1.875 in track.beats
    assert track.xs == (50.0, 110.0, 230.0, 230.0, 310.0, 400.0)


def test_swing_delays_the_offbeat_anchor() -> None:
    """Anchors resolve through the same swing-aware seam as triggers."""
    layout = _layout(
        _el("s1", ElementKind.STAFF_LINES, None, 1, 50, 350),
        _el("n0", ElementKind.NOTEHEAD, 0.0, 1, 100, 10),
        _el("n1", ElementKind.NOTEHEAD, 0.5, 1, 200, 10),
        _el("n2", ElementKind.NOTEHEAD, 1.0, 1, 300, 10),
    )
    (track,) = build_reveal_tracks(layout, score_end=2.0)
    straight = track.resolve(BPM60)
    swung = track.resolve(BPM60, (SwingRegion((0.0, 2.0), 0.6),))
    i = track.beats.index(0.5)
    assert straight.times[i] == pytest.approx(0.5)
    assert swung.times[i] == pytest.approx(0.6)
    # STEPPED edge holds pre-swing value just before the delayed onset
    assert reveal_x(swung, 0.55, RevealMode.STEPPED) == 110.0
    assert reveal_x(swung, 0.6, RevealMode.STEPPED) == 210.0


def test_track_validation() -> None:
    with pytest.raises(ValueError):
        SystemRevealTrack(1, (0.0, 0.0), (0.0, 1.0), 0.0)
    with pytest.raises(ValueError):
        SystemRevealTrack(1, (0.0, 1.0), (1.0, 0.0), 0.0)
    with pytest.raises(ValueError):
        SystemRevealTrack(1, (0.0,), (1.0,), 0.0)


def test_real_fixture_tracks(engraved, score_model) -> None:
    score_end = max(m.start + m.quarter_length
                    for m in score_model.measures)
    tracks = build_reveal_tracks(engraved.layout, score_end)
    assert [t.system for t in tracks] == [1, 2, 3, 4, 5]
    for t in tracks:
        assert all(b1 > b0 for b0, b1 in zip(t.beats, t.beats[1:]))
        assert all(x1 >= x0 for x0, x1 in zip(t.xs, t.xs[1:]))
        assert t.xs[0] == t.x_left
    # consecutive systems interlock: lead of k+1 == last onset of k,
    # end sentinel of k == first onset of k+1
    for a, b in zip(tracks, tracks[1:]):
        assert b.beats[0] == a.beats[-2]
        assert a.beats[-1] == b.beats[1]
