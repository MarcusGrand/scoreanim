"""The system pulse values: what the document says, and what size they
make a system.

Pure — no scene, no Qt. The reading the follow half multiplies
(`intensity_at`) has its own tests in test_intensity.py; what is pinned
here is the knobs, their clamps, the onset bumps (how heads are counted
and what shape a bump takes), and the exactly-1.0 guarantee the render
side leans on to decide it may skip the systems entirely.
"""

import pytest

from scoreanim.core.animation.pulse import (DEFAULT_AMOUNT,
                                            DEFAULT_NOTES_FOR_FULL,
                                            DEFAULT_POP_AMOUNT,
                                            DEFAULT_SETTLE_S, SystemBumps,
                                            SystemPulse, build_bumps, pop_at,
                                            pulse_scale, read_pulse)
from scoreanim.core.animation.scale_groups import HEAD_KINDS
from scoreanim.core.animation.schedule import build_trigger_schedule
from scoreanim.core.score.identity import ElementKind

# The whole page at once, so a bump's arithmetic reads off the numbers.
POP = SystemPulse(pop_amount=0.1, notes_for_full=4, settle=0.25)


def _rows(*rows):
    """(kind, system) rows, written as the short strings a test can read:
    "N1" is a notehead on system 1, "S2" a stem on system 2."""
    kinds = {"N": ElementKind.NOTEHEAD, "S": ElementKind.STEM,
             "D": ElementKind.OTHER, "B": ElementKind.BEAM,
             "/": ElementKind.SLASH, "R": ElementKind.REST}
    return [[(kinds[item[0]], int(item[1:])) for item in row] for row in rows]


# -- reading the document ------------------------------------------------


def test_an_empty_document_is_off() -> None:
    for raw in (None, {}):
        pulse = read_pulse(raw)
        assert pulse.amount == DEFAULT_AMOUNT == 0.0
        assert pulse.pop_amount == DEFAULT_POP_AMOUNT == 0.0
        assert pulse.is_off
        # the shape settings still read as their defaults, so a document
        # that only ever set the amount pops the way the panel shows
        assert pulse.notes_for_full == DEFAULT_NOTES_FOR_FULL == 6
        assert pulse.settle == DEFAULT_SETTLE_S == 0.25


def test_either_amount_alone_turns_it_on() -> None:
    assert not read_pulse({"amount": 0.05}).is_off
    assert not read_pulse({"pop_amount": 0.05}).is_off
    assert read_pulse({"amount": 0.05}).follows_volume
    assert not read_pulse({"amount": 0.05}).pops_on_onsets
    assert read_pulse({"pop_amount": 0.05}).pops_on_onsets
    assert not read_pulse({"pop_amount": 0.05}).follows_volume


def test_the_pop_settings_are_clamped_at_both_ends() -> None:
    """Same as the amount: the range is enforced at consumption, so a
    hand-edited file cannot make the page jump."""
    assert read_pulse({"pop_amount": -1.0}).pop_amount == 0.0
    assert read_pulse({"pop_amount": 3.0}).pop_amount == 0.2
    assert read_pulse({"notes_for_full": 0}).notes_for_full == 1
    assert read_pulse({"notes_for_full": 99}).notes_for_full == 24
    assert read_pulse({"notes_for_full": 6.7}).notes_for_full == 6
    assert read_pulse({"settle": 0.0}).settle == 0.01     # never a divide by 0
    assert read_pulse({"settle": -5.0}).settle == 0.01


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


# -- counting the heads on a beat ----------------------------------------


def test_a_chord_counts_every_head_and_its_ink_counts_for_nothing() -> None:
    """Two heads in one voice are two heads; the stem, dot and beam that
    hang off them are already-counted ink and must not add weight."""
    plain = build_bumps([0.0], _rows(["N1", "S1"]), POP)
    chord = build_bumps([0.0], _rows(["N1", "N1", "S1", "D1", "B1"]), POP)

    assert plain[1].strengths == (0.25,)             # 1 of 4
    assert chord[1].strengths == (0.5,)              # 2 of 4, ink ignored


def test_ink_with_no_head_on_the_beat_makes_no_bump_at_all() -> None:
    """A bar of rests is not an onset: nothing lands, so nothing jumps."""
    assert build_bumps([0.0], _rows(["R1", "R1", "D1"]), POP) == {}


