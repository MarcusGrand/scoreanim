"""The volume response: reading loudness out of the peak cache, and
turning it into a per-trigger gain.

Every cache here is built by the real PeakCacheBuilder from samples we
wrote ourselves, so the numbers under test are the ones the app would
actually see.
"""
from __future__ import annotations

import numpy as np
import pytest

from scoreanim.core.animation.intensity import (DEFAULT_LOUD, DEFAULT_QUIET,
                                                SMOOTHING_S, VolumeResponse,
                                                _smoothing_level, gain_for,
                                                intensity_at, peak_reference,
                                                read_volume,
                                                trigger_intensities,
                                                window_gains,
                                                window_intensities)
from scoreanim.core.audio import PeakCacheBuilder

RATE = 44100
BIN = 512                    # samples per bin at the finest level
BIN_S = BIN / RATE           # ~11.6 ms


def _cache(seconds: float, bursts=(), floor: float = 0.0):
    """A cache of `seconds` of sound at `floor` loudness, with a burst
    of the given amplitude at each (start second, length seconds)."""
    samples = np.full(int(seconds * RATE), floor, dtype=np.float32)
    for start, length, amplitude in bursts:
        lo = int(start * RATE)
        samples[lo:lo + int(length * RATE)] = amplitude
    builder = PeakCacheBuilder(RATE)
    builder.add_samples(samples)
    return builder.snapshot()


# -- reading the audio ----------------------------------------------------

def test_a_loud_beat_reads_high_and_silence_reads_low() -> None:
    """The whole point: a hit at 1.0 comes back near 1, a silent stretch
    comes back at 0."""
    cache = _cache(4.0, bursts=[(1.0, 0.1, 1.0), (2.0, 0.1, 0.2)])
    loud, quiet, silent = trigger_intensities(cache, [1.0, 2.0, 3.0])
    assert loud == pytest.approx(1.0, abs=0.05)
    assert quiet == pytest.approx(0.2, abs=0.05)
    assert silent == 0.0
    assert loud > quiet > silent


def test_one_outlier_does_not_flatten_everything_else() -> None:
    """The reference is a percentile, not the maximum. A single stray
    transient three times louder than the music must not push every
    real note down to nothing."""
    music = [(t / 2.0, 0.2, 0.3) for t in range(2, 20)]
    steady = _cache(12.0, bursts=music)
    with_outlier = _cache(12.0, bursts=[*music, (11.0, 0.02, 1.0)])

    before = trigger_intensities(steady, [1.0, 2.0, 3.0])
    after = trigger_intensities(with_outlier, [1.0, 2.0, 3.0])
    for was, now in zip(before, after):
        assert now == pytest.approx(was, abs=0.05)
    assert min(after) > 0.5


def test_silence_does_not_drag_the_reference_down() -> None:
    """Only bins that carry sound count toward the reference, so a long
    silent tail cannot make quiet music read as loud."""
    short = _cache(3.0, bursts=[(1.0, 0.1, 0.5)])
    padded = _cache(60.0, bursts=[(1.0, 0.1, 0.5)])
    assert peak_reference(padded) == pytest.approx(peak_reference(short),
                                                   rel=1e-6)


def test_the_window_leans_forward_onto_the_attack() -> None:
    """A hit landing just after the trigger is caught; one well before
    it is not. That is what makes the reading follow the note being
    played rather than the one before it."""
    cache = _cache(4.0, bursts=[(1.0, 0.02, 1.0)])
    just_after, = trigger_intensities(cache, [1.0 - 0.05])   # hit +50 ms
    long_before, = trigger_intensities(cache, [1.0 + 0.4])   # hit -400 ms
    assert just_after > 0.9
    assert long_before == 0.0


def test_times_outside_the_recording_read_zero() -> None:
    cache = _cache(2.0, bursts=[(0.5, 0.5, 1.0)])
    assert trigger_intensities(cache, [-5.0, 99.0]) == (0.0, 0.0)


def test_a_silent_file_has_no_loudness_information() -> None:
    """Nothing to divide by: every reading is 0 rather than a crash or
    an arbitrary 1."""
    silent = _cache(2.0)
    assert peak_reference(silent) == 0.0
    assert trigger_intensities(silent, [0.5, 1.0]) == (0.0, 0.0)
    empty = PeakCacheBuilder(RATE).snapshot()
    assert peak_reference(empty) == 0.0
    assert trigger_intensities(empty, [0.5]) == (0.0,)


