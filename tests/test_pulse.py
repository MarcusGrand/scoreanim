"""The system pulse value: what the document says, and what size that
makes the page.

Pure — no scene, no Qt. The reading it multiplies (`intensity_at`) has
its own tests in test_intensity.py; what is pinned here is the one knob,
its clamp, and the exactly-1.0 guarantee the render side leans on to
decide it may skip the systems entirely.
"""

import pytest

from scoreanim.core.animation.pulse import (DEFAULT_AMOUNT, SystemPulse,
                                            pulse_scale, read_pulse)


# -- reading the document ------------------------------------------------


def test_an_empty_document_is_off() -> None:
    for raw in (None, {}):
        pulse = read_pulse(raw)
        assert pulse.amount == DEFAULT_AMOUNT == 0.0
        assert pulse.is_off


def test_the_amount_is_clamped_at_both_ends() -> None:
    """The range is enforced here, at consumption, so a hand-edited file
    cannot make the page jump."""
    assert read_pulse({"amount": -1.0}).amount == 0.0
    assert read_pulse({"amount": 0.05}).amount == 0.05
    assert read_pulse({"amount": 0.2}).amount == 0.2
    assert read_pulse({"amount": 3.0}).amount == 0.2      # the ceiling


def test_a_key_this_build_does_not_consume_is_ignored() -> None:
    """Reading tolerates it; serialization keeps it (test_project_
    serialize.py) — together that is the raw round-trip guarantee."""
    pulse = read_pulse({"amount": 0.1, "shape": "square"})
    assert pulse.amount == 0.1


def test_an_int_amount_reads_as_a_number() -> None:
    assert read_pulse({"amount": 0}).is_off


# -- what it does --------------------------------------------------------


def test_off_is_exactly_one_at_every_loudness() -> None:
    """Exactly, not approximately: the driver compares against 1.0 to
    decide whether a system needs touching at all."""
    off = SystemPulse(amount=0.0)
    for intensity in (0.0, 0.25, 0.5, 1.0):
        assert pulse_scale(intensity, off) == 1.0


def test_silence_is_exactly_one_even_at_full_amount() -> None:
    assert pulse_scale(0.0, SystemPulse(amount=0.2)) == 1.0


def test_the_scale_is_one_plus_amount_times_intensity() -> None:
    pulse = SystemPulse(amount=0.1)
    assert pulse_scale(1.0, pulse) == pytest.approx(1.1)
    assert pulse_scale(0.5, pulse) == pytest.approx(1.05)
    assert pulse_scale(0.25, pulse) == pytest.approx(1.025)


def test_a_louder_moment_is_always_a_bigger_page() -> None:
    pulse = SystemPulse(amount=0.05)
    sizes = [pulse_scale(i / 10.0, pulse) for i in range(11)]
    assert sizes == sorted(sizes)
    assert sizes[0] == 1.0
    assert sizes[-1] == pytest.approx(1.05)
