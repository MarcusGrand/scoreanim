"""Never-clip repagination (Phase 10R, rule-7 amendment): when the
encoded page breaks cannot hold their systems, the adapter keeps the
encoded SYSTEM breaks, discards the encoded page breaks, and re-derives
page breaks from measured band heights — one extra engrave, flagged,
deterministic, never stored (rule 5). The video fixture's FLAT load is
the live case: Dorico's breaks assume hidden staves.

M6.0 (BACKLOG 16) is the fix that makes "keeps the encoded SYSTEM
breaks" literally true: a Dorico page break is encoded as `new-page`
ALONE, so the strip used to take its implied system break with it.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict

from scoreanim.core.engraving.systems import SystemBand, plan_page_breaks
from scoreanim.core.engraving.types import EngravingParams, Rect
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.score.musicxml_prep import SystemBreak
from scoreanim.core.score.musicxml_rewrite import (
    _promote_page_breaks_to_system, _repaginate)

from .conftest import TESTSCORE


def _band(system: int, page: int, y: float, h: float) -> SystemBand:
    return SystemBand(system=system, page=page, rect=Rect(0, y, 1000, h))


def test_planner_packs_greedily_with_measured_margins():
    # page 1 holds two systems (top 50, gap 30); page height 1000
    bands = (_band(1, 1, 50, 300), _band(2, 1, 630, 300),
             _band(3, 2, 50, 900), _band(4, 2, 1000, 900))  # overflows
    breaks = plan_page_breaks(bands, 1000.0, {1: 1, 2: 5, 3: 9, 4: 13})
    # 50+300+250(gap: 630-350=280 median)+300 = fits; sys3 900 doesn't
    # fit after sys2 → break at m9; sys4 doesn't fit after sys3 → m13
    assert breaks == (9, 13)


def test_planner_no_breaks_when_everything_fits():
    bands = (_band(1, 1, 50, 300), _band(2, 1, 400, 300))
    assert plan_page_breaks(bands, 1000.0, {1: 1, 2: 5}) == ()


def test_planner_oversized_single_system_never_loops():
    # a system taller than the page still gets placed (alone)
    bands = (_band(1, 1, 50, 300), _band(2, 1, 400, 2000))
    assert plan_page_breaks(bands, 1000.0, {1: 1, 2: 5}) == (5,)


def test_planner_empty():
    assert plan_page_breaks((), 1000.0, {}) == ()


def test_video_flat_repaginates_cleanly(engraved_video,
                                        engraved_video_hidden):
    from scoreanim.core.engraving.systems import system_bands

    page_h = engraved_video.layout.pages[0].height
    assert len(engraved_video.layout.pages) == 15    # one system per page
    for band in system_bands(engraved_video.layout):
        assert band.rect.y + band.rect.h <= page_h
    assert [w.code for w in engraved_video.warnings].count(
        "repaginated") == 1
    assert not [w for w in engraved_video.warnings
                if w.code == "system-overflow"]
    # musical content identical across pagination AND hiding
    assert engraved_video.note_records == engraved_video_hidden.note_records


def test_prior_fixtures_never_repaginate(engraved, engraved_spanners):
    for es in (engraved, engraved_spanners):
        assert not [w for w in es.warnings if w.code == "repaginated"]


# ---------------------------------------------------------------------------
# M6.0 — BACKLOG 16: a repagination may not change SYSTEM content
# ---------------------------------------------------------------------------

def _print_attrs(root: ET.Element) -> dict[int, dict[str, str]]:
    """Part 1's <print> attributes per 1-based measure ordinal."""
    part = root.findall("part")[0]
    return {ordinal: dict(measure.find("print").attrib)
            for ordinal, measure in enumerate(part.findall("measure"), start=1)
            if measure.find("print") is not None}


def test_testscore_encodes_its_page_breaks_page_only():
    """The premise of the whole fix (spike §3.6): m5 and m13 carry
    new-page and NO new-system, so new-page is their only break
    marker."""
    attrs = _print_attrs(ET.fromstring(TESTSCORE.read_bytes()))
    assert attrs[5].get("new-page") == "yes"
    assert attrs[13].get("new-page") == "yes"
    assert "new-system" not in attrs[5]
    assert "new-system" not in attrs[13]


def test_promotion_says_the_implied_system_break_out_loud():
    root = ET.fromstring(TESTSCORE.read_bytes())
    assert _promote_page_breaks_to_system(root) > 0
    attrs = _print_attrs(root)
    assert attrs[5]["new-system"] == "yes"
    assert attrs[13]["new-system"] == "yes"


def test_promotion_is_idempotent_and_touches_nothing_else():
    root = ET.fromstring(TESTSCORE.read_bytes())
    _promote_page_breaks_to_system(root)
    before = _print_attrs(root)
    assert _promote_page_breaks_to_system(root) == 0
    assert _print_attrs(root) == before
    # Dorico writes new-page="no" explicitly on a system-only break
    # (m9), so the promotion has a negative case to skip as well as an
    # absent one — it fires on "yes" and nothing else.
    assert before[9] == {"new-system": "yes", "new-page": "no"}


def test_repaginate_preserves_page_only_system_breaks():
    """The unit form of spike F2: after a strip-and-re-assert that plans
    a DIFFERENT page set, m5 and m13 still start systems."""
    root = ET.fromstring(TESTSCORE.read_bytes())
    _repaginate(root, (9,))
    attrs = _print_attrs(root)
    assert attrs[5]["new-system"] == "yes"
    assert attrs[13]["new-system"] == "yes"
    assert attrs[9]["new-page"] == "yes"
    assert [o for o, a in attrs.items() if a.get("new-page") == "yes"] == [9]


def _spans(engraved) -> dict[int, tuple[int, int]]:
    per: dict[int, list[int]] = defaultdict(list)
    for measure, system in sorted(engraved.system_of_measure.items()):
        per[system].append(measure)
    return {s: (ms[0], ms[-1]) for s, ms in sorted(per.items())}


def test_a_forced_system_break_no_longer_collapses_the_encoded_systems():
    """Spike F2 end to end, and the damage this pass repairs: a system
    FORCE at testscore m19 overflows, which repaginates. Before M6.0 the
    strip took m5's and m13's implied system breaks with it and the
    score collapsed to {1:(1,8), 2:(9,16), 3:(17,18), 4:(19,19)}."""
    out = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(),
        system_breaks={19: SystemBreak.FORCE})
    assert "repaginated" in {w.code for w in out.warnings}
    assert _spans(out) == {1: (1, 4), 2: (5, 8), 3: (9, 12), 4: (13, 16),
                           5: (17, 18), 6: (19, 19)}
