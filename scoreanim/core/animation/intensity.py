"""How loud the recording is at each trigger, and what that does to the
animation.

The recording already carries the answer: the peak cache
(`core/audio/peaks.py`) holds one rms value per ~11.6 ms bin. This
module reads it at each trigger and hands back ONE number per trigger —
an intensity in [0, 1], and from it a gain. The applier then uses the
gain to scale how far the animation departs from rest, so a loud beat
pops harder than a quiet one.

All of this is derived data, recomputed from the audio and never saved
(rule 5). What the document stores is the three settings below.

Two things stay deliberately separate:

- WHAT the audio says — `trigger_intensities`, an honest 0-to-1 reading
  of the recording. It knows nothing about the user's settings.
- WHAT WE DO ABOUT IT — `gain_for`, one small function, which is where
  the whole mapping lives.

The mapping is linear in rms today. It may become perceptual (based on
decibels, which is closer to how loudness is heard) once we have looked
at it in the app; when it does, `gain_for` and `trigger_intensities`
are the only two places to change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from scoreanim.core.audio.peaks import PeakCache

# How much of the recording to listen to around a trigger. It leans
# forward on purpose: the attack — the loud first moment of a note — is
# what tells a hit apart from a quiet inner voice, and it lands at or
# just after the beat, never before it. The small look-back covers a
# player who is a touch ahead of the click.
WINDOW_BEFORE_S = 0.025
WINDOW_AFTER_S = 0.075

# What counts as "full" loudness. Not the file's loudest bin — one
# stray transient would then flatten every other note to nothing. The
# 95th percentile of the bins that carry any sound at all is steady:
# it ignores a single outlier, and long silences cannot drag it down
# because silent bins are left out of the reckoning.
REFERENCE_PERCENTILE = 95.0

DEFAULT_AMOUNT = 0.0        # off: the feature costs nothing until asked for
DEFAULT_QUIET = 0.5
DEFAULT_LOUD = 1.5

_AMOUNT_RANGE = (0.0, 1.0)
_GAIN_RANGE = (0.0, 5.0)


@dataclass(frozen=True)
class VolumeResponse:
    """The three numbers the user sets. `amount` 0 turns the whole thing
    off — gain 1 everywhere, which is exactly the look before this
    feature existed."""
    amount: float = DEFAULT_AMOUNT
    quiet: float = DEFAULT_QUIET     # gain at intensity 0
    loud: float = DEFAULT_LOUD       # gain at intensity 1

    @property
    def is_off(self) -> bool:
        return self.amount <= 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def read_volume(raw: Mapping[str, object] | None) -> VolumeResponse:
    """The document's sparse `style.volume` entry, clamped. Ranges are
    enforced HERE, at consumption, and the command that writes the entry
    checks only that a value is a finite number — the `effect_params`
    precedent, so a hand-edited file cannot produce a broken animation."""
    raw = raw or {}
    return VolumeResponse(
        amount=_clamp(float(raw.get("amount", DEFAULT_AMOUNT)),
                      *_AMOUNT_RANGE),
        quiet=_clamp(float(raw.get("quiet", DEFAULT_QUIET)), *_GAIN_RANGE),
        loud=_clamp(float(raw.get("loud", DEFAULT_LOUD)), *_GAIN_RANGE),
    )


def peak_reference(cache: PeakCache) -> float:
    """The rms value that counts as intensity 1. See
    REFERENCE_PERCENTILE. Returns 0 for an empty or wholly silent
    file, which the caller reads as "no loudness information"."""
    if not cache.levels:
        return 0.0
    rms = cache.levels[0].rms
    if len(rms) == 0:
        return 0.0
    sounding = rms[rms > 0.0]
    if len(sounding) == 0:
        return 0.0
    return float(np.percentile(sounding, REFERENCE_PERCENTILE))


def trigger_intensities(cache: PeakCache,
                        times_seconds: Sequence[float]) -> tuple[float, ...]:
    """One loudness reading in [0, 1] per time, in the order given.

    The times are AUDIO seconds — measured from the start of the sound
    file, which is what the cache is indexed by. Score seconds have to
    have the project's offset added before they get here.

    Each reading is the loudest rms bin in the window around the time,
    at the finest level the cache has (~11.6 ms per bin), over the
    reference above. A time before the recording starts, or past what
    has been decoded, reads 0."""
    reference = peak_reference(cache)
    if reference <= 0.0:
        return tuple(0.0 for _ in times_seconds)
    level = cache.levels[0]
    n_bins = len(level.rms)
    # bin index from seconds — the one conversion peaks.py uses
    bins_per_sec = cache.sample_rate / level.samples_per_bin
    out: list[float] = []
    for t in times_seconds:
        lo = int((t - WINDOW_BEFORE_S) * bins_per_sec)
        hi = int((t + WINDOW_AFTER_S) * bins_per_sec) + 1
        lo = max(lo, 0)
        hi = min(hi, n_bins)
        if hi <= lo:                 # before the start, or past the end
            out.append(0.0)
            continue
        out.append(_clamp(float(level.rms[lo:hi].max()) / reference,
                          0.0, 1.0))
    return tuple(out)


def gain_for(intensity: float, volume: VolumeResponse) -> float:
    """How strongly a trigger animates: 1.0 leaves it exactly as
    authored, above 1 exaggerates it, below 1 tones it down.

    Two steps. First read the intensity onto the user's quiet-to-loud
    range. Then mix that with 1.0 by `amount`, so the amount slider goes
    smoothly from "no response at all" to the full range — and at amount
    0 the answer is exactly 1.0, not merely close to it."""
    if volume.is_off:
        return 1.0
    raw = volume.quiet + (volume.loud - volume.quiet) * intensity
    return 1.0 + (raw - 1.0) * volume.amount


def trigger_gains(cache: PeakCache | None, times_seconds: Sequence[float],
                  volume: VolumeResponse) -> tuple[float, ...] | None:
    """One gain per trigger, or None when there is nothing to do — no
    recording, or the response turned off. None is not "all ones": it
    tells the caller to skip the modulation entirely, which is what
    keeps the old look bit-for-bit identical."""
    if cache is None or volume.is_off or not times_seconds:
        return None
    return tuple(gain_for(value, volume)
                 for value in trigger_intensities(cache, times_seconds))
