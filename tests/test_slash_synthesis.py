"""PHASES 1.5 verification: synthesized slash elements for the drum part.

Fixture facts (verified against the raw MusicXML): three [start, stop)
regions — mm 3–9, 11–15, 16–17 — with quarter-note slash units; meters
inside the regions are 4/4 except m5 and m14 (2/4).
"""

from collections import Counter

import pytest

from scoreanim.core.score.identity import ElementKind

SLASH_MEASURES_44 = {3, 4, 6, 7, 8, 9, 11, 12, 13, 15, 16, 17}
SLASH_MEASURES_24 = {5, 14}


@pytest.fixture(scope="session")
def slashes(engraved):
    return [e for e in engraved.layout.elements
            if e.identity.kind is ElementKind.SLASH]


def test_slash_count_per_measure_follows_the_meter(slashes) -> None:
    def measure_of(e) -> int:
        return int(str(e.identity.element_id).split(":")[1].lstrip("m"))

    per_measure = Counter(measure_of(e) for e in slashes)
    expected = {**{m: 4 for m in SLASH_MEASURES_44},
                **{m: 2 for m in SLASH_MEASURES_24}}
    assert per_measure == expected
    assert len(slashes) == 12 * 4 + 2 * 2


def test_slash_onsets_fall_on_the_beats(slashes, score_model) -> None:
    for e in slashes:
        onset = e.identity.onset
        assert onset is not None
        assert onset == int(onset), e.identity.element_id     # whole beats
    # first slash of m3 starts exactly at the measure start
    m3 = score_model.measure(3)
    first_m3 = min((e.identity.onset for e in slashes
                    if str(e.identity.element_id).startswith("P7:m3:")))
    assert first_m3 == m3.start


def test_slashes_sit_inside_the_drum_staff(engraved, slashes) -> None:
    staff_lines = {
        e.identity.element_id: e
        for e in engraved.layout.elements
        if e.identity.kind is ElementKind.STAFF_LINES
        and e.identity.part == "P7"
    }
    assert staff_lines, "no drum staff lines decomposed"
    for slash in slashes:
        assert slash.identity.part == "P7"
        assert slash.identity.part_name == "Drum Set"
        # inside some drum staff bbox on the same page (small vertical
        # slack: the slash spans line 2 to line 4, so it fits strictly)
        host = [s for s in staff_lines.values()
                if s.page == slash.page and s.bbox.contains(slash.bbox, slack=1)]
        assert host, f"{slash.identity.element_id} outside every drum staff"


def test_slashes_animate_like_notes(slashes) -> None:
    """The animation layer keys on (identity, onset) — synthesized
    slashes must be indistinguishable from notes in that regard."""
    for e in slashes:
        assert e.identity.onset is not None
        assert e.glyph.paths
        assert e.anchor == e.bbox.center


def test_slashes_land_on_the_beat_columns_the_horns_stand_on(engraved,
                                                             slashes) -> None:
    """The bug (2026-08-31): slashes were spread evenly across the bar,
    so they drifted up to 95 units off the beats — the clef/key/time
    prefix at a system start holds no beats, and Verovio spaces by
    duration, not evenly. Beat 2 in the slash staff must sit at the same
    x as beat 2 everywhere else in the system.

    Compared against the SMALLEST notehead left edge on the beat: a
    chord second is displaced a notehead-width to the right, so the
    minimum is the one on the alignment.
    """
    graces = {n.element_id for n in engraved.note_records if n.grace}
    noteheads: dict[tuple[int, float], float] = {}
    for e in engraved.layout.elements:
        if (e.identity.kind is not ElementKind.NOTEHEAD
                or e.identity.onset is None
                or e.identity.element_id in graces):
            continue                        # a grace is drawn off the beat
        key = (e.page, round(e.identity.onset, 6))
        noteheads[key] = min(noteheads.get(key, e.bbox.x), e.bbox.x)

    checked = 0
    for slash in slashes:
        column = noteheads.get((slash.page, round(slash.identity.onset, 6)))
        if column is None:
            continue                        # no other staff plays this beat
        assert abs(slash.bbox.x - column) <= 2.0, (
            f"{slash.identity.element_id} at {slash.bbox.x:.1f} is off the "
            f"beat column {column:.1f}")
        checked += 1
    assert checked >= 30, f"only {checked} slashes shared a beat with a note"
