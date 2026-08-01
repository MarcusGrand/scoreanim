"""The whole page breathing with the recording.

Every system swells and shrinks together with how loud the recording is
right now. The policy is pure and lives in core
(`core/animation/pulse.py`); all this does is read the clock, ask for
the one number, and set it on every system group.

Its own object for the same reason reveal has one: it is a concern the
applier does not otherwise have — one value per FRAME, not one per
element and not one per trigger — and keeping it here means the applier
gains only a seam.

The saving idea is the reveal driver's, borrowed whole: remember the
value last written and do nothing when it has not changed. Silence reads
intensity 0, which is exactly 1.0, so a quiet passage costs one lookup a
frame and no writes at all; a paused clock re-reads the same time and
costs the same. Only music that is actually moving writes, which is the
feature.
"""
from __future__ import annotations

from typing import Iterable

from scoreanim.core.animation import SystemPulse, intensity_at, pulse_scale
from scoreanim.core.audio import PeakCache
from scoreanim.render.system_group import SystemGroupItem


class PulseDriver:
    """The pulse half of the applier: one size for the page at time t,
    set on every system."""

    def __init__(self, groups: Iterable[SystemGroupItem] = ()) -> None:
        self._groups = tuple(groups)
        # The recording and how to read it, all pushed in from the
        # applier's own seams. The reference is a percentile over every
        # bin, so it is worked out where the audio changes and handed to
        # each lookup, never recomputed per frame.
        self._peaks: PeakCache | None = None
        self._offset = 0.0
        self._reference = 0.0
        self._pulse = SystemPulse()
        # The value last written, or None for "nothing has been written"
        # — the reveal driver's edge cache, one value instead of a map
        # because every system takes the same one.
        self._last: float | None = None

    # -- configuration -------------------------------------------------------

    def configure(self, peaks: PeakCache | None, offset_seconds: float,
                  reference: float, pulse: SystemPulse) -> None:
        """The recording, the audio time of score beat 0, the loudness
        that counts as full, and the user's one setting.

        Turning it off — or losing the recording — puts every system
        back to exactly 1.0, once, and only if something was ever
        written. Off means the groups are untouched, not written with
        1.0 every frame."""
        self._peaks = peaks
        self._offset = offset_seconds
        self._reference = reference
        self._pulse = pulse
        if self._is_idle and self._last is not None:
            self._write(1.0)
            self._last = None

    def invalidate(self) -> None:
        """Forget the value written, so the next apply writes whatever it
        finds. A full refresh does this: the scene may have moved under
        us."""
        self._last = None

    # -- application ---------------------------------------------------------

    def apply(self, t_score_seconds: float) -> int:
        """Set every system's size for time t; returns groups touched.

        `t` is SCORE seconds and the peak cache is indexed from the start
        of the sound file, so the offset goes back on here — the same
        conversion the applier's live per-trigger reading makes.

        A pure function of t: scrubbing, live playback and export all
        read the same size at the same moment. A time before the
        recording or past what has been decoded reads intensity 0, which
        is scale exactly 1.0."""
        if self._is_idle:
            return 0
        scale = pulse_scale(
            intensity_at(self._peaks, t_score_seconds + self._offset,
                         self._reference),
            self._pulse)
        if scale == self._last:
            return 0
        self._last = scale
        return self._write(scale)

    # -- internals -----------------------------------------------------------

    @property
    def _is_idle(self) -> bool:
        return self._pulse.is_off or self._peaks is None

    def _write(self, scale: float) -> int:
        for group in self._groups:
            group.set_system_scale(scale)
        return len(self._groups)