def test_a_slash_counts_as_the_head_it_stands_in_for() -> None:
    """A slash region draws slashes instead of noteheads (rule 10), so
    they are what lands on the beat."""
    assert build_bumps([0.0], _rows(["/1", "/1"]), POP)[1].strengths == (0.5,)


def test_each_head_counts_in_the_system_it_actually_sits_in() -> None:
    """One beat's ink can straddle a system break, and the trigger's own
    system is a single min() hint — so the count follows each element,
    the reveal-grouping precedent."""
    bumps = build_bumps([2.0], _rows(["N1", "N2", "N2", "S2"]), POP)

    assert set(bumps) == {1, 2}
    assert bumps[1].strengths == (0.25,)             # 1 head
    assert bumps[2].strengths == (0.5,)              # 2 heads
    assert bumps[1].seconds == bumps[2].seconds == (2.0,)


def test_an_element_with_no_system_is_left_out() -> None:
    """Page furniture carries no system, so there is no group to bump."""
    rows = [[(ElementKind.NOTEHEAD, None), (ElementKind.NOTEHEAD, 1)]]
    assert build_bumps([0.0], rows, POP)[1].strengths == (0.25,)


def test_strength_caps_at_notes_for_full() -> None:
    """Past the ceiling a beat is as strong as a beat can be — a denser
    chord cannot push the system further."""
    row = ["N1"] * 4
    assert build_bumps([0.0], _rows(row), POP)[1].strengths == (1.0,)
    assert build_bumps([0.0], _rows(row * 3), POP)[1].strengths == (1.0,)


def test_notes_for_full_moves_what_counts_as_a_full_beat() -> None:
    row = _rows(["N1"] * 3)
    assert build_bumps([0.0], row,
                       SystemPulse(pop_amount=0.1,
                                   notes_for_full=3))[1].strengths == (1.0,)
    assert build_bumps([0.0], row,
                       SystemPulse(pop_amount=0.1,
                                   notes_for_full=12))[1].strengths == (0.25,)


def test_a_systems_bumps_come_out_in_time_order() -> None:
    """What makes the bisect in pop_at legitimate."""
    bumps = build_bumps([0.0, 1.0, 2.5],
                        _rows(["N1"], ["N1", "N1"], ["N1"]), POP)
    assert bumps[1].seconds == (0.0, 1.0, 2.5)
    assert bumps[1].strengths == (0.25, 0.5, 0.25)


def test_the_amount_is_not_folded_into_a_strength() -> None:
    """Turning the knob must not need the lists rebuilt — only the
    settings the strengths are measured against do."""
    row = _rows(["N1", "N1"])
    assert build_bumps([0.0], row, SystemPulse(pop_amount=0.02,
                                               notes_for_full=4)) \
        == build_bumps([0.0], row, SystemPulse(pop_amount=0.2,
                                               notes_for_full=4))


# -- the shape of a bump -------------------------------------------------


def _one(strength: float = 1.0, at: float = 0.0) -> SystemBumps:
    return SystemBumps((at,), (strength,))


def test_a_bump_is_at_its_biggest_the_moment_it_fires() -> None:
    """Straight up, like a note pop: the peak is AT the trigger, not
    eased into."""
    peak = pop_at(_one(), 0.0, POP)
    assert peak == pytest.approx(0.1)                # the whole amount
    for t in (0.001, 0.05, 0.2):
        assert pop_at(_one(), t, POP) < peak


def test_a_bump_falls_the_whole_way_down() -> None:
    values = [pop_at(_one(), i * 0.01, POP) for i in range(26)]
    assert values == sorted(values, reverse=True)
    assert len(set(values)) == len(values)           # strictly, no plateau


def test_a_bump_is_gone_at_the_settle_and_stays_gone() -> None:
    """Exactly 0, not nearly — that is what lets a resting system sit at
    exactly its engraved size."""
    for t in (0.25, 0.2500001, 1.0, 60.0):
        assert pop_at(_one(), t, POP) == 0.0


def test_nothing_has_happened_yet_before_the_bump() -> None:
    for t in (-5.0, -0.001):
        assert pop_at(_one(), t, POP) == 0.0


