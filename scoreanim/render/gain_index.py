"""How strongly each element animates: the volume response's bookkeeping.

A loud beat pops harder than a quiet one. The reading itself and the
mapping from a reading to a gain are pure and live in core
(`core/animation/intensity.py`); this holds the state around them — the
recording, the loudness that counts as full, and one gain per element —
so the applier gains a seam instead of five fields.

The third half of the applier, after reveal and pulse, and here for the
same reason both of those are: it is a concern with its own inputs and
its own rebuild seams. Unlike those two it touches no Qt at all — it
deals in element ids and numbers, never in items. It sits in `render/`
anyway, because it is the applier's own working state rather than
something core would hand anybody else.

Every element gets its own window: its trigger, out to the end of its
notated duration, so two notes on the same beat with different lengths
read different stretches of the recording. An element whose effects
FOLLOW the recording ignores that average and reads how loud things are
right now, every time it re-evaluates — `live_gain` is that reading, one
lookup per trigger per frame.

No recording, or the response turned off, means no gains at all
(`row` returns None), which is what keeps the look bit-for-bit what it
was before the feature existed.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from scoreanim.core.animation import (VolumeResponse, audio_windows, gain_for,
                                      intensity_at, peak_reference,
                                      read_volume, window_gains)
from scoreanim.core.audio import PeakCache
from scoreanim.core.score.identity import Beats, ElementId
from scoreanim.core.timing import SwingRegion, TempoMap


class GainIndex:
    """One gain per element, rebuilt from the three things that move it:
    the recording, the settings, and the seconds axis."""

    def __init__(self, beats_per_trigger: Sequence[Beats],
                 element_ids_per_trigger: Sequence[Sequence[ElementId | None]],
                 duration_by_element: Mapping[ElementId, Beats]) -> None:
        # The schedule, in the shape the pure window arithmetic wants
        # (core/animation/windows.py): ids and beats, never items. An
        # element with no identity contributes None, which every duration
        # lookup treats as "no engraved duration".
        self._beats = tuple(beats_per_trigger)
        self._element_ids = tuple(tuple(row)
                                  for row in element_ids_per_trigger)
        self._duration_by_element = duration_by_element
        # The recording, and the audio time of score beat 0 — what turns
        # a trigger's score seconds into the audio seconds the peak cache
        # is indexed by.
        self._peaks: PeakCache | None = None
        self._offset = 0.0
        self._gains: tuple[tuple[float, ...], ...] | None = None
        # The settings a reading is mapped through, and the "full
        # loudness" it is measured against. The reference is a percentile
        # over every bin, so it is worked out on the seams that can move
        # it and handed to each lookup, never recomputed per frame.
        self._volume = VolumeResponse()
        self._reference = 0.0

    # -- what the recording is -----------------------------------------------

    @property
    def peaks(self) -> PeakCache | None:
        return self._peaks

    @property
    def offset(self) -> float:
        """The audio time of score beat 0."""
        return self._offset

    @property
    def reference(self) -> float:
        """The loudness that counts as full — 0 with no recording."""
        return self._reference

    @property
    def gains(self) -> tuple[tuple[float, ...], ...] | None:
        """Every gain, in the schedule's own shape; None means no
        modulation at all."""
        return self._gains

    def set_audio(self, peaks: PeakCache | None,
                  offset_seconds: float) -> bool:
        """The recording the animation follows. Returns whether anything
        actually moved, so the caller can skip the rebuild and the
        refresh when it did not."""
        if peaks is self._peaks and offset_seconds == self._offset:
            return False
        self._peaks = peaks
        self._offset = offset_seconds
        return True

    # -- rebuilding ----------------------------------------------------------

    def recompute(self, trigger_seconds: Sequence[float],
                  tempo_map: TempoMap | None,
                  swing: Sequence[SwingRegion],
                  volume_raw: Mapping[str, object]) -> None:
        """Re-read the gains from ALL THREE seams that can move them: the
        audio, the settings, and the seconds axis itself — a tempo edit
        slides every element to a different stretch of the recording, and
        it moves both ends of that stretch.

        The engraved end of each window resolves through the ONE
        swing-aware seam in a single batched call, the same pattern
        `derive_windows` uses for the settle stretches. An element the
        duration map omits (dynamics, texts) gets a zero-length window,
        which intensity.py reads as "use the attack"."""
        self._volume = read_volume(volume_raw)
        self._reference = (peak_reference(self._peaks)
                           if self._peaks is not None else 0.0)
        rows = audio_windows(self._beats, trigger_seconds, self._element_ids,
                             self._duration_by_element, tempo_map, swing,
                             self._offset)
        flat = window_gains(self._peaks,
                            [w for row in rows for w in row], self._volume)
        if flat is None:
            self._gains = None
            return
        out: list[tuple[float, ...]] = []
        at = 0
        for row in rows:
            out.append(tuple(flat[at:at + len(row)]))
            at += len(row)
        self._gains = tuple(out)

    # -- reading -------------------------------------------------------------

    def row(self, i: int) -> tuple[float, ...] | None:
        """The gains of trigger `i`'s elements, or None for no
        modulation at all."""
        return self._gains[i] if self._gains is not None else None

    def live_gain(self, t_score_seconds: float) -> float:
        """How loud the recording is at THIS moment, as a gain — what an
        element that follows the recording takes instead of the average
        over its own note. Score seconds in; the offset makes them audio
        seconds, the same conversion the windows make."""
        return gain_for(
            intensity_at(self._peaks, t_score_seconds + self._offset,
                         self._reference),
            self._volume)
