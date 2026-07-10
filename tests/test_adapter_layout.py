"""PHASES 1.3 verification: the Verovio adapter against the Dorico test
score (concert-pitch expectations throughout, CLAUDE.md rule 9).

Pinned counts come from the fixture itself (Phase 0/T0 spike facts):
3 pages, 500 notes (119/224/157 per page), 7 parts, 3 grace notes,
248 <chord/> continuations + 133 chord roots = 381 chord members,
17 unpitched drum notes.
"""

from collections import Counter

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio_adapter import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind

from .conftest import TESTSCORE

PART_NAMES = {
    "Sop. Alto Ten. 1", "Ten. 2 Bari.", "Tpts. (B Flat)", "Tbns.",
    "Guitar", "Bass Guitar", "Drum Set",
}


def test_page_count_and_geometry(engraved) -> None:
    pages = engraved.layout.pages
    assert len(pages) == 3
    assert all(p.width == pytest.approx(2095.5, abs=1) for p in pages)
    assert all(p.height == pytest.approx(2966.9, abs=1) for p in pages)


def test_notehead_count_and_page_distribution(engraved) -> None:
    noteheads = [e for e in engraved.layout.elements
                 if e.identity.kind is ElementKind.NOTEHEAD]
    assert len(noteheads) == 500
    per_page = Counter(e.page for e in noteheads)
    assert per_page == {1: 119, 2: 224, 3: 157}


def test_identities_carry_part_names_and_onsets(engraved) -> None:
    noteheads = [e for e in engraved.layout.elements
                 if e.identity.kind is ElementKind.NOTEHEAD]
    assert {e.identity.part_name for e in noteheads} == PART_NAMES
    assert all(e.identity.onset is not None for e in noteheads)
    assert all(e.identity.part is not None and e.identity.staff == 1
               and e.identity.voice is not None for e in noteheads)


def test_grace_slur_extent(engraved) -> None:
    """The m1 grace-note slur: starts on the first grace (just before
    beat 2 = qstamp 1.0) and ends on the beat."""
    slur = next(e for e in engraved.layout.elements
                if e.identity.kind is ElementKind.SLUR
                and str(e.identity.element_id).startswith("P1:m1:"))
    assert slur.identity.part_name == "Sop. Alto Ten. 1"
    start, end = slur.identity.extent
    assert end == 1.0
    assert 0.75 < start < 1.0
    assert slur.page == 1


def test_note_records_cover_all_notes(engraved) -> None:
    records = engraved.note_records
    assert len(records) == 500
    unpitched = [r for r in records if r.pitch_step is None]
    assert len(unpitched) == 17
    assert all(r.staff_loc is not None and r.part == "P7" for r in unpitched)
    graces = [r for r in records if r.grace]
    assert len(graces) == 3
    chord_members = [r for r in records if r.chord_group is not None]
    assert len(chord_members) == 381
    assert len({r.chord_group for r in chord_members}) == 133


def test_open_ties_are_not_rendered(engraved) -> None:
    """64 ties exist in the source; the 5 with unresolved endpoints
    (spikes/NOTES.md) produce no drawn curve. None of the drawn ties has
    a degenerate extent."""
    ties = [e for e in engraved.layout.elements
            if e.identity.kind is ElementKind.TIE]
    assert len(ties) == 59
    assert all(t.identity.extent is None or
               t.identity.extent[0] < t.identity.extent[1] for t in ties)


def test_element_ids_unique(engraved) -> None:
    ids = [e.identity.element_id for e in engraved.layout.elements]
    assert len(ids) == len(set(ids))


def test_bboxes_positive_and_on_page(engraved) -> None:
    slack = 40.0        # page units (4 mm) — text bboxes are estimates
    for e in engraved.layout.elements:
        page = engraved.layout.pages[e.page - 1]
        assert e.bbox.w >= 0 and e.bbox.h >= 0, e.identity.element_id
        assert e.bbox.x >= -slack and e.bbox.y >= -slack, e.identity.element_id
        assert e.bbox.x2 <= page.width + slack, e.identity.element_id
        assert e.bbox.y2 <= page.height + slack, e.identity.element_id
        assert page.width >= 100 and page.height >= 100


def test_anchor_is_bbox_center_and_xy_near_bbox(engraved) -> None:
    for e in engraved.layout.elements:
        assert e.anchor == e.bbox.center
        assert e.bbox.x - 1 <= e.x <= e.bbox.x2 + 1, e.identity.element_id
        assert e.bbox.y - 1 <= e.y <= e.bbox.y2 + 1, e.identity.element_id


def test_every_element_has_geometry(engraved) -> None:
    for e in engraved.layout.elements:
        assert e.glyph.paths or e.glyph.texts, e.identity.element_id


def test_text_decomposition_preserves_anchor_and_styling(engraved) -> None:
    """Text fidelity, pinned the way note geometry is (the redraw must
    match Verovio's own output — including its upstream tofu):

    - staff labels are end-anchored single runs with the part names;
    - the page header keeps per-line anchors and the gray lyricist fill;
    - the tempo mark is four runs, with the metronome note isolated as a
      720px Bravura run (and Verovio's own tofu  left in the
      405px text run — upstream, BACKLOG item 3, not ours to fix)."""
    page1 = [e for e in engraved.layout.elements if e.page == 1]

    labels = [t for e in page1 for t in e.glyph.texts
              if e.identity.kind is ElementKind.TEXT
              and len(t.runs) == 1 and t.runs[0].content in PART_NAMES]
    assert {t.runs[0].content for t in labels} == PART_NAMES
    assert all(t.anchor == "end" for t in labels)

    def by_content(fragment: str):
        for e in page1:
            for t in e.glyph.texts:
                if fragment in "".join(r.content for r in t.runs):
                    return t
        raise AssertionError(f"no text containing {fragment!r}")

    title = by_content("Det var en gang")
    assert title.anchor == "middle"
    assert title.runs[0].font_weight == "bold"
    assert by_content("Fra Lyriske stykker").runs[0].font_style == "italic"
    assert by_content("Edvard Grieg").anchor == "end"
    assert by_content("Project Lyricist").runs[0].fill == "#C0C0C0"

    tempo = by_content("Swing")
    assert [r.content for r in tempo.runs] == \
        ["Swing ", "", "\xa0=\xa0", "120"]
    assert tempo.runs[1].font_family == "Bravura"
    assert tempo.runs[1].font_size == 720
    assert all(r.font_weight == "bold" for r in tempo.runs)


def test_every_text_primitive_is_well_formed(engraved) -> None:
    for e in engraved.layout.elements:
        for t in e.glyph.texts:
            assert t.anchor in ("start", "middle", "end"), e.identity.element_id
            assert t.runs, e.identity.element_id
            for r in t.runs:
                assert r.font_size > 0 and r.content.strip(), \
                    e.identity.element_id


def test_load_is_deterministic(engraved) -> None:
    """CLAUDE.md rule 4: same file + params → identical ElementIds and
    geometry on a fresh load."""
    second = VerovioEngravingProvider().load_detailed(TESTSCORE,
                                                      EngravingParams())
    first_sig = [(str(e.identity.element_id), e.page, e.bbox, e.x, e.y)
                 for e in engraved.layout.elements]
    second_sig = [(str(e.identity.element_id), e.page, e.bbox, e.x, e.y)
                  for e in second.layout.elements]
    assert first_sig == second_sig
    assert engraved.note_records == second.note_records
