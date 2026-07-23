"""Phase 5.1a: system attribution and broken-spanner segments.

Facts pinned from the fixtures (spikes/spanner_split.py, spikes/NOTES.md
Phase 5): testscore casts off as 1/2/2 systems per page (5 score-wide);
its 7 drawn m8→m9 ties break across the page-2 system boundary.
broken_hairpin_and_slur_test has 3 systems on one page, a hairpin broken
across m4→m5 (tstamp-addressed in MEI), a slur and 7 ties broken across
m8→m9 (one tie unmatched/undrawn: "3 ties left open" importer quirk,
minus one that stays within the system... pinned counts below are from
the render itself).
"""

import re
from collections import Counter

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind

from .conftest import SPANNER_SCORE

_MEASURE_RE = re.compile(r":m(\d+):")


def _measure_of(element_id: str) -> int | None:
    m = _MEASURE_RE.search(element_id)
    return int(m.group(1)) if m else None


def test_every_notehead_carries_a_system(engraved) -> None:
    noteheads = [e for e in engraved.layout.elements
                 if e.identity.kind is ElementKind.NOTEHEAD]
    assert all(e.system is not None for e in noteheads)
    per_system = Counter(e.system for e in noteheads)
    assert sorted(per_system) == [1, 2, 3, 4, 5]


def test_systems_follow_the_casting_off(engraved) -> None:
    """1/2/2 systems per page; measures 1-4/5-8/9-12/13-16/17-19."""
    page_of_system: dict[int, set[int]] = {}
    first_measure: dict[int, int] = {}
    for e in engraved.layout.elements:
        if e.identity.kind is not ElementKind.NOTEHEAD or e.system is None:
            continue
        page_of_system.setdefault(e.system, set()).add(e.page)
        m = _measure_of(str(e.identity.element_id))
        assert m is not None
        first_measure[e.system] = min(first_measure.get(e.system, m), m)
    assert page_of_system == {1: {1}, 2: {2}, 3: {2}, 4: {3}, 5: {3}}
    assert first_measure == {1: 1, 2: 5, 3: 9, 4: 13, 5: 17}


def test_slashes_and_ledgers_carry_systems(engraved) -> None:
    for kind in (ElementKind.SLASH, ElementKind.LEDGER_LINES):
        els = [e for e in engraved.layout.elements if e.identity.kind is kind]
        assert els
        assert all(e.system is not None for e in els), kind


def test_testscore_broken_tie_segments(engraved) -> None:
    """The m8→m9 ties (P3×2, P4×4, P6×1) each emit one continuation
    segment in system 3, inheriting the source identity under :seg1."""
    segs = [e for e in engraved.layout.elements
            if ":seg" in str(e.identity.element_id)]
    assert len(segs) == 7
    assert all(e.identity.kind is ElementKind.TIE for e in segs)
    assert all(e.system == 3 and e.page == 2 for e in segs)
    parts = Counter(e.identity.part for e in segs)
    assert parts == {"P3": 2, "P4": 4, "P6": 1}
    ids = {str(e.identity.element_id) for e in engraved.layout.elements}
    for seg in segs:
        source_id = str(seg.identity.element_id).rsplit(":seg", 1)[0]
        assert source_id in ids


def test_spanner_fixture_systems_and_segments(engraved_spanners) -> None:
    els = engraved_spanners.layout.elements
    noteheads = [e for e in els if e.identity.kind is ElementKind.NOTEHEAD]
    assert sorted({e.system for e in noteheads}) == [1, 2, 3]

    segs = {str(e.identity.element_id): e for e in els
            if ":seg" in str(e.identity.element_id)}
    kinds = Counter(e.identity.kind for e in segs.values())
    assert kinds == {ElementKind.TIE: 6, ElementKind.SLUR: 1,
                     ElementKind.HAIRPIN: 1}
    # the broken hairpin continues from system 1 into system 2, the
    # broken slur and ties from system 2 into system 3
    hairpin_seg = next(e for e in segs.values()
                       if e.identity.kind is ElementKind.HAIRPIN)
    assert hairpin_seg.system == 2
    slur_seg = next(e for e in segs.values()
                    if e.identity.kind is ElementKind.SLUR)
    assert slur_seg.system == 3
    assert all(e.system == 3 for e in segs.values()
               if e.identity.kind is ElementKind.TIE)
    # segments are attributable (part-tintable)
    assert all(e.identity.part in ("P1", "P2") for e in segs.values())


def test_hairpin_identity_resolved_from_tstamp(engraved_spanners) -> None:
    """Hairpins carry @staff + @tstamp/@tstamp2 (no startid); the adapter
    resolves part, staff, onset, and extent from them. m1-4 are 4/4, so
    m4 beat 1 = 12.0 quarters; tstamp2 '1m+2.5' = m5 beat 2.5 = 17.5."""
    hairpins = [e for e in engraved_spanners.layout.elements
                if e.identity.kind is ElementKind.HAIRPIN
                and ":seg" not in str(e.identity.element_id)]
    assert len(hairpins) == 1
    hp = hairpins[0]
    assert hp.identity.part == "P1"
    assert hp.identity.staff == 1
    assert hp.identity.onset == 12.0
    assert hp.identity.extent == (12.0, 17.5)
    assert hp.system == 1


def test_segment_ids_deterministic_across_loads(engraved_spanners) -> None:
    again = VerovioEngravingProvider().load_detailed(SPANNER_SCORE,
                                                     EngravingParams())
    ids_a = [str(e.identity.element_id)
             for e in engraved_spanners.layout.elements]
    ids_b = [str(e.identity.element_id) for e in again.layout.elements]
    assert ids_a == ids_b
    systems_a = [e.system for e in engraved_spanners.layout.elements]
    systems_b = [e.system for e in again.layout.elements]
    assert systems_a == systems_b
