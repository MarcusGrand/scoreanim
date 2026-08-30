"""Where each beat sits on the page, read off the staves Verovio drew.

Verovio spaces a measure by duration, not evenly, and at a system start
the measure opens with a clef/key/time prefix that holds no beats. So
anything we synthesize ourselves (rule 10's slashes) has to be placed on
the columns the real ink already stands on, not spread across the bar.

A column is one (onset, x) pair for a measure: the x every staff's ink
at that beat is aligned to. It comes from the noteheads and ordinary
rests Verovio laid out, on ANY part or staff, using each element's bbox
left edge — that is the alignment point for both glyph families (they
agree to 0.1 unit in testscore). Two things are deliberately left out:

- grace notes, which carry the main note's onset but are drawn well to
  its left (up to 53 units in complex1) — they would drag the column off
  the beat;
- mRest, which is centred in the bar rather than placed on beat 1.

Inputs: the accumulator list + _LoadState. Outputs: plain data. Nothing
is written back — no state, no accumulator touched.
"""

from __future__ import annotations

from scoreanim.core.animation.schedule import quantize_beats
from scoreanim.core.engraving.verovio.decompose import _ElementAccumulator
from scoreanim.core.engraving.verovio.records import _LoadState
from scoreanim.core.score.identity import Beats

# Classes that stand on a beat. mRest is excluded on purpose (centred in
# the bar); multiRest likewise spans bars and stands on none of them.
_COLUMN_CLASSES = frozenset({"note", "rest"})

# (page, measure) → columns, ascending by onset
BeatColumns = dict[tuple[int, int], tuple[tuple[Beats, float], ...]]


def build_beat_columns(
        accumulators: list[tuple[int, _ElementAccumulator]],
        st: _LoadState) -> BeatColumns:
    """The beat columns of every measure on every page.

    Where several elements share one beat, the smallest left edge wins:
    a chord second is displaced a notehead-width to the right, so the
    minimum is the one on the alignment.
    """
    # (page, measure) → quantized onset → (onset, x)
    slots: dict[tuple[int, int], dict[int, tuple[Beats, float]]] = {}
    # (page, measure) → right edge of the widest staff drawn in it
    staff_right: dict[tuple[int, int], float] = {}

    for page, acc in accumulators:
        if acc.measure is None or acc.bbox is None:
            continue
        key = (page, acc.measure)
        if acc.svg_class == "staff":
            if acc.bbox.x2 > staff_right.get(key, float("-inf")):
                staff_right[key] = acc.bbox.x2
            continue
        if acc.svg_class not in _COLUMN_CLASSES:
            continue
        note = st.mei.notes.get(acc.verovio_id)
        if note is not None and note.grace:
            continue
        onset = st.onset_by_id.get(acc.verovio_id)
        if onset is None:
            continue
        _keep_leftmost(slots.setdefault(key, {}), onset, acc.bbox.x)

    # The end of the measure is a column too — the barline the last beat
    # is spaced against. Only where some ink already anchors the bar: a
    # measure with no columns at all has to fall back to even spacing,
    # and one lone end column would hide that.
    for key, slot in slots.items():
        start = st.measure_start.get(key[1])
        duration = st.measure_duration.get(key[1])
        right = staff_right.get(key)
        if start is None or duration is None or right is None:
            continue
        _keep_leftmost(slot, start + duration, right)

    return {key: tuple(sorted(slot.values()))
            for key, slot in slots.items()}


def _keep_leftmost(slot: dict[int, tuple[Beats, float]],
                   onset: Beats, x: float) -> None:
    q = quantize_beats(onset)
    seen = slot.get(q)
    if seen is None or x < seen[1]:
        slot[q] = (onset, x)


def x_for_onset(columns: tuple[tuple[Beats, float], ...],
                onset: Beats, guess: float) -> float:
    """The x a beat sits on, in the same left-edge terms the columns use.

    An exact column wins. Between two columns the x is interpolated
    straight, which is close enough — Verovio's spacing is near linear
    over a single beat. Off the ends we lean on ``guess``, the caller's
    even-spacing fallback: with no column at all it IS the answer, and
    with no column to the left (a bar whose first event is not on beat 1
    in any staff) it is used but never allowed past the first real
    column.
    """
    if not columns:
        return guess
    q = quantize_beats(onset)
    left: tuple[Beats, float] | None = None
    right: tuple[Beats, float] | None = None
    for column in columns:
        cq = quantize_beats(column[0])
        if cq == q:
            return column[1]
        if cq < q:
            left = column
        else:
            right = column
            break
    if left is None:
        return min(guess, right[1]) if right is not None else guess
    if right is None:
        return guess
    span = right[0] - left[0]
    if span <= 0:
        return left[1]
    return left[1] + (onset - left[0]) / span * (right[1] - left[1])
