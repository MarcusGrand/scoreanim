"""Retiming a span: the target is hit, the anchors do not move, and
nothing outside the span changes."""
from __future__ import annotations

import math
import random

import pytest

from scoreanim.core.timing.retime import (BPM_MAX, BPM_MIN, bpm_at,
                                          flatten_span, lock_anchors,
                                          scale_span, span_bounds)
from scoreanim.core.timing.tempo_map import TempoEvent, TempoMap

STEADY = (TempoEvent(0.0, 120.0),)
CURVE = (TempoEvent(0.0, 120.0), TempoEvent(4.0, 90.0),
         TempoEvent(8.0, 144.0), TempoEvent(16.0, 100.0))


def probes(*extra: float) -> tuple[float, ...]:
    return (-4.0, 0.0, 1.5, 4.0, 8.0, 12.0, 16.0, 24.0) + extra


def seconds(events, at):
    m = TempoMap(list(events))
    return [m.seconds_at(b) for b in at]


def test_target_is_hit_exactly() -> None:
    events = scale_span(CURVE, beat=8.0, seconds=4.5, left=4.0, right=12.0)
    assert TempoMap(list(events)).seconds_at(8.0) == pytest.approx(4.5,
                                                                  abs=1e-12)


def test_anchors_and_everything_outside_hold_still() -> None:
    before = seconds(CURVE, probes())
    events = scale_span(CURVE, beat=8.0, seconds=4.5, left=4.0, right=12.0)
    after = seconds(events, probes())
    for beat, was, now in zip(probes(), before, after):
        if beat <= 4.0 or beat >= 12.0:
            assert now == pytest.approx(was, abs=1e-12), f"beat {beat} moved"
    assert after != before                       # non-vacuity


def test_events_outside_the_span_are_untouched() -> None:
    events = scale_span(CURVE, beat=8.0, seconds=4.5, left=4.0, right=12.0)
    assert [e for e in events
            if e.position < 4.0 or e.position > 12.0] == [CURVE[0], CURVE[3]]
    # the anchor gets a neutral boundary event, carrying the bpm that was
    # already in force there — that is what stops the scaling bleeding past
    boundary = next(e for e in events if e.position == 12.0)
    assert boundary.bpm == bpm_at(CURVE, 12.0) == 144.0


def test_tempo_shape_inside_a_span_is_preserved() -> None:
    events = (TempoEvent(0.0, 120.0), TempoEvent(1.0, 60.0),
              TempoEvent(2.0, 90.0), TempoEvent(4.0, 120.0))
    out = scale_span(events, beat=4.0, seconds=3.0, left=0.0, right=None)
    bpms = {e.position: e.bpm for e in out}
    assert bpms[1.0] / bpms[2.0] == pytest.approx(60.0 / 90.0)
    assert bpms[0.0] / bpms[1.0] == pytest.approx(120.0 / 60.0)


def test_ripple_shifts_the_tail_by_one_constant() -> None:
    before = seconds(CURVE, probes(32.0, 40.0))
    events = scale_span(CURVE, beat=8.0, seconds=4.5, left=4.0, right=None)
    after = seconds(events, probes(32.0, 40.0))
    deltas = {round(now - was, 9)
              for beat, was, now in zip(probes(32.0, 40.0), before, after)
              if beat >= 8.0}
    assert len(deltas) == 1 and deltas != {0.0}
    for beat, was, now in zip(probes(32.0, 40.0), before, after):
        if beat <= 4.0:
            assert now == pytest.approx(was, abs=1e-12)


def test_last_line_ripples_by_definition() -> None:
    """right=None is both the ripple rule and the last tick's only
    option, so they are the same code path."""
    a = scale_span(CURVE, beat=16.0, seconds=9.0, left=8.0, right=None)
    assert TempoMap(list(a)).seconds_at(16.0) == pytest.approx(9.0)


def test_a_first_event_after_beat_zero_still_pins_its_anchor() -> None:
    """TempoMap extends the first event's bpm BACK to beat 0, so scaling
    it would move seconds before the anchor. The beat-0 normalization is
    what stops that."""
    events = (TempoEvent(4.0, 120.0), TempoEvent(8.0, 90.0))
    before = seconds(events, (0.0, 1.0, 2.0, 4.0, 12.0))
    out = scale_span(events, beat=8.0, seconds=3.5, left=4.0, right=12.0)
    after = seconds(out, (0.0, 1.0, 2.0, 4.0, 12.0))
    assert after == pytest.approx(before, abs=1e-12)
    assert TempoMap(list(out)).seconds_at(8.0) == pytest.approx(3.5)


