"""Staff-group engraving (Phase 8): <part-group> injection through the
adapter — grpSym decomposition, joined barlines, and THE id-stability pin
(ids are minted from musical identity, so a grouped re-engrave must not
move any of them; discharges BACKLOG 5's "verify" note).

Facts from spikes/NOTES.md "Phase 8 — part-group injection": one
id-bearing grpSym per system per group; connector paths fold into the
measure's existing barLine group; baseline m1 barlines leave the P1–P2
inter-staff gap (y 1604–2964 on page 1) empty.
"""

from collections import Counter, defaultdict

import pytest

from scoreanim.core.animation.reveal import ANCHOR_KINDS, REVEALED_KINDS
from scoreanim.core.animation.schedule import ANIMATED_KINDS
from scoreanim.core.animation.style import TINTED_KINDS
from scoreanim.core.engraving.svg_geom import path_bbox
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.engraving.verovio.decompose import _PageDecomposer
from scoreanim.core.engraving.verovio.identity import _identity_for
from scoreanim.core.engraving.verovio.mei_index import _MeiIndex
from scoreanim.core.engraving.verovio.records import _LoadState
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_prep import PartGroupSpec
from tests.conftest import TESTSCORE

SAX_GROUP = PartGroupSpec(parts=("P1", "P2"))
# Two disjoint groups: the configuration that re-opened BACKLOG 1 —
# Verovio's condense:"auto" would condense the layout and draw
# systemDividers; condense:"encoded" (Phase 10) keeps the encoded layout.
TWO_GROUPS = (PartGroupSpec(parts=("P1", "P2")),
              PartGroupSpec(parts=("P3", "P4")))


@pytest.fixture(scope="module")
def engraved_grouped():
    return VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), groups=(SAX_GROUP,))


@pytest.fixture(scope="module")
def engraved_two_groups():
    return VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), groups=TWO_GROUPS)


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


# --- Phase 10: N>=2 groups (BACKLOG 1, re-opened and closed here) ----------

def test_two_groups_load_with_the_encoded_layout(engraved,
                                                 engraved_two_groups) -> None:
    """condense:"encoded" keeps the layout group-count-invariant: same
    pages, same per-system staff row count, TWO span-keyed grpSyms per
    system, and no systemDivider ink at all."""
    spans = Counter(str(e.identity.element_id).rsplit(":", 1)[-1]
                    for e in _grpsyms(engraved_two_groups.layout))
    assert spans == {"P1-P2": 5, "P3-P4": 5}
    per_system = Counter(e.system
                         for e in _grpsyms(engraved_two_groups.layout))
    assert per_system == {n: 2 for n in range(1, 6)}
    assert not [e for e in engraved_two_groups.layout.elements
                if e.identity.kind is ElementKind.SYSTEM_DIVIDER]
    base_staves = [e for e in engraved.layout.elements
                   if e.identity.kind is ElementKind.STAFF_LINES]
    two_staves = [e for e in engraved_two_groups.layout.elements
                  if e.identity.kind is ElementKind.STAFF_LINES]
    assert len(two_staves) == len(base_staves)   # no staves hidden


def test_element_ids_stable_under_two_groups(engraved,
                                             engraved_two_groups) -> None:
    # the 8.3 pin, at N=2: grouped ids == baseline + the grpSym ids
    base_ids = {str(e.identity.element_id) for e in engraved.layout.elements}
    grouped = {str(e.identity.element_id)
               for e in engraved_two_groups.layout.elements}
    grp_ids = {str(e.identity.element_id)
               for e in _grpsyms(engraved_two_groups.layout)}
    assert grouped - grp_ids == base_ids


def test_system_divider_is_static_by_construction() -> None:
    # ruling (a): SYSTEM_DIVIDER never animates, tints, anchors, or
    # reveals — every one of those sets is an allowlist
    assert ElementKind.SYSTEM_DIVIDER not in ANIMATED_KINDS
    assert ElementKind.SYSTEM_DIVIDER not in TINTED_KINDS
    assert ElementKind.SYSTEM_DIVIDER not in REVEALED_KINDS
    assert ElementKind.SYSTEM_DIVIDER not in ANCHOR_KINDS


def test_system_divider_decomposes_with_system_scoped_identity() -> None:
    """No fixture draws a divider under condense:"encoded", so the id-less
    systemDivider branch is covered synthetically: the Verovio shape is an
    id-less <g class="systemDivider"> with two polygons, hosted directly
    in the system (triage spike, section B)."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2096 2967">'
        '<svg viewBox="0 0 20960 29670" class="definition-scale">'
        '<g class="page-margin" transform="translate(50, 50)">'
        '<g class="system" xml:id="s1">'
        '<g class="systemDivider">'
        '<polygon points="0,100 300,50 300,90 0,140"/>'
        '<polygon points="0,200 300,150 300,190 0,240"/>'
        '</g></g></g></svg></svg>')
    st = _LoadState(prep=None, mei=_MeiIndex(), onset_by_id={},
                    measure_start={}, measure_duration={},
                    staff_n_by_id={}, layer_n_by_id={})
    accs = _PageDecomposer(svg, page=1, adapter=st).run()
    (acc,) = accs
    assert acc.kind is ElementKind.SYSTEM_DIVIDER
    assert acc.system == 1 and len(acc.paths) == 2 and acc.bbox is not None
    identity = _identity_for(acc, page=1, st=st, counters=defaultdict(int))
    assert str(identity.element_id) == "score:sys1:systemdivider:0"
    assert identity.onset is None and identity.part is None


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
