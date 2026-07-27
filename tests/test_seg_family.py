"""The `:seg` fan-out (M3.3), pinned per the ruling — BACKLOG 9's last
open question.

Ruling 2026-07-27: an override on one segment of a system-broken spanner
writes the whole family. `spikes/seg_fanout.py` audited the grammar
first (4 fixtures, 30124 elements, 116 broken spanners: no nesting, no
orphans, no identity mismatch); these are the parts of that audit worth
keeping green forever, plus the family arithmetic itself.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scoreanim.core.editing import family_of, is_segment, source_of
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementId

FIXTURE = (Path(__file__).parent.parent / "testdata"
           / "broken_hairpin_and_slur_test.musicxml")
SEG_RE = re.compile(r"^(?P<source>.+):seg(?P<k>\d+)$")


# -- the arithmetic ------------------------------------------------------

def test_a_flat_element_is_its_own_family() -> None:
    eid = ElementId("P1:m4:s1:v1:notehead:0")
    assert not is_segment(eid)
    assert source_of(eid) == eid
    assert family_of(eid, [eid]) == (eid,)


def test_a_segment_resolves_to_its_source() -> None:
    src = ElementId("P1:m4:s1:v0:hairpin:0")
    seg = ElementId("P1:m4:s1:v0:hairpin:0:seg1")
    assert is_segment(seg) and source_of(seg) == src


def test_the_family_is_source_first_then_segments_in_order() -> None:
    """Order matters: the head carries the style and the rest ride as
    `segments`, so a stable head keeps the command deterministic."""
    src = ElementId("P1:m4:s1:v0:hairpin:0")
    known = [ElementId(f"{src}:seg2"), ElementId(f"{src}:seg10"),
             src, ElementId(f"{src}:seg1"),
             ElementId("P1:m4:s1:v1:notehead:0")]      # a bystander
    assert family_of(ElementId(f"{src}:seg2"), known) == (
        src, ElementId(f"{src}:seg1"), ElementId(f"{src}:seg2"),
        ElementId(f"{src}:seg10"))


def test_the_family_never_names_an_id_the_score_lacks() -> None:
    """Intersected with the loaded registry, so an override cannot be
    written against something the current engraving does not have."""
    src = ElementId("P1:m4:s1:v0:hairpin:0")
    assert family_of(src, [src]) == (src,)
    assert family_of(ElementId(f"{src}:seg1"), []) == \
        (ElementId(f"{src}:seg1"),)          # stale id: still clearable


def test_a_similar_looking_id_is_not_swept_in() -> None:
    """`:seg` must match the whole suffix and be all digits — a
    neighbouring spanner index must not join the family."""
    src = ElementId("P1:m4:s1:v0:hairpin:0")
    known = [src, ElementId("P1:m4:s1:v0:hairpin:1"),
             ElementId("P1:m4:s1:v0:hairpin:1:seg1"),
             ElementId(f"{src}:segX")]
    assert family_of(src, known) == (src,)


# -- the grammar the ruling rests on -------------------------------------

@pytest.fixture(scope="module")
def layout():
    return VerovioEngravingProvider().load(FIXTURE, EngravingParams())


def test_segments_are_their_sources_but_for_the_id(layout) -> None:
    """The premise of fanning out at all: a segment inherits everything
    but the id (`identity = replace(source, element_id=...)`), so the
    family really is one musical object. Also re-pins the FINDING-5
    invariant — only spanners have segments; a stem minting `:seg1`
    ids was a bug."""
    by_id = {str(el.identity.element_id): el.identity
             for el in layout.elements}
    families = [eid for eid in by_id if SEG_RE.match(eid)]
    assert families, "fixture must contain a system-broken spanner"

    for eid in families:
        src = by_id.get(SEG_RE.match(eid).group("source"))
        assert src is not None, f"{eid} has no source element"
        assert not SEG_RE.match(str(src.element_id)), "segments must not nest"
        seg = by_id[eid]
        assert (seg.kind, seg.part, seg.staff, seg.voice, seg.onset,
                seg.extent) == (src.kind, src.part, src.staff, src.voice,
                                src.onset, src.extent)
        assert src.kind.name in ("TIE", "SLUR", "HAIRPIN")


def test_family_of_recovers_the_real_families(layout) -> None:
    known = [el.identity.element_id for el in layout.elements]
    broken = [eid for eid in known if SEG_RE.match(str(eid))]
    for seg in broken:
        family = family_of(seg, known)
        assert len(family) >= 2                  # the source came along
        assert seg in family
        # every member resolves to the same source
        assert {source_of(m) for m in family} == {source_of(seg)}
