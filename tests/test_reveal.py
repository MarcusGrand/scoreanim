"""Phase 5 re-plan (rulings A/B, 2026-07-12): per-(system, part) reveal
tracks anchored on the trigger schedule's tie-gated beats.

Synthetic geometry (page units arbitrary): staff scaffolds span
x 50..500. TempoMap at 60 bpm makes seconds == beats, so time
expectations read directly.
"""
from __future__ import annotations

import pytest

from scoreanim.core.animation import build_trigger_schedule
from scoreanim.core.animation.reveal import (RevealMode, SystemRevealTrack,
                                             build_reveal_tracks, reveal_x)
from scoreanim.core.engraving.types import (Layout, PageGeometry, Point,
                                            Rect, RenderedElement,
                                            RenderPrimitive)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)
from scoreanim.core.score.model import ScoreNote
from scoreanim.core.timing.swing import SwingRegion
from scoreanim.core.timing.tempo_map import TempoEvent, TempoMap

BPM60 = TempoMap([TempoEvent(0.0, 60.0)])


def _el(eid: str, kind: ElementKind, onset: float | None, system: int,
        x: float, w: float, part: str = "P1",
        extent: tuple[float, float] | None = None) -> RenderedElement:
    ident = ElementIdentity(ElementId(eid), kind, PartId(part), part,
                            1, 1, onset, extent)
    bbox = Rect(x, 0.0, w, 10.0)
    return RenderedElement(ident, 1, x, 0.0, bbox, Point(x, 0.0),
                           RenderPrimitive(paths=()), system=system)


def _note(part: str, onset: float, step: str, order: int,
          tie: str | None) -> ScoreNote:
    return ScoreNote(part=PartId(part), measure=1, staff=1,
                     voice_label="1", onset=onset, grace=False,
                     pitch_step=step, pitch_alter=0.0, octave=4,
                     staff_loc=None, order=order, tie=tie)


def _layout(*elements: RenderedElement) -> Layout:
    return Layout(pages=(PageGeometry(1, 600.0, 600.0),), elements=elements)


@pytest.fixture()
def tied_setup():
    """One system, two parts. P1 has a tied pair (beats 2→3, same
    pitch); P2 walks quarters straight through. A tie curve sits
    between P1's tied heads."""
    layout = _layout(
        _el("scaffold", ElementKind.STAFF_LINES, None, 1, 50, 450),
        # P1: note, note, tied pair (start@2, stop@3), note
        _el("p1n0", ElementKind.NOTEHEAD, 0.0, 1, 100, 10),
        _el("p1n1", ElementKind.NOTEHEAD, 1.0, 1, 200, 10),
        _el("p1t0", ElementKind.NOTEHEAD, 2.0, 1, 300, 10),
        _el("p1t1", ElementKind.NOTEHEAD, 3.0, 1, 400, 10),
        _el("p1tie", ElementKind.TIE, 2.0, 1, 315, 80, extent=(2.0, 3.0)),
        _el("p1n4", ElementKind.NOTEHEAD, 4.0, 1, 450, 10),
        # P2: straight quarters, offset x slightly left
        _el("p2n0", ElementKind.NOTEHEAD, 0.0, 1, 95, 10, part="P2"),
        _el("p2n1", ElementKind.NOTEHEAD, 1.0, 1, 195, 10, part="P2"),
        _el("p2n2", ElementKind.NOTEHEAD, 2.0, 1, 295, 10, part="P2"),
        _el("p2n3", ElementKind.NOTEHEAD, 3.0, 1, 395, 10, part="P2"),
        _el("p2n4", ElementKind.NOTEHEAD, 4.0, 1, 445, 10, part="P2"),
    )
    mapping = {
        ElementId("p1n0"): _note("P1", 0.0, "D", 0, None),
        ElementId("p1n1"): _note("P1", 1.0, "E", 1, None),
        ElementId("p1t0"): _note("P1", 2.0, "C", 2, "start"),
        ElementId("p1t1"): _note("P1", 3.0, "C", 3, "stop"),
        ElementId("p1n4"): _note("P1", 4.0, "F", 4, None),
        ElementId("p2n0"): _note("P2", 0.0, "G", 0, None),
        ElementId("p2n1"): _note("P2", 1.0, "A", 1, None),
        ElementId("p2n2"): _note("P2", 2.0, "B", 2, None),
        ElementId("p2n3"): _note("P2", 3.0, "C", 3, None),
        ElementId("p2n4"): _note("P2", 4.0, "D", 4, None),
    }
    schedule = build_trigger_schedule(layout, mapping)
    tracks = build_reveal_tracks(layout, schedule, score_end=6.0)
    return {t.part: t for t in tracks}


def test_tied_group_is_one_anchor(tied_setup) -> None:
    """Ruling A: the tied pair collapses to a single anchor at the
    chain start whose x covers the whole group (stop head + tie curve);
    there is NO anchor at the tie-stop's notated onset."""
    p1 = tied_setup[PartId("P1")]
    assert p1.beats == (-1.0, 0.0, 1.0, 2.0, 4.0, 6.0)
    assert 3.0 not in p1.beats                     # no stop-onset anchor
    assert p1.xs == (50.0, 110.0, 210.0, 410.0, 460.0, 500.0)
    # the chain-start anchor covers the stop head (410 > tie fold 395)