@pytest.mark.parametrize("beat,left,right", [
    (4.0, 0.0, 8.0),             # beat is an existing event
    (6.0, 4.0, 8.0),             # left is an existing event
    (8.0, 4.0, 16.0),            # both anchors are existing events
    (10.0, 8.0, None),           # ripple from an existing event
])
def test_anchors_coinciding_with_events(beat, left, right) -> None:
    m = TempoMap(list(CURVE))
    target = m.seconds_at(beat) + 0.2
    out = scale_span(CURVE, beat=beat, seconds=target, left=left, right=right)
    assert TempoMap(list(out)).seconds_at(beat) == pytest.approx(target)
    assert TempoMap(list(out)).seconds_at(left) == pytest.approx(
        m.seconds_at(left), abs=1e-12)


def test_a_boundary_a_hair_from_an_event_is_not_duplicated() -> None:
    out = scale_span(CURVE, beat=8.0 + 1e-12, seconds=4.5, left=4.0, right=12.0)
    positions = [e.position for e in out]
    assert len(positions) == len(set(positions))
    for a, b in zip(positions, positions[1:]):
        assert b - a > 1e-6


def test_a_no_op_retime_leaves_the_map_alone_and_keeps_user_events() -> None:
    """The inserted boundary says nothing and goes; the user's equal-bpm
    event at beat 4 is an anchor of theirs and stays."""
    events = (TempoEvent(0.0, 120.0), TempoEvent(4.0, 120.0))
    m = TempoMap(list(events))
    out = scale_span(events, beat=2.0, seconds=m.seconds_at(2.0), left=0.0,
                 right=4.0)
    assert out == events
    assert seconds(out, probes()) == pytest.approx(seconds(events, probes()))


@pytest.mark.parametrize("kwargs", [
    dict(beat=8.0, seconds=4.5, left=8.0, right=12.0),      # beat == left
    dict(beat=8.0, seconds=4.5, left=9.0, right=12.0),      # beat < left
    dict(beat=8.0, seconds=4.5, left=4.0, right=8.0),       # beat == right
    dict(beat=8.0, seconds=float("nan"), left=4.0, right=12.0),
    dict(beat=8.0, seconds=1.0, left=4.0, right=12.0),      # under the floor
    dict(beat=8.0, seconds=1e6, left=4.0, right=12.0),      # over the ceiling
])
def test_bad_input_raises(kwargs) -> None:
    with pytest.raises(ValueError):
        scale_span(CURVE, **kwargs)


def test_no_events_raises() -> None:
    with pytest.raises(ValueError):
        scale_span((), beat=1.0, seconds=1.0, left=0.0, right=2.0)


@pytest.mark.parametrize("right", [12.0, None])
def test_bounds_endpoints_are_reachable_and_saturate_the_bpm_range(right
                                                                  ) -> None:
    lo, hi = span_bounds(CURVE, beat=8.0, left=4.0, right=right, flatten=False)
    assert lo < hi
    for target in (lo, hi):
        out = scale_span(CURVE, beat=8.0, seconds=target, left=4.0, right=right)
        assert TempoMap(list(out)).seconds_at(8.0) == pytest.approx(target)
        extreme = min(min(e.bpm for e in out) / BPM_MIN,
                      BPM_MAX / max(e.bpm for e in out))
        assert extreme == pytest.approx(1.0, rel=1e-6)


def test_bounds_bracket_the_current_position() -> None:
    m = TempoMap(list(CURVE))
    lo, hi = span_bounds(CURVE, beat=8.0, left=4.0, right=12.0, flatten=False)
    assert lo < m.seconds_at(8.0) < hi


def test_beyond_the_bounds_raises() -> None:
    lo, hi = span_bounds(CURVE, beat=8.0, left=4.0, right=12.0, flatten=False)
    for target in (lo - 0.01, hi + 0.01):
        with pytest.raises(ValueError):
            scale_span(CURVE, beat=8.0, seconds=target, left=4.0, right=12.0)


def test_bpm_at_extends_the_first_event_backwards() -> None:
    assert bpm_at(CURVE, -2.0) == 120.0
    assert bpm_at(CURVE, 4.0) == 90.0
    assert bpm_at(CURVE, 7.9) == 90.0
    assert bpm_at(CURVE, 1000.0) == 100.0


def _random_events(rng: random.Random) -> tuple[TempoEvent, ...]:
    beats = sorted(rng.sample(range(1, 40), rng.randint(0, 4)))
    return (TempoEvent(0.0, rng.uniform(60.0, 180.0)),) + tuple(
        TempoEvent(float(b), rng.uniform(60.0, 180.0)) for b in beats)