# -- reading a whole note's worth of audio ---------------------------------

def test_a_window_reads_the_average_over_its_whole_length() -> None:
    """Half the window at full amplitude and half silent: the energy
    average is sqrt(0.5) of the loud part, not the loud part itself."""
    cache = _cache(4.0, bursts=[(1.0, 1.0, 1.0)])
    reference = peak_reference(cache)
    assert reference == pytest.approx(1.0, abs=0.01)   # the sound is at 1.0
    half, = window_intensities(cache, [(1.0, 3.0)])
    assert half == pytest.approx(np.sqrt(0.5), abs=0.01)
    whole, = window_intensities(cache, [(1.0, 2.0)])
    assert whole == pytest.approx(1.0, abs=0.01)


def test_a_short_note_and_a_long_one_on_the_same_beat_differ() -> None:
    """The feature. Both start together on a beat that is loud for a
    moment and quiet after; the short one reads the loud part alone, the
    long one averages the quiet in."""
    cache = _cache(6.0, bursts=[(1.0, 0.25, 1.0), (1.25, 2.75, 0.1)])
    short, long = window_intensities(cache, [(1.0, 1.25), (1.0, 4.0)])
    assert short > long
    assert short == pytest.approx(1.0, abs=0.05)
    assert long == pytest.approx(0.33, abs=0.05)   # mostly the quiet tail


def test_a_window_with_no_duration_falls_back_to_the_attack() -> None:
    """Dynamics, texts and chord symbols carry no notated length, so
    they read exactly what they always did."""
    cache = _cache(4.0, bursts=[(1.0, 0.1, 1.0), (2.0, 0.1, 0.3)])
    times = [1.0, 2.0, 3.0]
    assert window_intensities(cache, [(t, t) for t in times]) \
        == trigger_intensities(cache, times)
    # an end BEFORE the start is the same thing, not a negative window
    assert window_intensities(cache, [(1.0, 0.5)]) \
        == trigger_intensities(cache, [1.0])


def test_an_average_never_reads_louder_than_the_attack() -> None:
    """Why the effect may feel gentler than it did: against the same
    reference, an average over a note can only be at or below the peak
    at its start."""
    cache = _cache(8.0, bursts=[(t / 2.0, 0.15, 0.2 + t / 20.0)
                                for t in range(2, 15)])
    starts = [1.0, 2.0, 3.0, 4.0, 5.0]
    peaks = trigger_intensities(cache, starts)
    averages = window_intensities(cache, [(t, t + 0.5) for t in starts])
    assert all(a <= p + 1e-6 for a, p in zip(averages, peaks))
    assert max(averages) < max(peaks)          # non-vacuity: it really moved


def test_a_window_clamps_to_what_the_recording_holds() -> None:
    """One starting before the file and one running past the decoded
    end both read the part that exists — the same answer as the window
    clipped to the recording by hand."""
    cache = _cache(2.0, bursts=[(0.0, 2.0, 0.5)])
    early, = window_intensities(cache, [(-3.0, 1.0)])
    late, = window_intensities(cache, [(1.0, 90.0)])
    clipped_early, clipped_late = window_intensities(cache,
                                                     [(0.0, 1.0), (1.0, 2.0)])
    assert early == pytest.approx(clipped_early, abs=0.01)
    assert late == pytest.approx(clipped_late, abs=0.01)


def test_a_window_outside_the_recording_reads_zero() -> None:
    cache = _cache(2.0, bursts=[(0.5, 0.5, 1.0)])
    assert window_intensities(cache, [(-9.0, -5.0), (50.0, 60.0)]) \
        == (0.0, 0.0)


def test_a_window_shorter_than_one_bin_reads_the_bin_under_it() -> None:
    """A grace note can be shorter than the ~11.6 ms the cache resolves.
    It still gets a reading rather than a zero."""
    cache = _cache(3.0, bursts=[(1.0, 0.5, 1.0)])
    tiny, = window_intensities(cache, [(1.2, 1.2 + BIN_S / 4)])
    assert tiny == pytest.approx(1.0, abs=0.05)


