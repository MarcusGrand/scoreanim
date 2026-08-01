"""The whole page breathing, applied to the scene.

Two things move a system's size — the recording's loudness and the
onsets landing on that system — and the policy for both is pure and
lives in core (`core/animation/pulse.py`). All this does is read the
clock, ask for each system's number, and set it on that system's group.

Its own object for the same reason reveal has one: it is a concern the
applier does not otherwise have — a value per FRAME, not one per element
and not one per trigger — and keeping it here means the applier gains
only a seam.

The saving idea is the reveal driver's, borrowed whole: remember the
value last written and do nothing where it has not changed. That cache
is per GROUP now, keyed like the reveal edges, because the bump half
differs from system to system: a page whose other systems are resting
writes only the one that just fired. Silence with no bumps live reads
exactly 1.0, so a quiet passage costs one lookup a frame and no writes
at all; a paused clock re-reads the same time and costs the same.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from scoreanim.core.animation import (SystemBumps, SystemPulse, intensity_at,
                                      pop_at, pulse_scale)
from scoreanim.core.audio import PeakCache
from scoreanim.render.system_group import SystemGroupItem


class PulseDriver:
    """The pulse half of the applier: one size per system at time t."""

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
        # When each system bumps, and how hard — built from the schedule
        # alone, on the seams that move the trigger seconds or the
        # settings. No audio involved.
        self._bumps: Mapping[int, SystemBumps] = {}
        # The value last written per group, keyed (page, system) like the
        # reveal driver's edges. A missing key is "nothing has been
        # written there".
        self._last: dict[tuple[int, int], float] = {}

    # -- configuration -------------------------------------------------------

    def configure(self, peaks: PeakCache | None, offset_seconds: float,
                  reference: float, pulse: SystemPulse) -> None:
        """The recording, the audio time of score beat 0, the loudness
        that counts as full, and the user's settings.

        Turning everything off — or losing the recording with nothing
        else to move the page — puts every system back to exactly 1.0,
        once, and only if something was ever written. Off means the
        groups are untouched, not written with 1.0 every frame."""
        self._peaks = peaks
        self._offset = offset_seconds
        self._reference = reference
        self._pulse = pulse
        if self._is_idle and self._last:
            for group in self._groups:
                group.set_system_scale(1.0)
            self._last.clear()

    def set_bumps(self, bumps: Mapping[int, SystemBumps]) -> None:
        """Where the onset bumps are, by system. Rebuilt wherever the
        trigger seconds are — a tempo edit moves every bump — and
        wherever the settings move, since the strengths are measured
        against `notes_for_full`."""
        self._bumps = bumps

    def invalidate(self) -> None:
        """Forget the values written, so the next apply writes whatever
        it finds. A full refresh does this: the scene may have moved
        under us."""
        self._last.clear()

    # -- application ---------------------------------------------------------

    def apply(self, t_score_seconds: float) -> int:
        """Set every system's size for time t; returns groups touched.

        The loudness is read once for the whole page — it is one number
        at one moment — and each system's own bump goes on top of it.
        `t` is SCORE seconds and the peak cache is indexed from the start
        of the sound file, so the offset goes back on here — the same
        conversion the applier's live per-trigger reading makes.

        A pure function of t: scrubbing, live playback and export all
        read the same size at the same moment. A time before the
        recording or past what has been decoded reads intensity 0, and
        with no bump live that is scale exactly 1.0."""
        if self._is_idle:
            return 0
        intensity = (intensity_at(self._peaks, t_score_seconds + self._offset,
                                  self._reference)
                     if self._peaks is not None else 0.0)
        changed = 0
        for group in self._groups:
            key = (group.page, group.system)
            scale = pulse_scale(
                intensity, self._pulse,
                pop_at(self._bumps.get(group.system), t_score_seconds,
                       self._pulse))
            if self._last.get(key) == scale:
                continue
            self._last[key] = scale
            group.set_system_scale(scale)
            changed += 1
        return changed

    # -- internals -----------------------------------------------------------

    @property
    def _is_idle(self) -> bool:
        """Nothing can move a system: both modes off, or the only mode
        that is on has no recording to read."""
        if self._pulse.pops_on_onsets:
            return False
        return not self._pulse.follows_volume or self._peaks is None
