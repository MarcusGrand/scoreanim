"""Beat columns: where each beat sits on the page (2026-08-31).

Hand-built accumulators, so the rules are pinned on their own rather
than on whatever a fixture happens to draw: columns come out sorted, two
elements on one beat collapse to the leftmost, mRest is ignored, a grace
note never steals the beat, and the measure's end is a column too.
"""

import pytest

from scoreanim.core.engraving.types import Rect
from scoreanim.core.engraving.verovio.beat_columns import (build_beat_columns,
                                                           x_for_onset)
from scoreanim.core.engraving.verovio.decompose import _ElementAccumulator
from scoreanim.core.engraving.verovio.mei_index import _MeiIndex, _MeiNote
from scoreanim.core.engraving.verovio.records import _LoadState
from scoreanim.core.score.identity import ElementKind


def _acc(vid: str, svg_class: str, measure: int | None, x: float,
         w: float = 20.0) -> _ElementAccumulator:
    acc = _ElementAccumulator(verovio_id=vid, svg_class=svg_class,
                              kind=ElementKind.OTHER, measure=measure,
                              staff=1, layer=1, owner_onset=None)
    acc.bbox = Rect(x, 100.0, w, 20.0)
    return acc


def _state(onsets: dict[str, float],
           notes: dict[str, _MeiNote] | None = None) -> _LoadState:
    return _LoadState(prep=None, mei=_MeiIndex(notes=notes or {}),
                      onset_by_id=onsets,
                      measure_start={1: 0.0}, measure_duration={1: 4.0},
                      staff_n_by_id={}, layer_n_by_id={})


def _grace(grace: bool) -> _MeiNote:
    return _MeiNote(measure=1, staff=1, layer=1, pname="c", alter=0.0,
                    octave=4, loc=None, grace=grace, chord_id=None)


def test_columns_come_out_sorted_by_onset():
    accs = [(1, _acc("n3", "note", 1, 300.0)),
            (1, _acc("n1", "note", 1, 100.0)),
            (1, _acc("n2", "note", 1, 200.0))]
    st = _state({"n1": 0.0, "n2": 1.0, "n3": 2.0})
    columns = build_beat_columns(accs, st)[(1, 1)]
    assert [c[0] for c in columns] == sorted(c[0] for c in columns)
    assert columns[:3] == ((0.0, 100.0), (1.0, 200.0), (2.0, 300.0))


def test_two_elements_on_one_beat_collapse_to_the_leftmost():
    """A chord second is displaced a notehead-width right; the alignment
    is the smaller left edge."""
    accs = [(1, _acc("n1", "note", 1, 220.0)),
            (1, _acc("n2", "note", 1, 200.0)),
            (1, _acc("r1", "rest", 1, 210.0))]
    st = _state({"n1": 1.0, "n2": 1.0, "r1": 1.0})
    columns = build_beat_columns(accs, st)[(1, 1)]
    assert (1.0, 200.0) in columns
    assert len([c for c in columns if c[0] == 1.0]) == 1


def test_rests_make_columns_but_mrest_does_not():
    accs = [(1, _acc("r1", "rest", 1, 150.0)),
            (1, _acc("mr1", "mRest", 1, 400.0))]
    st = _state({"r1": 1.0, "mr1": 0.0})
    columns = build_beat_columns(accs, st)[(1, 1)]
    assert (1.0, 150.0) in columns
    assert not [c for c in columns if c[1] == 400.0]


def test_a_grace_note_never_takes_the_beat():
    """A grace carries the main note's onset but is drawn to its left —
    letting it in would drag the column off the beat (complex1)."""
    accs = [(1, _acc("g1", "note", 1, 160.0)),
            (1, _acc("n1", "note", 1, 200.0))]
    st = _state({"g1": 1.0, "n1": 1.0},
                notes={"g1": _grace(True), "n1": _grace(False)})
    columns = build_beat_columns(accs, st)[(1, 1)]
    assert (1.0, 200.0) in columns


def test_the_measure_end_is_a_column():
    accs = [(1, _acc("n1", "note", 1, 100.0)),
            (1, _acc("s1", "staff", 1, 80.0, w=420.0))]
    st = _state({"n1": 0.0})
    columns = build_beat_columns(accs, st)[(1, 1)]
    assert columns[-1] == (4.0, 500.0)          # start 0 + duration 4


def test_a_measure_no_ink_anchors_has_no_columns():
    """Staff lines alone are not an anchor — a lone end column would hide
    the fact that nothing places the beats."""
    accs = [(1, _acc("s1", "staff", 1, 80.0, w=420.0)),
            (1, _acc("mr1", "mRest", 1, 250.0))]
    st = _state({"mr1": 0.0})
    assert build_beat_columns(accs, st) == {}


def test_pages_are_kept_apart():
    accs = [(1, _acc("n1", "note", 1, 100.0)),
            (2, _acc("n2", "note", 2, 900.0))]
    st = _state({"n1": 0.0, "n2": 4.0})
    columns = build_beat_columns(accs, st)
    assert set(columns) == {(1, 1), (2, 2)}


# --- x_for_onset -----------------------------------------------------------

COLUMNS = ((0.0, 100.0), (1.0, 200.0), (2.0, 260.0), (4.0, 500.0))


def test_an_exact_column_wins_over_the_guess():
    assert x_for_onset(COLUMNS, 2.0, guess=999.0) == 260.0


def test_a_beat_between_columns_is_interpolated():
    assert x_for_onset(COLUMNS, 3.0, guess=999.0) == pytest.approx(380.0)
    assert x_for_onset(COLUMNS, 1.5, guess=999.0) == pytest.approx(230.0)


def test_with_no_columns_the_guess_is_the_answer():
    assert x_for_onset((), 1.0, guess=42.0) == 42.0


def test_with_nothing_on_the_left_the_guess_stays_left_of_the_first_column():
    late = ((2.0, 260.0), (4.0, 500.0))
    assert x_for_onset(late, 0.0, guess=120.0) == 120.0
    assert x_for_onset(late, 0.0, guess=900.0) == 260.0