@pytest.mark.parametrize("seed", range(25))
def test_property_pins_hold_and_target_is_hit(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(20):
        events = _random_events(rng)
        left = float(rng.randint(0, 30))
        beat = left + rng.choice((0.25, 1.0 / 3.0, 0.5, 1.0, 4.0))
        right = beat + rng.choice((0.5, 1.0, 4.0)) if rng.random() < 0.7 \
            else None
        lo, hi = span_bounds(events, beat=beat, left=left, right=right, flatten=False)
        if hi - lo < 2e-3:
            continue
        target = rng.uniform(lo + 1e-4, hi - 1e-4)
        out = scale_span(events, beat=beat, seconds=target, left=left, right=right)
        m_before, m_after = TempoMap(list(events)), TempoMap(list(out))
        assert m_after.seconds_at(beat) == pytest.approx(target, abs=1e-9)
        assert m_after.seconds_at(left) == pytest.approx(
            m_before.seconds_at(left), abs=1e-9)
        if right is not None:
            for probe in (right, right + 7.5):
                assert m_after.seconds_at(probe) == pytest.approx(
                    m_before.seconds_at(probe), abs=1e-9)
        positions = [e.position for e in out]
        assert positions == sorted(positions)
        assert all(BPM_MIN - 1e-9 <= e.bpm <= BPM_MAX + 1e-9 for e in out)
        assert all(math.isfinite(e.bpm) for e in out)
        assert len(out) <= len(events) + 4      # zero event + 3 boundaries


# -- even spacing (the default drag rule) ------------------------------------

def test_flatten_spaces_every_beat_of_the_span_equally() -> None:
    out = flatten_span(CURVE, beat=8.0, seconds=4.5, left=0.0, right=None)
    m = TempoMap(list(out))
    steps = [round(m.seconds_at(b + 1.0) - m.seconds_at(b), 9)
             for b in range(8)]
    assert len(set(steps)) == 1                  # one constant tempo
    assert m.seconds_at(8.0) == pytest.approx(4.5, abs=1e-12)
    assert m.seconds_at(0.0) == 0.0


def test_flatten_drops_the_tempo_detail_inside_the_span() -> None:
    """Dropping what was inside IS the rule, not a side effect."""
    out = flatten_span(CURVE, beat=16.0, seconds=9.0, left=0.0, right=None)
    assert [e.position for e in out if e.position < 16.0] == [0.0]


def test_flatten_holds_both_anchors_and_the_tail() -> None:
    before = seconds(CURVE, probes(32.0))
    out = flatten_span(CURVE, beat=8.0, seconds=4.5, left=4.0, right=16.0)
    after = seconds(out, probes(32.0))
    for beat, was, now in zip(probes(32.0), before, after):
        if beat <= 4.0 or beat >= 16.0:
            assert now == pytest.approx(was, abs=1e-12), f"beat {beat} moved"
    assert TempoMap(list(out)).seconds_at(8.0) == pytest.approx(4.5)
    assert after != before                       # non-vacuity


def test_flatten_with_no_anchor_after_slides_the_tail_intact() -> None:
    before = seconds(CURVE, probes(32.0))
    out = flatten_span(CURVE, beat=8.0, seconds=4.5, left=4.0, right=None)
    after = seconds(out, probes(32.0))
    deltas = {round(now - was, 9)
              for beat, was, now in zip(probes(32.0), before, after)
              if beat >= 8.0}
    assert len(deltas) == 1 and deltas != {0.0}


def test_flatten_bounds_depend_only_on_the_span_length() -> None:
    """One bpm replaces the lot, so what is inside cannot restrict it."""
    lo, hi = span_bounds(CURVE, beat=8.0, left=4.0, right=None, flatten=True)
    m = TempoMap(list(CURVE))
    assert hi - m.seconds_at(4.0) == pytest.approx(60.0 * 4.0 / BPM_MIN)
    assert lo - m.seconds_at(4.0) == pytest.approx(60.0 * 4.0 / BPM_MAX)
    for target in (lo, hi):
        out = flatten_span(CURVE, beat=8.0, seconds=target, left=4.0,
                           right=None)
        assert TempoMap(list(out)).seconds_at(8.0) == pytest.approx(target)


def test_flatten_beyond_its_bounds_raises() -> None:
    lo, hi = span_bounds(CURVE, beat=8.0, left=4.0, right=12.0, flatten=True)
    for target in (lo - 0.01, hi + 0.01):
        with pytest.raises(ValueError):
            flatten_span(CURVE, beat=8.0, seconds=target, left=4.0, right=12.0)


# -- anchors come from the locks ---------------------------------------------

def test_lock_anchors_falls_back_to_the_score_start() -> None:
    assert lock_anchors((), 8.0) == (0.0, None)
    assert lock_anchors((16.0,), 8.0) == (0.0, 16.0)


def test_lock_anchors_takes_the_nearest_lock_either_side() -> None:
    locks = (0.0, 4.0, 12.0, 40.0)
    assert lock_anchors(locks, 8.0) == (4.0, 12.0)
    assert lock_anchors(locks, 50.0) == (40.0, None)


def test_a_lock_on_the_dragged_beat_is_not_its_own_anchor() -> None:
    assert lock_anchors((4.0, 8.0, 12.0), 8.0) == (4.0, 12.0)
