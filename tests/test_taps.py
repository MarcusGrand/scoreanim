"""Tap → tempo derivation (PHASES 4.3), headless on synthetic taps.

The two spec cases: noisy steady taps must yield a stable BPM (one
event, no jittery quarter spacing); a rit. must come out as a ramp of
decreasing events. Plus lock-to-taps exactness and the guard rails.
"""
from __future__ import annotations

import random

import pytest

from scoreanim.core.timing import TempoEvent, TempoMap
from scoreanim.core.timing.taps import (Tap, TapSession, derive_tempo_events,
                                        lock_to_taps, start_residual)


def steady_session(seed: int, n: int = 32, bpm: float = 120.0,
                   sigma: float = 0.030, start_beat: float = 0.0,
                   start_time: float = 5.0) -> TapSession:
    """n quarter taps at constant bpm with gaussian jitter (σ = 30 ms —
    the top of the human tap-noise band)."""
    rng = random.Random(seed)
    spb = 60.0 / bpm
    return TapSession(1.0, tuple(
        Tap(start_beat + i, start_time + i * spb + rng.gauss(0, sigma))
        for i in range(n)))


def rit_session(seed: int, b0: float = 120.0, b1: float = 80.0,
                beats: int = 16, sigma: float = 0.020) -> TapSession:
    rng = random.Random(seed)
    taps, t = [], 5.0
    for i in range(beats + 1):
        taps.append(Tap(float(i), t + rng.gauss(0, sigma)))
        t += 60.0 / (b0 + (b1 - b0) * i / beats)
    return TapSession(1.0, tuple(taps))


@pytest.mark.parametrize("seed", range(10))
def test_noisy_steady_taps_one_stable_event(seed: int) -> None:
    derivation = derive_tempo_events(steady_session(seed))
    assert len(derivation.events) == 1
    assert derivation.events[0].position == 0.0
    assert derivation.events[0].bpm == pytest.approx(120.0, abs=2.0)
    assert derivation.first_beat == 0.0 and derivation.last_beat == 31.0
    assert not derivation.warnings


def test_derived_span_telescopes_to_the_tapped_time() -> None:
    """Segment averages are exact between smoothed boundaries: the
    derived map's span equals the tapped span to within the smoothing
    of the two endpoints (≪ tap jitter), so error never accumulates."""
    session = rit_session(seed=5)
    derivation = derive_tempo_events(session)
    m = TempoMap(list(derivation.events))
    derived = m.seconds_at(derivation.last_beat) \
        - m.seconds_at(derivation.first_beat)
    raw = session.taps[-1].seconds - session.taps[0].seconds
    assert derived == pytest.approx(raw, abs=0.05)


@pytest.mark.parametrize("seed", range(10))
def test_rit_becomes_a_decreasing_ramp(seed: int) -> None:
    derivation = derive_tempo_events(rit_session(seed))
    bpms = [e.bpm for e in derivation.events]
    assert len(bpms) >= 3                          # a ramp, not a step
    assert all(b1 < b0 for b0, b1 in zip(bpms, bpms[1:]))
    assert bpms[0] == pytest.approx(120.0, abs=10.0)
    assert bpms[-1] < 92.0                         # heading into the 80
    positions = [e.position for e in derivation.events]
    assert all(0.0 <= p < 16.0 for p in positions)


def test_lock_to_taps_reproduces_every_interval_exactly() -> None:
    session = steady_session(seed=11, n=8, sigma=0.040)
    derivation = lock_to_taps(session)
    assert len(derivation.events) == 7             # one per interval
    m = TempoMap(list(derivation.events))
    for a, b in zip(session.taps, session.taps[1:]):
        got = m.seconds_at(b.beat) - m.seconds_at(a.beat)
        assert got == pytest.approx(b.seconds - a.seconds, abs=1e-9)


def test_start_residual_sign_and_magnitude() -> None:
    m = TempoMap([TempoEvent(0.0, 120.0)])         # beat 8 at 4.0 s score
    late = TapSession(1.0, (Tap(8.0, 5.538), Tap(9.0, 6.038)))
    assert start_residual(late, m, offset_seconds=1.5) \
        == pytest.approx(0.038, abs=1e-9)          # 38 ms late
    early = TapSession(1.0, (Tap(8.0, 5.47), Tap(9.0, 5.97)))
    assert start_residual(early, m, 1.5) == pytest.approx(-0.03, abs=1e-9)


def test_double_tap_and_gap_warnings() -> None:
    base = steady_session(seed=1, n=10, sigma=0.0)
    taps = list(base.taps)
    # simulate a bounced key: tap 5 lands 60 ms after tap 4
    taps[4] = Tap(taps[4].beat, taps[3].seconds + 0.06)
    derivation = derive_tempo_events(TapSession(1.0, tuple(taps)))
    assert any("double-tap" in w for w in derivation.warnings)
    # and a lost tap: long gap
    taps = list(base.taps)
    taps[6] = Tap(taps[6].beat, taps[5].seconds + 1.4)
    with_gap = TapSession(1.0, tuple(
        t if i < 7 else Tap(t.beat, t.seconds + 0.9)
        for i, t in enumerate(taps)))
    derivation = derive_tempo_events(with_gap)
    assert any("gap" in w for w in derivation.warnings)


def test_min_taps_and_monotonicity_validation() -> None:
    short = TapSession(1.0, tuple(Tap(float(i), i * 0.5) for i in range(3)))
    with pytest.raises(ValueError, match="at least"):
        derive_tempo_events(short)
    backwards = TapSession(1.0, (Tap(0.0, 1.0), Tap(1.0, 0.9),
                                 Tap(2.0, 1.5), Tap(3.0, 2.0)))
    with pytest.raises(ValueError, match="increasing"):
        derive_tempo_events(backwards)


def test_non_quarter_unit() -> None:
    """Half-note taps (unit=2): bpm is still quarter bpm."""
    spb = 60.0 / 120.0                             # quarter seconds at 120
    session = TapSession(2.0, tuple(
        Tap(2.0 * i, 5.0 + 2 * i * spb) for i in range(8)))
    derivation = derive_tempo_events(session)
    assert len(derivation.events) == 1
    assert derivation.events[0].bpm == pytest.approx(120.0, abs=1e-6)
