"""Peak cache math (PHASES 4.1), headless with synthetic signals."""
from __future__ import annotations

import numpy as np
import pytest

from scoreanim.core.audio import (PeakCache, PeakCacheBuilder, column_extents,
                                  to_mono)

RATE = 48_000


def _sine(seconds: float, freq: float = 440.0, amp: float = 0.8,
          rate: int = RATE) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _build(signal: np.ndarray, chunk: int | None = None,
           **kwargs) -> PeakCache:
    builder = PeakCacheBuilder(RATE, **kwargs)
    if chunk is None:
        builder.add_samples(signal)
    else:
        for i in range(0, len(signal), chunk):
            builder.add_samples(signal[i:i + chunk])
    return builder.snapshot()


def test_sine_min_max_rms() -> None:
    cache = _build(_sine(2.0, amp=0.8))
    base = cache.levels[0]
    # every full bin spans ~4.7 periods: extremes ≈ ±A, rms ≈ A/√2
    assert base.mins[:-1] == pytest.approx(-0.8, abs=0.01)
    assert base.maxs[:-1] == pytest.approx(0.8, abs=0.01)
    assert base.rms[:-1] == pytest.approx(0.8 / np.sqrt(2), abs=0.02)
    assert cache.duration_seconds == pytest.approx(2.0)


def test_chunk_feeding_is_invariant() -> None:
    signal = np.random.default_rng(7).normal(0, 0.3, RATE * 3) \
        .astype(np.float32)
    one_shot = _build(signal)
    for chunk in (100, 1152, 4096, 4097):          # odd sizes included
        chunked = _build(signal, chunk=chunk)
        for a, b in zip(one_shot.levels, chunked.levels):
            np.testing.assert_array_equal(a.mins, b.mins)
            np.testing.assert_array_equal(a.maxs, b.maxs)
            np.testing.assert_allclose(a.rms, b.rms, atol=1e-6)


def test_pyramid_levels_reduce_exactly() -> None:
    signal = np.random.default_rng(3).normal(0, 0.3, RATE * 2) \
        .astype(np.float32)
    cache = _build(signal)
    for finer, coarser in zip(cache.levels, cache.levels[1:]):
        assert coarser.samples_per_bin == finer.samples_per_bin * 2
        pairs = len(finer.mins) // 2
        np.testing.assert_array_equal(
            coarser.mins[:pairs],
            np.minimum(finer.mins[:pairs * 2:2], finer.mins[1:pairs * 2:2]))
        np.testing.assert_array_equal(
            coarser.maxs[:pairs],
            np.maximum(finer.maxs[:pairs * 2:2], finer.maxs[1:pairs * 2:2]))
        np.testing.assert_allclose(
            coarser.rms[:pairs],
            np.sqrt((np.square(finer.rms[:pairs * 2:2])
                     + np.square(finer.rms[1:pairs * 2:2])) / 2),
            atol=1e-6)


def test_level_for_selection() -> None:
    cache = _build(_sine(10.0))
    base = cache.levels[0].samples_per_bin
    # exactly base-bin density → base level
    assert cache.level_for(base / RATE) is cache.levels[0]
    # zoomed in far beyond the base bin → still the finest level
    assert cache.level_for(1e-6) is cache.levels[0]
    # zoomed way out → a coarser level, but ≥ 1 bin per pixel
    wide = cache.level_for(1.0)
    assert wide.samples_per_bin > base
    assert wide.samples_per_bin <= RATE


def test_to_mono_means_channels() -> None:
    left = np.ones(4, dtype=np.float32)
    right = np.zeros(4, dtype=np.float32)
    interleaved = np.ravel(np.column_stack([left, right]))
    np.testing.assert_array_equal(to_mono(interleaved, 2),
                                  np.full(4, 0.5, dtype=np.float32))
    # trailing partial frame dropped
    np.testing.assert_array_equal(to_mono(interleaved[:-1], 2),
                                  np.full(3, 0.5, dtype=np.float32))


def test_column_extents_known_signal() -> None:
    # 1 s silence, then 1 s of ±0.8 sine
    signal = np.concatenate([np.zeros(RATE, dtype=np.float32),
                             _sine(1.0, amp=0.8)])
    cache = _build(signal)
    cols = column_extents(cache, 0.0, 2.0, 200)
    assert cols.shape == (200, 3)
    silent, loud = cols[:98], cols[102:198]
    assert np.abs(silent).max() == 0.0
    assert loud[:, 0] == pytest.approx(-0.8, abs=0.02)
    assert loud[:, 1] == pytest.approx(0.8, abs=0.02)
    assert loud[:, 2] == pytest.approx(0.8 / np.sqrt(2), abs=0.03)


def test_column_extents_past_end_and_empty() -> None:
    cache = _build(_sine(1.0))
    cols = column_extents(cache, 0.5, 3.0, 100)
    # data ends at t=1.0 → column 20; column 20 itself may still touch the
    # final partial bin (sub-bin boundary spill), everything after is zero
    assert np.abs(cols[21:]).max() == 0.0      # past the decoded end: zero
    assert np.abs(cols[:18]).max() > 0.1
    empty = PeakCacheBuilder(RATE).snapshot()
    assert np.abs(column_extents(empty, 0.0, 1.0, 50)).max() == 0.0


def test_partial_snapshot_grows_consistently() -> None:
    signal = _sine(2.0)
    builder = PeakCacheBuilder(RATE)
    builder.add_samples(signal[:RATE // 2])
    early = builder.snapshot()
    assert early.duration_seconds == pytest.approx(0.5)
    builder.add_samples(signal[RATE // 2:])
    full = builder.snapshot()
    assert full.duration_seconds == pytest.approx(2.0)
    # the early snapshot's full bins are a prefix of the final ones
    n = len(early.levels[0].mins) - 1          # last early bin may be partial
    np.testing.assert_array_equal(early.levels[0].mins[:n],
                                  full.levels[0].mins[:n])
