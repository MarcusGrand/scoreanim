"""The whole page breathing with the recording.

Every system swells and shrinks together with how loud the recording is
right now, the way a boombox pulses in a music video. One value drives
them all; each system turns around the centre of its own ink, so the
page reads as one object and systems never slide into each other.

The value is
`1 + amount × intensity_at(recording, t + offset)` — the raw loudness
reading from `core/animation/intensity.py`, NOT the quiet-to-loud gain
mapping the volume response uses. This feature has one knob of its own,
and mixing it with that mapping would make two settings fight over one
number.

It has its own module rather than a fourth section of `intensity.py`
for the same reason that file keeps its two halves apart: `intensity.py`
says what the AUDIO does, and this says what WE DO about it. Same split,
one file down.

Pure, and a pure function of t: scrubbing, live playback and export all
read the same size at the same moment. Silence, no recording, or a time
outside the decoded extent all read intensity 0, which lands the scale
at exactly 1.0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

DEFAULT_AMOUNT = 0.0        # off: the groups are never touched at all

# How far the page may breathe. The ceiling is low on purpose: a whole
# system growing is a big gesture, and even 0.05 is plenty of motion.
# Nothing checks whether two systems touch, so this is the only guard
# against a crowded page overlapping at the top of the range.
_AMOUNT_RANGE = (0.0, 0.2)


@dataclass(frozen=True)
class SystemPulse:
    """The one number the user sets. `amount` 0 turns the whole thing
    off — no group is ever scaled, which is exactly the look before this
    feature existed."""
    amount: float = DEFAULT_AMOUNT

    @property
    def is_off(self) -> bool:
        return self.amount <= 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def read_pulse(raw: Mapping[str, object] | None) -> SystemPulse:
    """The document's sparse `style.pulse` entry, clamped. The range is
    enforced HERE, at consumption, and the command that writes the entry
    checks only that a value is a finite number — the `style.volume`
    precedent, so a hand-edited file cannot make the page jump."""
    raw = raw or {}
    return SystemPulse(
        amount=_clamp(float(raw.get("amount", DEFAULT_AMOUNT)),
                      *_AMOUNT_RANGE))


def pulse_scale(intensity: float, pulse: SystemPulse) -> float:
    """How big every system is at one moment: 1.0 leaves the page
    exactly as engraved.

    `intensity` is a raw reading in [0, 1] (`intensity.intensity_at`).
    At amount 0 the answer is exactly 1.0, not merely close to it, which
    is what lets the caller skip the groups entirely."""
    if pulse.is_off:
        return 1.0
    return 1.0 + pulse.amount * intensity
