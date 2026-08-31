"""PHASES 1.5 verification: synthesized slash elements for the drum part.

Fixture facts (verified against the raw MusicXML): three [start, stop)
regions — mm 3–9, 11–15, 16–17 — with quarter-note slash units; meters
inside the regions are 4/4 except m5 and m14 (2/4).
"""

from collections import Counter, defaultdict

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


def test_a_slash_stands_exactly_where_verovio_put_its_note(engraved,
                                                          slashes) -> None:
    """Since 2026-08-31 we do not work out a slash's x at all: an
    invisible note per slash unit goes into the score, Verovio spaces
    it, and the slash stands on it. So the alignment against the other
    staves is not "close" — it is EXACT, and the tolerance here is a
    float epsilon rather than an engraving one.

    Compared against the notehead x MOST of the beat's noteheads share.
    Neither the smallest nor the largest would do: an interval of a
    second cannot be printed on one stem, so Verovio displaces one of
    the two a notehead-width off the alignment (testscore m3 beat 4 has
    a B4 sitting left of its own chord's C5). The alignment is where
    the rest of them are.
    """
    graces = {n.element_id for n in engraved.note_records if n.grace}
    columns: dict[tuple[int, float], Counter] = defaultdict(Counter)
    for e in engraved.layout.elements:
        if (e.identity.kind is not ElementKind.NOTEHEAD
                or e.identity.onset is None
                or e.identity.element_id in graces):
            continue                        # a grace is drawn off the beat
        columns[(e.page, round(e.identity.onset, 6))][e.bbox.x] += 1
    noteheads = {key: c.most_common(1)[0][0] for key, c in columns.items()}

    checked = 0
    for slash in slashes:
        column = noteheads.get((slash.page, round(slash.identity.onset, 6)))
        if column is None:
            continue                        # no other staff plays this beat
        assert slash.bbox.x == pytest.approx(column, abs=1e-6), (
            f"{slash.identity.element_id} at {slash.bbox.x:.1f} is off the "
            f"beat column {column:.1f}")
        checked += 1
    assert checked >= 30, f"only {checked} slashes shared a beat with a note"


def _sig_right_edge(engraved, part: str, measure: int) -> float | None:
    """The right edge of a measure's opening clef/key/time prefix, for
    one part — the run of signatures that holds no beats.

    A courtesy signature at the end of a system carries this measure's
    id but the NEXT measure's onset (the FINDING-4 retime), and it sits
    past every beat, so onset is what tells the two apart."""
    start = engraved.timeline.starts.get(measure)
    edges = [e.bbox.x2 for e in engraved.layout.elements
             if e.identity.part == part
             and e.identity.kind in (ElementKind.CLEF, ElementKind.KEY_SIG,
                                     ElementKind.METER_SIG)
             and str(e.identity.element_id).split(":")[1] == f"m{measure}"
             and e.identity.onset == start]
    return max(edges) if edges else None


@pytest.mark.parametrize("fixture", ["engraved", "engraved_video"])
def test_no_slash_is_drawn_inside_the_signature_prefix(fixture, request) -> None:
    """The Nidelven bug (2026-08-31): the first slash of bar 1 was drawn
    between the key signature and the time signature. A measure that
    opens a system carries a clef/key/time prefix holding no beats, and
    nothing may sit in it."""
    engraved = request.getfixturevalue(fixture)
    checked = 0
    for slash in (e for e in engraved.layout.elements
                  if e.identity.kind is ElementKind.SLASH):
        measure = int(str(slash.identity.element_id).split(":")[1][1:])
        prefix_end = _sig_right_edge(engraved, slash.identity.part, measure)
        if prefix_end is None:
            continue                        # no prefix in this bar
        assert slash.bbox.x >= prefix_end, (
            f"{slash.identity.element_id} at {slash.bbox.x:.1f} is inside "
            f"its own staff's signature prefix (ends {prefix_end:.1f})")
        checked += 1
    assert checked, "no slash measure carried a signature — test proves nothing"


def test_the_reported_nidelven_bar_1(engraved_nidelven) -> None:
    """The score and bar Marcus reported it on, pinned end to end."""
    slashes = sorted((e for e in engraved_nidelven.layout.elements
                      if e.identity.kind is ElementKind.SLASH
                      and str(e.identity.element_id).startswith("P5:m1:")),
                     key=lambda e: e.identity.onset)
    assert len(slashes) == 4
    prefix_end = _sig_right_edge(engraved_nidelven, "P5", 1)
    assert prefix_end is not None
    assert slashes[0].bbox.x >= prefix_end
    # and they still run left to right across the bar
    assert [s.bbox.x for s in slashes] == sorted(s.bbox.x for s in slashes)