def test_a_silent_file_gives_no_window_any_loudness() -> None:
    assert window_intensities(_cache(2.0), [(0.5, 1.5)]) == (0.0,)
    empty = PeakCacheBuilder(RATE).snapshot()
    assert window_intensities(empty, [(0.5, 1.5)]) == (0.0,)


# -- reading one moment ----------------------------------------------------

def _smooth_bin_s(cache) -> float:
    """Seconds per bin at the level the live reading actually uses."""
    level = _smoothing_level(cache)
    assert level is not None
    return level.samples_per_bin / RATE


def test_the_live_reading_comes_off_the_ninety_millisecond_level() -> None:
    """At 44.1 kHz the pyramid is 11.6, 23.2, 46.4, 92.9 ms ... so the
    reading is taken four levels up, not at the finest one."""
    cache = _cache(4.0, bursts=[(1.0, 1.0, 1.0)])
    assert _smooth_bin_s(cache) == pytest.approx(0.0929, abs=0.001)
    assert abs(_smooth_bin_s(cache) - SMOOTHING_S) < 0.005


def test_it_interpolates_between_neighbouring_bins() -> None:
    """A step from silence to full sound: on a bin's centre the reading
    is that bin's own value, and between two centres it is part-way
    between them, climbing all the way."""
    step_s = 2.0
    cache = _cache(4.0, bursts=[(step_s, 2.0, 1.0)])
    reference = peak_reference(cache)
    bin_s = _smooth_bin_s(cache)
    level = _smoothing_level(cache)
    # the first bin lying wholly inside the sound, and the one before it
    inside = int(np.ceil(step_s / bin_s)) + 1
    quiet, loud = inside - 3, inside
    at_quiet = intensity_at(cache, (quiet + 0.5) * bin_s)
    at_loud = intensity_at(cache, (loud + 0.5) * bin_s)
    assert at_quiet == pytest.approx(float(level.rms[quiet]) / reference,
                                     abs=1e-6)
    assert at_loud == pytest.approx(float(level.rms[loud]) / reference,
                                    abs=1e-6)
    assert at_quiet == pytest.approx(0.0, abs=0.01)
    assert at_loud == pytest.approx(1.0, abs=0.01)
    # halfway between two centres is halfway between two values
    a, b = loud - 1, loud
    half = intensity_at(cache, (a + 1.0) * bin_s)
    assert half == pytest.approx(
        (float(level.rms[a]) + float(level.rms[b])) / 2 / reference,
        abs=1e-6)
    # and the whole ramp climbs, with no step back
    walk = [intensity_at(cache, (quiet + 0.5) * bin_s + k * bin_s / 8)
            for k in range(8 * 3 + 1)]
    assert all(b >= a - 1e-9 for a, b in zip(walk, walk[1:]))
    assert walk[0] < walk[-1]


def test_it_reads_nothing_outside_the_recording() -> None:
    cache = _cache(2.0, bursts=[(0.0, 2.0, 1.0)])
    assert intensity_at(cache, -0.001) == 0.0
    assert intensity_at(cache, -5.0) == 0.0
    assert intensity_at(cache, float("-inf")) == 0.0    # the pre-roll time
    assert intensity_at(cache, 2.5) == 0.0
    assert intensity_at(cache, 1.0) > 0.5               # not vacuous
    assert intensity_at(PeakCacheBuilder(RATE).snapshot(), 0.5) == 0.0
    assert intensity_at(_cache(2.0), 1.0) == 0.0        # silent file


def test_the_reading_is_smoothed_so_the_ink_cannot_flicker() -> None:
    """One loud bin's worth of sound between quiet ones. The attack
    reading takes it at face value; the live reading averages it down
    over ~90 ms, which is what stops a tremolo shaking the note.

    Four seconds of real playing first, so the reference is the music's
    own loudness and not the spike's."""
    spike_s = 5.0
    cache = _cache(6.0, bursts=[(0.0, 4.0, 1.0),        # the music
                                (4.0, 2.0, 0.05),       # a quiet stretch
                                (spike_s, BIN_S, 1.0)])  # one loud bin
    assert peak_reference(cache) == pytest.approx(1.0, abs=0.05)
    attack, = trigger_intensities(cache, [spike_s])
    live = intensity_at(cache, spike_s + BIN_S / 2)
    assert attack > 0.8                   # the spike, near enough at face value
    assert live < attack / 2
    # it still moves: the spike reads clearly above the quiet either side
    assert live > intensity_at(cache, spike_s - 0.5) + 0.1


