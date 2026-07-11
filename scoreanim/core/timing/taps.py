"""Tap capture: raw performance taps → tempo events (PHASES 4.3).

A tap is (beat, RAW audio seconds) — audio seconds, not score seconds, so
sessions survive later offset edits and re-derivation is always possible
(ARCHITECTURE.md §4: raw taps are part of the project document). Beats
are assigned at capture time: the first tap anchors to the nearest beat
under the then-current map, every later tap is ``first + n * unit``
(ruling 2026-07-11).

Derivation (``derive_tempo_events``) must not turn ±20–40 ms of human
tap jitter into jittery quarter spacing:

1. Each tap's time is smoothed by a Theil–Sen fit over a ±``window``
   neighborhood — the median pairwise slope is robust to one outlier tap
   per window, and a 5-point fit cuts single-interval BPM noise from
   ~8–12 % to ~2 % at 30 ms jitter.
2. Greedy segmentation over the smoothed series: a new segment starts
   when the local BPM drifts from the running segment average by more
   than max(abs_tol, rel_tol·avg). Steady tapping → ONE event; a rit.
   crosses the threshold repeatedly → a ramp of events.
3. Each segment emits its exact average BPM between smoothed boundary
   times, so total duration telescopes — error never accumulates across
   segments.

Alignment is never absorbed globally: derived events live only inside
[first_beat, last_beat) and the map before the tapped span stays the
authority (``start_residual`` reports the mismatch; re-tap is cheap).
``lock_to_taps`` instead emits one event per interval — dense hard
anchors reproducing every tap exactly, for elastic passages.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from scoreanim.core.score.identity import Beats
from scoreanim.core.timing.tempo_map import TempoEvent, TempoMap

MIN_TAPS = 4


@dataclass(frozen=True)
class Tap:
    beat: Beats                  # assigned at capture (first + n * unit)
    seconds: float               # raw audio seconds from the AudioClock


@dataclass(frozen=True)
class TapSession:
    unit: Beats                  # beats per tap (1.0 = quarter notes)
    taps: tuple[Tap, ...]        # strictly increasing in beat and seconds


@dataclass(frozen=True)
class TapDerivation:
    events: tuple[TempoEvent, ...]       # positions in [first_beat, last_beat)
    first_beat: Beats
    last_beat: Beats
    warnings: tuple[str, ...]


def derive_tempo_events(session: TapSession, *, window: int = 2,
                        rel_tol: float = 0.06, abs_tol: float = 2.0,
                        min_taps: int = MIN_TAPS) -> TapDerivation:
    beats, seconds = _validated(session, min_taps)
    warnings = _interval_warnings(seconds)
    smoothed = _theil_sen_times(beats, seconds, window)

    n = len(beats)
    boundaries = [0]
    for i in range(1, n):
        k = boundaries[-1]
        if i - k < 2:
            continue
        segment_bpm = 60.0 * (beats[i] - beats[k]) / (smoothed[i]
                                                      - smoothed[k])
        local_bpm = _local_bpm(beats, smoothed, i, window)
        if abs(local_bpm - segment_bpm) > max(abs_tol,
                                              rel_tol * segment_bpm):
            boundaries.append(i - 1)
    if boundaries[-1] != n - 1:
        boundaries.append(n - 1)
    # a final segment of a single interval is pure jitter, not a tempo
    # change — merge it into its predecessor
    if len(boundaries) >= 3 and boundaries[-1] - boundaries[-2] < 2:
        del boundaries[-2]

    events = tuple(
        TempoEvent(beats[p], 60.0 * (beats[q] - beats[p])
                   / (smoothed[q] - smoothed[p]))
        for p, q in zip(boundaries, boundaries[1:]))
    return TapDerivation(events=events, first_beat=beats[0],
                         last_beat=beats[-1], warnings=warnings)


def lock_to_taps(session: TapSession, *,
                 min_taps: int = 2) -> TapDerivation:
    """One event per raw interval — hard anchors: a TempoMap built from
    them reproduces every tap-to-tap interval exactly."""
    beats, seconds = _validated(session, min_taps)
    events = tuple(
        TempoEvent(beats[i], 60.0 * (beats[i + 1] - beats[i])
                   / (seconds[i + 1] - seconds[i]))
        for i in range(len(beats) - 1))
    return TapDerivation(events=events, first_beat=beats[0],
                         last_beat=beats[-1],
                         warnings=_interval_warnings(seconds))


def start_residual(session: TapSession, tempo_map: TempoMap,
                   offset_seconds: float) -> float:
    """How late (+) or early (−) the first tap is against the current
    map. Reported, never auto-absorbed: the map before the tapped span
    stays the authority on absolute alignment."""
    first = session.taps[0]
    return first.seconds - (offset_seconds
                            + tempo_map.seconds_at(first.beat))


# ---------------------------------------------------------------------------

def _validated(session: TapSession,
               min_taps: int) -> tuple[list[Beats], list[float]]:
    taps = session.taps
    if len(taps) < min_taps:
        raise ValueError(f"need at least {min_taps} taps, got {len(taps)}")
    beats = [t.beat for t in taps]
    seconds = [t.seconds for t in taps]
    if any(b1 <= b0 for b0, b1 in zip(beats, beats[1:])) \
            or any(s1 <= s0 for s0, s1 in zip(seconds, seconds[1:])):
        raise ValueError("taps must be strictly increasing in beat and time")
    return beats, seconds


def _interval_warnings(seconds: list[float]) -> tuple[str, ...]:
    """Suspicious intervals are flagged, never dropped: beats were
    assigned sequentially at capture, so dropping a tap would shift
    every later beat number. A bad session is re-tapped (one undo)."""
    intervals = [s1 - s0 for s0, s1 in zip(seconds, seconds[1:])]
    if not intervals:
        return ()
    m = median(intervals)
    warnings = []
    for i, dt in enumerate(intervals):
        if dt < 0.4 * m:
            warnings.append(f"possible double-tap at tap {i + 2}")
        elif dt > 2.5 * m:
            warnings.append(f"gap after tap {i + 1}")
    return tuple(warnings)


def _theil_sen_times(beats: list[Beats], seconds: list[float],
                     window: int) -> list[float]:
    """Per-tap robust local fit: median pairwise slope over the ±window
    neighborhood, median intercept, evaluated at the tap's own beat."""
    n = len(beats)
    smoothed = []
    for i in range(n):
        lo, hi = max(0, i - window), min(n - 1, i + window)
        idx = range(lo, hi + 1)
        slopes = [(seconds[j] - seconds[k]) / (beats[j] - beats[k])
                  for j in idx for k in idx if j > k]
        c = median(slopes)
        a = median(seconds[j] - c * beats[j] for j in idx)
        smoothed.append(a + c * beats[i])
    return smoothed


def _local_bpm(beats: list[Beats], smoothed: list[float], i: int,
               window: int) -> float:
    """Local tempo at tap i from the smoothed series (central slope)."""
    lo, hi = max(0, i - window), min(len(beats) - 1, i + window)
    return 60.0 * (beats[hi] - beats[lo]) / (smoothed[hi] - smoothed[lo])