def test_stepped_holds_through_the_tie(tied_setup) -> None:
    p1 = tied_setup[PartId("P1")].resolve(BPM60)
    S = RevealMode.STEPPED
    assert reveal_x(p1, 1.99, S) == 210.0          # before the group
    assert reveal_x(p1, 2.0, S) == 410.0           # whole group at once
    assert reveal_x(p1, 2.99, S) == 410.0
    assert reveal_x(p1, 3.0, S) == 410.0           # NOTHING at stop onset
    assert reveal_x(p1, 3.99, S) == 410.0          # holds to chain end
    assert reveal_x(p1, 4.0, S) == 460.0           # next event advances


def test_other_part_keeps_stepping_during_the_tie(tied_setup) -> None:
    """Per-part edges (your ruling): P2's track is untouched by P1's
    tie — it still steps at beat 3."""
    p2 = tied_setup[PartId("P2")]
    assert p2.beats == (-1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 6.0)
    c2 = p2.resolve(BPM60)
    assert reveal_x(c2, 3.0, RevealMode.STEPPED) == 405.0
    c1 = tied_setup[PartId("P1")].resolve(BPM60)
    assert reveal_x(c1, 3.0, RevealMode.STEPPED) == 410.0  # P1 holding


def test_continuous_reads_the_same_anchors(tied_setup) -> None:
    """CONTINUOUS (pending its wavefront redesign) lerps over the same
    tie-gated anchors: it arrives at the group's end at chain start and
    is never mid-group during the tie."""
    c1 = tied_setup[PartId("P1")].resolve(BPM60)
    C = RevealMode.CONTINUOUS
    assert reveal_x(c1, 2.0, C) == 410.0
    for t in (2.2, 2.5, 3.0, 3.5, 3.99):
        assert 410.0 <= reveal_x(c1, t, C) <= 460.0


def test_rests_are_anchors() -> None:
    """Ruling B: a rest is an event — the edge advances at it, so a
    spanner over a rest bar advances."""
    layout = _layout(
        _el("s", ElementKind.STAFF_LINES, None, 1, 50, 450),
        _el("n0", ElementKind.NOTEHEAD, 0.0, 1, 100, 10),
        _el("r1", ElementKind.REST, 1.0, 1, 200, 10),
        _el("m2", ElementKind.MREST, 2.0, 1, 300, 40),
        _el("n3", ElementKind.NOTEHEAD, 4.0, 1, 450, 10),
    )
    mapping = {ElementId("n0"): _note("P1", 0.0, "C", 0, None),
               ElementId("n3"): _note("P1", 4.0, "D", 1, None)}
    schedule = build_trigger_schedule(layout, mapping)
    (track,) = build_reveal_tracks(layout, schedule, score_end=6.0)
    assert track.beats == (-1.0, 0.0, 1.0, 2.0, 4.0, 6.0)
    assert track.xs == (50.0, 110.0, 210.0, 340.0, 460.0, 500.0)
    c = track.resolve(BPM60)
    assert reveal_x(c, 1.0, RevealMode.STEPPED) == 210.0   # rest advances
    assert reveal_x(c, 2.0, RevealMode.STEPPED) == 340.0   # mRest advances


def test_grace_anchor_and_cummax() -> None:
    """A grace at a fractional trigger is an anchor; an engraving-x
    accident is clamped monotone, never a backward step."""
    layout = _layout(
        _el("s1", ElementKind.STAFF_LINES, None, 1, 50, 450),
        _el("n0", ElementKind.NOTEHEAD, 0.0, 1, 100, 10),
        _el("n1", ElementKind.NOTEHEAD, 1.0, 1, 220, 10),
        _el("g", ElementKind.NOTEHEAD, 1.875, 1, 205, 10),   # grace, x left
        _el("n2", ElementKind.NOTEHEAD, 2.0, 1, 300, 10),
    )
    grace = _note("P1", 2.0, "E", 2, None)
    grace = type(grace)(**{**grace.__dict__, "grace": True})
    mapping = {ElementId("n0"): _note("P1", 0.0, "C", 0, None),
               ElementId("n1"): _note("P1", 1.0, "D", 1, None),
               ElementId("g"): grace,
               ElementId("n2"): _note("P1", 2.0, "F", 3, None)}
    schedule = build_trigger_schedule(layout, mapping)
    (track,) = build_reveal_tracks(layout, schedule, score_end=4.0)
    assert 1.875 in track.beats
    assert track.xs == (50.0, 110.0, 230.0, 230.0, 310.0, 500.0)


