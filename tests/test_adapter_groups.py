"""Staff-group engraving (Phase 8): <part-group> injection through the
adapter — grpSym decomposition, joined barlines, and THE id-stability pin
(ids are minted from musical identity, so a grouped re-engrave must not
move any of them; discharges BACKLOG 5's "verify" note).

Facts from spikes/NOTES.md "Phase 8 — part-group injection": one
id-bearing grpSym per system per group; connector paths fold into the
measure's existing barLine group; baseline m1 barlines leave the P1–P2
inter-staff gap (y 1604–2964 on page 1) empty.
"""

import pytest

from scoreanim.core.animation.reveal import REVEALED_KINDS
from scoreanim.core.animation.schedule import ANIMATED_KINDS
from scoreanim.core.animation.style import TINTED_KINDS
from scoreanim.core.engraving.svg_geom import path_bbox
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio_adapter import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_prep import PartGroupSpec
from tests.conftest import TESTSCORE

SAX_GROUP = PartGroupSpec(parts=("P1", "P2"))


@pytest.fixture(scope="module")
def engraved_grouped():
    return VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), groups=(SAX_GROUP,))


def _grpsyms(layout):
    return [e for e in layout.elements
            if e.identity.kind is ElementKind.GROUP_SYMBOL]


def test_grouped_score_loads_losslessly(engraved_grouped) -> None:
    # the decomposer raises on unknown classes, orphan drawables, lossy
    # claims, and duplicate ids — loading at all is the assertion
    assert engraved_grouped.layout.elements


def test_grpsym_one_per_system_and_static(engraved_grouped) -> None:
    syms = _grpsyms(engraved_grouped.layout)
    assert len(syms) == 5                      # systems 1 / 2,3 / 4,5
    assert [e.page for e in syms] == [1, 2, 2, 3, 3]
    for e in syms:
        ident = e.identity
        assert ident.onset is None and ident.extent is None
        assert ident.part is None and ident.staff is None
    assert ElementKind.GROUP_SYMBOL not in ANIMATED_KINDS
    assert ElementKind.GROUP_SYMBOL not in TINTED_KINDS
    assert ElementKind.GROUP_SYMBOL not in REVEALED_KINDS


def test_grpsym_carries_system_stamp(engraved_grouped) -> None:
    # system-at-a-time mode frames by element.system — the bracket must
    # ride its system's band in both presentation modes
    assert [e.system for e in _grpsyms(engraved_grouped.layout)] == \
        [1, 2, 3, 4, 5]


def test_grpsym_ids_are_span_keyed_and_deterministic(engraved_grouped) -> None:
    ids = sorted(str(e.identity.element_id)
                 for e in _grpsyms(engraved_grouped.layout))
    assert ids == [f"score:sys{n}:grpsym:P1-P2" for n in range(1, 6)]
    again = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), groups=(SAX_GROUP,))
    assert sorted(str(e.identity.element_id)
                  for e in _grpsyms(again.layout)) == ids


def test_element_ids_stable_under_grouping(engraved, engraved_grouped) -> None:
    """THE pin: ids are minted from musical identity, so injecting a
    part-group must not change a single existing id — only add the
    GROUP_SYMBOL ones. (Verovio's own ids all re-roll on any input
    change even with a fixed seed — spikes/NOTES.md Phase 8 — which is
    exactly why overrides key on OUR ids.)"""
    base_ids = {str(e.identity.element_id) for e in engraved.layout.elements}
    grouped = {str(e.identity.element_id)
               for e in engraved_grouped.layout.elements}
    grp_ids = {str(e.identity.element_id)
               for e in _grpsyms(engraved_grouped.layout)}
    assert grouped - grp_ids == base_ids


def test_kinds_stable_under_grouping(engraved, engraved_grouped) -> None:
    base = {str(e.identity.element_id): e.identity.kind
            for e in engraved.layout.elements}
    grouped = {str(e.identity.element_id): e.identity.kind
               for e in engraved_grouped.layout.elements
               if e.identity.kind is not ElementKind.GROUP_SYMBOL}
    assert grouped == base


def test_joined_barlines_fill_the_grouped_inter_staff_gap(
        engraved, engraved_grouped) -> None:
    """Connector paths fold into existing BARLINE elements (spike outcome
    A): the grouped m1 barline must draw ink at y-values inside its own
    vertical span that the baseline barline leaves empty (the scoping
    probe established baseline barlines are gapped per-staff segments —
    any joined look was a bbox-union artifact)."""
    def path_spans(layout, eid: str) -> list[tuple[float, float]]:
        (el,) = [e for e in layout.elements
                 if str(e.identity.element_id) == eid]
        spans = []
        for p in el.glyph.paths:
            r = p.transform.apply_rect(path_bbox(p.d))
            spans.append((r.y, r.y2))
        return spans

    def covered(spans, y: float) -> bool:
        return any(a <= y <= b for a, b in spans)

    base = path_spans(engraved.layout, "score:m1:barline:0")
    grouped = path_spans(engraved_grouped.layout, "score:m1:barline:0")
    assert len(grouped) > len(base)            # connector segments added

    # the FIRST baseline gap (topmost pair of staves = P1-P2, the grouped
    # saxes) must now be covered; deeper gaps between ungrouped staves
    # are larger and must stay empty
    edges = sorted(base)
    gaps = [(b1 + a2) / 2
            for (_, b1), (a2, _) in zip(edges, edges[1:]) if a2 > b1]
    sax_gap_mid, lower_gap_mids = gaps[0], gaps[1:]
    assert not covered(base, sax_gap_mid)
    assert covered(grouped, sax_gap_mid)
    assert lower_gap_mids and \
        not any(covered(grouped, y) for y in lower_gap_mids)
