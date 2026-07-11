"""Waveform peak cache: multi-resolution min/max/rms bins (PHASES 4.1).

Derived data, never persisted (rule 5) — recomputed per audio load by an
event-driven decoder in ui land feeding ``PeakCacheBuilder.add_samples``
chunk by chunk (chunking is invariant: any split gives the same bins).
``snapshot()`` is cheap, so the waveform can render progressively while
the decode runs.

The pyramid keeps painting O(pixels) at every zoom: level 0 bins
``base_bin`` samples (~11.6 ms at 44.1 kHz), each level above halves the
resolution; ``level_for`` picks the coarsest level that still gives at
least one bin per pixel, and ``column_extents`` reduces the visible bins
to exactly one (min, max, rms) triple per pixel column.

Pure numpy — no Qt (enforced by tests/test_no_qt_in_core.py). numpy is
already a hard transitive dependency (music21); Phase 4 declares it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PeakLevel:
    samples_per_bin: int
    mins: np.ndarray             # float32 in [-1, 1], one per bin
    maxs: np.ndarray
    rms: np.ndarray


@dataclass(frozen=True)
class PeakCache:
    sample_rate: int
    n_samples: int               # mono samples binned so far
    levels: tuple[PeakLevel, ...]        # levels[0] finest, ×2 per level

    @property
    def duration_seconds(self) -> float:
        return self.n_samples / self.sample_rate

    def level_for(self, seconds_per_pixel: float) -> PeakLevel:
        """Coarsest level still giving ≥ 1 bin per pixel column."""
        samples_per_pixel = seconds_per_pixel * self.sample_rate
        chosen = self.levels[0]
        for level in self.levels:
            if level.samples_per_bin <= samples_per_pixel:
                chosen = level
            else:
                break
        return chosen


def to_mono(interleaved: np.ndarray, channels: int) -> np.ndarray:
    """Interleaved float frames → mono by channel mean. A trailing
    partial frame (decoder artifact) is dropped."""
    if channels <= 1:
        return interleaved.astype(np.float32, copy=False)
    frames = len(interleaved) // channels
    return interleaved[:frames * channels].reshape(frames, channels) \
        .mean(axis=1, dtype=np.float32)


class PeakCacheBuilder:
    """Chunk-fed accumulator. Full bins are reduced immediately; the
    sub-bin remainder is carried so chunk boundaries never show."""

    def __init__(self, sample_rate: int, base_bin: int = 512,
                 n_levels: int = 9) -> None:
        if sample_rate <= 0 or base_bin <= 0 or n_levels < 1:
            raise ValueError("sample_rate, base_bin, n_levels must be > 0")
        self._rate = sample_rate
        self._base_bin = base_bin
        self._n_levels = n_levels
        self._tail = np.empty(0, dtype=np.float32)
        self._mins: list[np.ndarray] = []
        self._maxs: list[np.ndarray] = []
        self._sumsq: list[np.ndarray] = []   # mean square per bin, actually
        self._n_samples = 0

    def add_samples(self, mono: np.ndarray) -> None:
        mono = mono.astype(np.float32, copy=False)
        self._n_samples += len(mono)
        data = np.concatenate([self._tail, mono]) if len(self._tail) \
            else mono
        n_bins = len(data) // self._base_bin
        self._tail = data[n_bins * self._base_bin:]
        if n_bins == 0:
            return
        binned = data[:n_bins * self._base_bin].reshape(n_bins,
                                                        self._base_bin)
        self._mins.append(binned.min(axis=1))
        self._maxs.append(binned.max(axis=1))
        self._sumsq.append(np.square(binned).mean(axis=1))

    def snapshot(self) -> PeakCache:
        """Current state as an immutable cache — cheap enough to call on
        every progress tick. The carried tail (if any) becomes a final
        partial bin so the waveform reaches the true end."""
        mins = np.concatenate(self._mins) if self._mins \
            else np.empty(0, dtype=np.float32)
        maxs = np.concatenate(self._maxs) if self._maxs \
            else np.empty(0, dtype=np.float32)
        meansq = np.concatenate(self._sumsq) if self._sumsq \
            else np.empty(0, dtype=np.float32)
        if len(self._tail):
            mins = np.append(mins, self._tail.min())
            maxs = np.append(maxs, self._tail.max())
            meansq = np.append(meansq, np.square(self._tail).mean())

        levels = [PeakLevel(self._base_bin, mins.astype(np.float32),
                            maxs.astype(np.float32),
                            np.sqrt(meansq, dtype=np.float32))]
        spb = self._base_bin
        for _ in range(1, self._n_levels):
            spb *= 2
            if len(mins) < 2:
                break
            pairs = len(mins) // 2
            odd = len(mins) - pairs * 2
            m2 = np.minimum(mins[:pairs * 2:2], mins[1:pairs * 2:2])
            x2 = np.maximum(maxs[:pairs * 2:2], maxs[1:pairs * 2:2])
            q2 = (meansq[:pairs * 2:2] + meansq[1:pairs * 2:2]) / 2
            if odd:                          # carry the unpaired last bin
                m2 = np.append(m2, mins[-1])
                x2 = np.append(x2, maxs[-1])
                q2 = np.append(q2, meansq[-1])
            mins, maxs, meansq = m2, x2, q2
            levels.append(PeakLevel(spb, mins.astype(np.float32),
                                    maxs.astype(np.float32),
                                    np.sqrt(meansq, dtype=np.float32)))
        return PeakCache(sample_rate=self._rate, n_samples=self._n_samples,
                         levels=tuple(levels))


def column_extents(cache: PeakCache, t0: float, t1: float,
                   width_px: int) -> np.ndarray:
    """(width_px, 3) float32 of (min, max, rms) per pixel column for the
    visible window [t0, t1] — the paint routine draws exactly this.
    Columns past the decoded extent (or an empty cache) are zero."""
    out = np.zeros((width_px, 3), dtype=np.float32)
    if width_px <= 0 or t1 <= t0 or cache.n_samples == 0:
        return out
    level = cache.level_for((t1 - t0) / width_px)
    bins_per_sec = cache.sample_rate / level.samples_per_bin
    n_bins = len(level.mins)
    edges = (t0 + (t1 - t0) * np.arange(width_px + 1) / width_px)
    idx = np.clip((edges * bins_per_sec).astype(np.int64), 0, n_bins)
    for col in range(width_px):
        lo, hi = idx[col], idx[col + 1]
        if lo >= n_bins:             # past the decoded extent: stays zero
            continue
        if hi <= lo:                 # sub-bin column: sample the bin under it
            hi = lo + 1
        out[col, 0] = level.mins[lo:hi].min()
        out[col, 1] = level.maxs[lo:hi].max()
        out[col, 2] = np.sqrt(np.square(level.rms[lo:hi]).mean())
    return out