def test_swing_delays_the_offbeat_anchor() -> None:
    layout = _layout(
        _el("s1", ElementKind.STAFF_LINES, None, 1, 50, 450),
        _el("n0", ElementKind.NOTEHEAD, 0.0, 1, 100, 10),
        _el("n1", ElementKind.NOTEHEAD, 0.5, 1, 200, 10),
        _el("n2", ElementKind.NOTEHEAD, 1.0, 1, 300, 10),
    )
    mapping = {ElementId("n0"): _note("P1", 0.0, "C", 0, None),
               ElementId("n1"): _note("P1", 0.5, "D", 1, None),
               ElementId("n2"): _note("P1", 1.0, "E", 2, None)}
    schedule = build_trigger_schedule(layout, mapping)
    (track,) = build_reveal_tracks(layout, schedule, score_end=2.0)
    straight = track.resolve(BPM60)
    swung = track.resolve(BPM60, (SwingRegion((0.0, 2.0), 0.6),))
    i = track.beats.index(0.5)
    assert straight.times[i] == pytest.approx(0.5)
    assert swung.times[i] == pytest.approx(0.6)
    assert reveal_x(swung, 0.55, RevealMode.STEPPED) == 110.0
    assert reveal_x(swung, 0.6, RevealMode.STEPPED) == 210.0


def test_track_validation() -> None:
    p = PartId("P1")
    with pytest.raises(ValueError):
        SystemRevealTrack(1, p, (0.0, 0.0), (0.0, 1.0), 0.0)
    with pytest.raises(ValueError):
        SystemRevealTrack(1, p, (0.0, 1.0), (1.0, 0.0), 0.0)
    with pytest.raises(ValueError):
        SystemRevealTrack(1, p, (0.0,), (1.0,), 0.0)


@pytest.fixture(scope="module")
def fixture_tracks(engraved, join_mapping, score_model):
    schedule = build_trigger_schedule(engraved.layout, join_mapping)
    score_end = max(m.start + m.quarter_length for m in score_model.measures)
    return build_reveal_tracks(engraved.layout, schedule, score_end)


def test_real_fixture_tracks(fixture_tracks) -> None:
    """Per-(system, part) tracks on the real score: every part tracks
    every system (rests/mRests guarantee anchors); properties hold; a
    part's consecutive systems interlock."""
    systems = sorted({t.system for t in fixture_tracks})
    parts = sorted({str(t.part) for t in fixture_tracks})
    assert systems == [1, 2, 3, 4, 5]
    assert len(parts) == 7
    assert len(fixture_tracks) == 35
    for t in fixture_tracks:
        assert all(b1 > b0 for b0, b1 in zip(t.beats, t.beats[1:]))
        assert all(x1 >= x0 for x0, x1 in zip(t.xs, t.xs[1:]))
        assert t.xs[0] == t.x_left
    for part in parts:
        own = [t for t in fixture_tracks if str(t.part) == part]
        own.sort(key=lambda t: t.system)
        for a, b in zip(own, own[1:]):
            # lead = prev system's last event — unless a broken chain's
            # start anchor lands first in the next system (then the
            # guard backs the lead off one beat)
            assert (b.beats[0] == a.beats[-2]
                    or b.beats[0] == b.beats[1] - 1.0)
            # end sentinel = next system's first event — unless it
            # coincides with the last anchor (guard pushes it one beat)
            assert (a.beats[-1] == b.beats[1]
                    or a.beats[-1] == a.beats[-2] + 1.0)


def test_broken_chain_reveals_both_sides_at_chain_start(
        engraved, join_mapping, score_model) -> None:
    """The m8→m9 broken ties (chain start in system 2): system 2's
    track covers the tie's segment-1 ink out to the margin at chain
    start, and system 3's track has a chain-start anchor covering the
    stop head — both sides stand revealed from chain start."""
    schedule = build_trigger_schedule(engraved.layout, join_mapping)
    score_end = max(m.start + m.quarter_length for m in score_model.measures)
    tracks = {(t.system, str(t.part)): t
              for t in build_reveal_tracks(engraved.layout, schedule,
                                           score_end)}
    els = {str(e.identity.element_id): e for e in engraved.layout.elements}
    seg = els["P3:m8:s1:v1:tie:0:seg1"]            # continuation, system 3
    source = els["P3:m8:s1:v1:tie:0"]              # source, system 2
    # P3 has TWO broken chains (fixture fact); the earliest chain start
    # is when the stop-side region first reveals
    chain_starts = sorted(
        schedule.beats_by_element[eid] for eid, n in join_mapping.items()
        if n.part == "P3" and n.tie == "stop" and n.onset >= 28.0
        and els[str(eid)].system == 3)
    assert all(cs < 32.0 for cs in chain_starts)   # gated before m9

    S = RevealMode.STEPPED
    c2 = tracks[(2, "P3")].resolve(BPM60)
    c3 = tracks[(3, "P3")].resolve(BPM60)
    latest = BPM60.seconds_at(chain_starts[-1])
    assert reveal_x(c2, latest, S) >= source.bbox.x2   # segment 1 covered
    assert reveal_x(c3, latest, S) >= seg.bbox.x2      # stop side covered
    # and just before the EARLIEST chain, the stop side is NOT revealed
    earliest = BPM60.seconds_at(chain_starts[0])
    assert reveal_x(c3, earliest - 0.01, S) < seg.bbox.x
