"""The whole page breathing, in two ways.

Every system takes ONE size at time t, and two things can move it. They
are independent — a knob each, either alone or both together — and what
they contribute ADDS:

    scale = 1 + follow amount × loudness + the live bump

**Follow volume** is the recording's own loudness, read raw through
`intensity_at` (`core/animation/intensity.py`), NOT the quiet-to-loud
gain mapping the volume response uses: this feature has knobs of its
own, and mixing it with that mapping would make two settings fight over
one number. The page swells and shrinks with the playing, the way a
boombox pulses in a music video.

**The onset pop** needs no recording at all. At every beat the system
the notes appear in bumps up and settles back, the way a single note
pops — and the MORE noteheads land on that beat, the stronger the bump.
A lone melody note gives a slight tick; a full chord across the staves
makes the system properly jump. It is driven entirely by the schedule,
so it works with no audio loaded and it is exact under export.

The two are one size in the end, so a system never has to choose: on a
loud chord the page is already swollen and the bump lands on top of it.

It has its own module rather than a fourth section of `intensity.py`
for the same reason that file keeps its two halves apart: `intensity.py`
says what the AUDIO does, and this says what WE DO about it. Same split,
one file down.

Pure, and a pure function of t: scrubbing, live playback and export all
read the same size at the same moment. Silence, no recording, or a time
outside the decoded extent all read intensity 0; with no bump live
either, that lands the scale at exactly 1.0.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from scoreanim.core.animation.scale_groups import HEAD_KINDS
from scoreanim.core.score.identity import ElementKind

DEFAULT_AMOUNT = 0.0        # off: the groups are never touched at all
DEFAULT_POP_AMOUNT = 0.0    # off too — the same "no key means no motion"
DEFAULT_NOTES_FOR_FULL = 6  # how many heads at once make the biggest bump
DEFAULT_SETTLE_S = 0.25     # the note pop's own settle, so it feels the same

# How far the page may breathe, either way. The ceiling is low on
# purpose: a whole system growing is a big gesture, and even 0.05 is
# plenty of motion. Nothing checks whether two systems touch, so this is
# the only guard against a crowded page overlapping at the top of the
# range.
_AMOUNT_RANGE = (0.0, 0.2)
_POP_AMOUNT_RANGE = (0.0, 0.2)

# One head is a tick, and a big tutti chord is the ceiling. Below 1 the
# strength arithmetic would divide by nothing; above 24 no real beat
# reaches full strength and the knob stops meaning anything.
_NOTES_FOR_FULL_RANGE = (1, 24)

# The floor every authored duration takes (presets.py): a settle of 0
# would be a division by nothing, and a bump nobody could see.
_SETTLE_MIN = 0.01


@dataclass(frozen=True)
class SystemPulse:
    """The user's settings. Both amounts 0 turns the whole thing off —
    no system is ever scaled, which is exactly the look before this
    feature existed."""
    amount: float = DEFAULT_AMOUNT              # follows the recording
    pop_amount: float = DEFAULT_POP_AMOUNT      # bumps on every onset
    notes_for_full: int = DEFAULT_NOTES_FOR_FULL
    settle: float = DEFAULT_SETTLE_S            # how long a bump takes to go

    @property
    def follows_volume(self) -> bool:
        return self.amount > 0.0

    @property
    def pops_on_onsets(self) -> bool:
        return self.pop_amount > 0.0

    @property
    def is_off(self) -> bool:
        return not self.follows_volume and not self.pops_on_onsets


@dataclass(frozen=True)
class SystemBumps:
    """One system's bumps: when each one starts, and how hard.

    Two parallel tuples rather than a list of pairs, because reading
    them is a bisect over the times — the same shape the trigger seconds
    themselves have."""
    seconds: tuple[float, ...] = ()     # ascending
    strengths: tuple[float, ...] = ()   # 0..1, parallel to seconds


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def read_pulse(raw: Mapping[str, object] | None) -> SystemPulse:
    """The document's sparse `style.pulse` entry, clamped. The ranges are
    enforced HERE, at consumption, and the command that writes the entry
    checks only that a value is a finite number — the `style.volume`
    precedent, so a hand-edited file cannot make the page jump."""
    raw = raw or {}
    return SystemPulse(
        amount=_clamp(float(raw.get("amount", DEFAULT_AMOUNT)),
                      *_AMOUNT_RANGE),
        pop_amount=_clamp(float(raw.get("pop_amount", DEFAULT_POP_AMOUNT)),
                          *_POP_AMOUNT_RANGE),
        notes_for_full=int(_clamp(
            float(raw.get("notes_for_full", DEFAULT_NOTES_FOR_FULL)),
            *_NOTES_FOR_FULL_RANGE)),
        settle=max(_SETTLE_MIN, float(raw.get("settle", DEFAULT_SETTLE_S))))


def build_bumps(trigger_seconds: Sequence[float],
                rows: Sequence[Iterable[tuple[ElementKind | None,
                                              int | None]]],
                pulse: SystemPulse) -> dict[int, SystemBumps]:
    """Every system's bumps, from the schedule alone.

    `rows[i]` is the (kind, system) of each item firing at trigger `i`,
    in any order. Two things about the counting:

    - Only HEADS count — noteheads, and the slashes a slash region draws
      instead of them. A stem, a dot, a beam or an accidental is ink
      hanging off a head that is already counted, so it must not add
      weight; two heads in one voice (a chord) both do.
    - Each head is counted in the system it ACTUALLY sits in, not in the
      trigger's own system hint. A trigger carries one system, aggregated
      with min() over its fresh onsets, and around a system break a
      single beat's ink can straddle two systems — the same reason the
      reveal driver keys off each item's own system.

    Strength is `heads / notes_for_full`, capped at 1: past that a beat
    is as strong as a beat can be. The amount is NOT folded in here, so
    these lists survive an amount change untouched; `pop_at` applies it.
    """
    seconds: dict[int, list[float]] = {}
    strengths: dict[int, list[float]] = {}
    for t, row in zip(trigger_seconds, rows):
        counts: dict[int, int] = {}
        for kind, system in row:
            if system is not None and kind in HEAD_KINDS:
                counts[system] = counts.get(system, 0) + 1
        for system, count in counts.items():
            seconds.setdefault(system, []).append(t)
            strengths.setdefault(system, []).append(
                min(1.0, count / pulse.notes_for_full))
    # The trigger seconds arrive sorted and each system takes them in
    # that order, so the per-system lists are sorted for free — which is
    # what makes the bisect in pop_at legitimate.
    return {system: SystemBumps(tuple(times), tuple(strengths[system]))
            for system, times in seconds.items()}


def pop_at(bumps: SystemBumps | None, t: float, pulse: SystemPulse) -> float:
    """How far one system is bumped up at time t, on top of everything
    else. 0 when nothing is live.

    The shape is the note pop's, so the two read as the same gesture:
    straight up at the trigger and easing back to nothing over `settle`.
    Overlapping bumps take the LARGEST live one, never the sum — a fast
    run would otherwise stack into an absurd size, and a dense passage
    should read as sustained lift rather than as a climb.

    Cost is a bisect plus a handful of comparisons: the look-back is
    bounded by `settle`, so only the bumps whose window contains t are
    ever looked at."""
    if bumps is None or not pulse.pops_on_onsets:
        return 0.0
    times = bumps.seconds
    # (t - settle, t]: a bump exactly `settle` old has already finished,
    # and one in the future has not started.
    lo = bisect_right(times, t - pulse.settle)
    hi = bisect_right(times, t)
    best = 0.0
    for i in range(lo, hi):
        live = bumps.strengths[i] * (1.0 - (t - times[i]) / pulse.settle)
        if live > best:
            best = live
    return pulse.pop_amount * best


def pulse_scale(intensity: float, pulse: SystemPulse,
                pop: float = 0.0) -> float:
    """How big one system is at one moment: 1.0 leaves it exactly as
    engraved.

    `intensity` is a raw reading in [0, 1] (`intensity.intensity_at`)
    and `pop` is this system's live bump (`pop_at`). The two DEVIATIONS
    add, so either one alone behaves exactly as if the other did not
    exist. With everything off the answer is exactly 1.0, not merely
    close to it, which is what lets the caller skip the groups
    entirely."""
    if pulse.is_off:
        return 1.0
    return 1.0 + pulse.amount * intensity + pop