def test_a_weaker_beat_makes_a_smaller_bump_the_whole_way_down() -> None:
    for t in (0.0, 0.1, 0.2):
        assert pop_at(_one(0.5), t, POP) == \
            pytest.approx(pop_at(_one(1.0), t, POP) / 2.0)


def test_overlapping_bumps_take_the_largest_and_never_the_sum() -> None:
    """A fast run must not inflate a system absurdly: the bumps do not
    stack, the biggest live one wins."""
    run = SystemBumps((0.0, 0.05, 0.1), (1.0, 1.0, 1.0))
    t = 0.12
    each = [1.0 * (1.0 - (t - s) / 0.25) * 0.1 for s in run.seconds]

    assert pop_at(run, t, POP) == pytest.approx(max(each))
    assert pop_at(run, t, POP) < sum(each)           # non-vacuity


def test_an_older_stronger_bump_can_still_beat_a_fresh_weak_one() -> None:
    """"Largest live", not "most recent" — a tutti chord keeps the
    system up while a passing grace note ticks under it."""
    both = SystemBumps((0.0, 0.2), (1.0, 0.1))
    assert pop_at(both, 0.2, POP) == pytest.approx(pop_at(_one(1.0), 0.2, POP))


def test_a_system_with_no_bumps_never_pops() -> None:
    assert pop_at(None, 3.0, POP) == 0.0
    assert pop_at(SystemBumps(), 3.0, POP) == 0.0


def test_pop_amount_zero_is_exactly_nothing() -> None:
    off = SystemPulse(amount=0.1, pop_amount=0.0)
    assert pop_at(_one(), 0.0, off) == 0.0


# -- the two halves together ---------------------------------------------


def test_the_two_deviations_add() -> None:
    pulse = SystemPulse(amount=0.1, pop_amount=0.05)
    assert pulse_scale(1.0, pulse, 0.05) == pytest.approx(1.15)
    assert pulse_scale(0.0, pulse, 0.05) == pytest.approx(1.05)
    assert pulse_scale(1.0, pulse, 0.0) == pytest.approx(1.1)


def test_a_pop_alone_needs_no_loudness_at_all() -> None:
    """The mode's whole point: it works with no recording loaded, where
    the reading is 0."""
    pop_only = SystemPulse(amount=0.0, pop_amount=0.1)
    assert pulse_scale(0.0, pop_only, 0.1) == pytest.approx(1.1)


def test_with_both_off_it_is_exactly_one_whatever_is_passed() -> None:
    off = SystemPulse()
    assert pulse_scale(1.0, off, 0.5) == 1.0


# -- on a real score -----------------------------------------------------


def test_counting_heads_on_a_real_schedule(engraved, join_mapping,
                                           score_model) -> None:
    """The fixture's own beats, counted the way the applier counts them:
    every element that fires, in the system it is drawn in."""
    schedule = build_trigger_schedule(engraved.layout, join_mapping,
                                      score_model.measures)
    system_of = {el.identity.element_id: el.system for el in
                 engraved.layout.elements}
    kind_of = {el.identity.element_id: el.identity.kind for el in
               engraved.layout.elements}
    rows = [[(kind_of.get(eid), system_of.get(eid)) for eid in trig.element_ids]
            for trig in schedule.triggers]
    seconds = [float(i) for i in range(len(rows))]   # one beat, one second
    pulse = SystemPulse(pop_amount=0.1, notes_for_full=4)

    bumps = build_bumps(seconds, rows, pulse)

    assert len(bumps) > 1                            # several systems bump
    # every bump lands on a beat that really does carry heads there
    # (the fixture has slash regions, and a slash is a head — see
    # test_a_slash_counts_as_the_head_it_stands_in_for)
    for system, entry in bumps.items():
        for t, strength in zip(entry.seconds, entry.strengths):
            heads = sum(1 for kind, sys in rows[int(t)]
                        if sys == system and kind in HEAD_KINDS)
            assert heads > 0
            assert strength == pytest.approx(min(1.0, heads / 4))
    # non-vacuity: the fixture has beats far heavier than one head, and
    # the ink hanging off them (stems, dots, beams) outnumbers the heads
    assert max(max(e.strengths) for e in bumps.values()) == 1.0
    assert min(min(e.strengths) for e in bumps.values()) == 0.25
    heads = sum(1 for row in rows for kind, _ in row if kind in HEAD_KINDS)
    assert sum(len(row) for row in rows) > 2 * heads
