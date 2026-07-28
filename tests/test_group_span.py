"""Which staves a group symbol spans (core/engraving/verovio/group_span.py).

Pure geometry, so it is pinned here on synthetic staff-center maps rather
than through a Verovio load — the adapter-level companion is
test_adapter_groups.test_group_survives_hidden_interior_staves.

The regression these guard (2026-07-29): contiguity used to be measured
against the integers between the span's ends, so a strings bracket over a
system where Violin II and Viola are hidden (rule 7(b)) covered staves
[7, 10], failed the check, and raised mid-load. Because the re-engrave
was unguarded, the user saw no bracket and no error.
"""

import pytest

from scoreanim.core.engraving.types import Rect
from scoreanim.core.engraving.verovio.group_span import covered_staves

# a 13-staff system, staff n centered at n * 100
FULL = {n: n * 100.0 for n in range(1, 14)}
# the same system with Violin II (8) and Viola (9) empty and hidden, and
# the winds/brass thinned out — brackets.musicxml's system 2
HIDDEN = {n: n * 100.0 for n in (3, 7, 10, 12, 13)}


def _spanning(top: float, bottom: float) -> Rect:
    return Rect(x=0.0, y=top, w=10.0, h=bottom - top)


def test_spans_every_staff_when_none_are_hidden() -> None:
    assert covered_staves(FULL, _spanning(650, 1150)) == [7, 8, 9, 10, 11]


def test_spans_the_visible_staves_across_a_hidden_gap() -> None:
    # the Violin I .. Double Bass bracket on a system where only staves
    # 7 and 10 of its span are drawn: well-formed, not corrupt
    assert covered_staves(HIDDEN, _spanning(650, 1150)) == [7, 10]


def test_a_span_ending_at_a_hidden_staff_names_the_last_visible_one() -> None:
    # Double Bass (11) hidden: the bracket stops at the Cello staff
    assert covered_staves({n: n * 100.0 for n in (7, 8, 9, 10, 12)},
                          _spanning(650, 1150)) == [7, 8, 9, 10]


def test_single_staff_span_is_legal() -> None:
    assert covered_staves(HIDDEN, _spanning(650, 750)) == [7]


def test_skipping_a_visible_staff_still_raises() -> None:
    # staff 8 is drawn on this system but sits outside the span — staff
    # numbers out of y order, which is a torn span, not hiding
    torn = {7: 700.0, 8: 5000.0, 9: 900.0}
    with pytest.raises(ValueError, match="contiguous run"):
        covered_staves(torn, _spanning(650, 950))


def test_covering_no_staff_raises() -> None:
    with pytest.raises(ValueError, match="spans no staff"):
        covered_staves(FULL, _spanning(10, 20))