def test_the_reference_may_be_handed_in_and_never_changes_the_answer():
    """The applier works the reference out once and passes it every
    frame; that must be a speed-up and nothing else."""
    cache = _cache(4.0, bursts=[(1.0, 0.5, 1.0), (2.0, 0.5, 0.3)])
    reference = peak_reference(cache)
    for t in (0.0, 0.5, 1.2, 2.2, 3.9):
        assert intensity_at(cache, t, reference) == intensity_at(cache, t)


def test_window_gains_skip_when_there_is_nothing_to_do() -> None:
    """The same None contract as the per-trigger gains."""
    cache = _cache(2.0, bursts=[(0.5, 0.5, 1.0)])
    on = VolumeResponse(amount=1.0)
    assert window_gains(None, [(0.5, 1.0)], on) is None
    assert window_gains(cache, [(0.5, 1.0)], VolumeResponse()) is None
    assert window_gains(cache, [], on) is None
    gains = window_gains(cache, [(0.5, 1.0), (1.5, 2.0)], on)
    assert gains is not None and len(gains) == 2
    assert gains[0] > gains[1]            # loud window, then the silence


# -- the gain -------------------------------------------------------------

def test_the_endpoints_are_the_settings() -> None:
    vol = VolumeResponse(amount=1.0, quiet=0.5, loud=1.5)
    assert gain_for(0.0, vol) == pytest.approx(0.5)
    assert gain_for(1.0, vol) == pytest.approx(1.5)
    assert gain_for(0.5, vol) == pytest.approx(1.0)


def test_amount_zero_is_exactly_one_everywhere() -> None:
    """Not "close to 1" — exactly 1, at every intensity and whatever the
    other two settings say. That is what keeps the old look intact."""
    vol = VolumeResponse(amount=0.0, quiet=0.1, loud=4.0)
    for intensity in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert gain_for(intensity, vol) == 1.0


def test_amount_mixes_toward_the_full_range() -> None:
    """Half the amount is half the departure from 1."""
    vol = VolumeResponse(amount=0.5, quiet=0.5, loud=1.5)
    assert gain_for(0.0, vol) == pytest.approx(0.75)
    assert gain_for(1.0, vol) == pytest.approx(1.25)


def test_gains_come_back_one_per_window_in_order() -> None:
    cache = _cache(4.0, bursts=[(1.0, 0.1, 1.0), (2.0, 0.1, 0.15)])
    gains = window_gains(cache, [(1.0, 1.1), (2.0, 2.1), (3.0, 3.1)],
                         VolumeResponse(amount=1.0, quiet=0.5, loud=1.5))
    assert gains is not None and len(gains) == 3
    assert gains[0] > gains[1] > gains[2]
    assert gains[2] == pytest.approx(0.5)      # silence: the quiet end


# -- reading the document -------------------------------------------------

def test_an_empty_entry_is_the_defaults_and_is_off() -> None:
    assert read_volume({}) == VolumeResponse()
    assert read_volume(None).is_off
    assert read_volume({}).quiet == DEFAULT_QUIET
    assert read_volume({}).loud == DEFAULT_LOUD


def test_values_are_clamped_at_consumption() -> None:
    """A hand-edited file cannot produce a broken animation — the
    command that writes these only checks they are finite numbers."""
    vol = read_volume({"amount": 9.0, "quiet": -3.0, "loud": 500.0})
    assert vol.amount == 1.0
    assert vol.quiet == 0.0
    assert vol.loud == 5.0


def test_keys_this_build_does_not_know_are_ignored() -> None:
    vol = read_volume({"amount": 0.5, "curve": "perceptual"})
    assert vol == VolumeResponse(amount=0.5, quiet=DEFAULT_QUIET,
                                 loud=DEFAULT_LOUD)
