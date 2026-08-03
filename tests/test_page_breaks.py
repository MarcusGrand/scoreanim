"""M6.2 — the combined break pass at the prep seam.

`_apply_breaks` writes BOTH `<print>` attributes of a measure in one
visit (D3). The two override maps key the same measure and write the
same element, and the spike measured what two racing passes cost:
whichever ran first, the second found the element already rewritten and
reported a working gesture as inert. So the coherence rule is STATED
(`_wanted_break_attrs`) rather than left to fall out of pass order, and
these tests walk it cell by cell against brief §3.4's matrix.

The trap this file inherits from M5, doubled: `load_detailed` re-
`prepare()`s on the repagination and scale-to-fit retries, and both must
now carry BOTH maps.

Numbers reproduce `spikes/page_breaks.py` (brief §3.1–§3.5).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict

from scoreanim.core.engraving.systems import (SystemBand, page_of_measure,
                                              page_starts, plan_page_breaks,
                                              system_bands)
from scoreanim.core.engraving.types import EngravingParams, Rect
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.score.musicxml_prep import PageBreak, SystemBreak, prepare
from scoreanim.core.score.musicxml_breaks import _apply_breaks

from .conftest import BIGBAND_SCORE as BIGBAND
from .conftest import TALL_SYSTEM_SCORE, TESTSCORE

# testscore, baseline (spike §3.1): 5 systems of 4, 4, 4, 4, 3 measures on
# 3 pages starting at m1, m5, m13. Its encoded breaks are m9 / m17 as
# `new-system="yes"` and m5 / m13 as `new-page="yes"` ONLY — the
# page-only encoding that makes §3.1's A3/A4 finding possible.
BASE_SYSTEMS = {1: (1, 4), 2: (5, 8), 3: (9, 12), 4: (13, 16), 5: (17, 19)}
BASE_PAGE_STARTS = (1, 5, 13)


def _load(path=TESTSCORE, strict=True, **kw):
    return VerovioEngravingProvider().load_detailed(
        path, EngravingParams(), strict=strict, **kw)


def _spans(engraved) -> dict[int, tuple[int, int]]:
    per: dict[int, list[int]] = defaultdict(list)
    for measure, system in sorted(engraved.system_of_measure.items()):
        per[system].append(measure)
    return {s: (ms[0], ms[-1]) for s, ms in sorted(per.items())}


def _pages(engraved) -> dict[int, int]:
    return page_of_measure(system_bands(engraved.layout),
                           engraved.system_of_measure)


def _starts(engraved) -> tuple[int, ...]:
    return tuple(sorted(page_starts(_pages(engraved))))


def _warning(engraved, code):
    matches = [w for w in engraved.warnings if w.code == code]
    assert matches, f"no {code} warning in {[w.code for w in engraved.warnings]}"
    return matches[0]


def _clipped(engraved) -> list[int]:
    """The never-clip invariant, asserted rather than trusted."""
    page_h = engraved.layout.pages[0].height
    return [b.system for b in system_bands(engraved.layout)
            if b.rect.y + b.rect.h > page_h + 0.5]


# ---------------------------------------------------------------------------
# the derivation (§1.2): no adapter change, no new field
# ---------------------------------------------------------------------------

def test_page_of_measure_composes_the_two_maps(engraved) -> None:
    assert _starts(engraved) == BASE_PAGE_STARTS
    pages = _pages(engraved)
    assert pages[1] == 1 and pages[4] == 1
    assert pages[5] == 2 and pages[12] == 2
    assert pages[13] == 3 and pages[19] == 3
    assert page_starts({}) == frozenset()


# ---------------------------------------------------------------------------
# the pass itself
# ---------------------------------------------------------------------------

def _rewritten(system=None, page=None) -> list[dict[str, str]]:
    """Part 1's <print> attributes per measure ordinal, after the pass."""
    root = ET.fromstring(TESTSCORE.read_bytes())
    _apply_breaks(root, system or {}, page or {})
    return [dict(m.find("print").attrib) if m.find("print") is not None else {}
            for m in root.findall("part")[0].findall("measure")]


def test_force_asserts_both_attributes() -> None:
    """A page break implies a system break, so both are said out loud —
    which is also M6.0's promotion, asserted at authoring time."""
    attrs = _rewritten(page={3: PageBreak.FORCE})
    assert attrs[2]["new-page"] == "yes"             # ordinal 3 → index 2
    assert attrs[2]["new-system"] == "yes"
    # sparse: every other measure keeps exactly what the file encodes
    assert attrs[4]["new-page"] == "yes" and "new-system" not in attrs[4]
    assert attrs[8]["new-system"] == "yes"


def test_suppress_keeps_the_system_break_the_page_break_implied() -> None:
    """§3.1 A3/A4, the mirror of M5's D7. m5's ONLY break marker is
    new-page, so clearing it alone would take the system break with it
    and merge two systems the user never asked to merge."""
    attrs = _rewritten(page={5: PageBreak.SUPPRESS})
    assert attrs[4]["new-page"] == "no"
    assert attrs[4]["new-system"] == "yes"


def test_suppress_without_an_encoded_page_break_writes_nothing() -> None:
    """Nothing to suppress → the canonical XML stays a true delta, and
    there is no implied system break to preserve either."""
    root = ET.fromstring(TESTSCORE.read_bytes())
    before = ET.tostring(root)
    _, inert = _apply_breaks(root, {}, {9: PageBreak.SUPPRESS})
    assert ET.tostring(root) == before
    assert inert == (9,)


def test_force_creates_a_print_element_when_absent() -> None:
    root = ET.fromstring(
        "<score-partwise><part id='P1'>"
        "<measure number='1'><note/></measure>"
        "<measure number='2'><note/></measure>"
        "</part></score-partwise>")
    second = root.findall("part")[0].findall("measure")[1]
    _apply_breaks(root, {}, {2: PageBreak.FORCE})
    pr = second.find("print")
    assert pr is not None and pr.get("new-page") == "yes"
    assert list(second).index(pr) == 0               # inserted first


def test_the_pass_touches_part_1_only() -> None:
    root = ET.fromstring(TESTSCORE.read_bytes())
    parts = root.findall("part")
    assert len(parts) > 1
    others = [ET.tostring(p) for p in parts[1:]]
    _apply_breaks(root, {9: SystemBreak.SUPPRESS}, {3: PageBreak.FORCE})
    assert [ET.tostring(p) for p in root.findall("part")[1:]] == others


def test_an_ordinal_past_the_end_is_inert() -> None:
    """§3.1 A7 — silently inert at the seam, so D8's warning is what
    tells the user (rule 5's accepted staleness trade)."""
    _, inert = _apply_breaks(ET.fromstring(TESTSCORE.read_bytes()), {},
                             {20: PageBreak.FORCE})
    assert inert == (20,)


def test_forcing_where_the_file_already_encodes_a_page_break_is_inert() -> None:
    """The page override wrote nothing on its OWN attribute, which is
    what inert means here. Unreachable through the toggle (D5 offers
    SUPPRESS where a page already starts) — it is a hand-edit signal."""
    _, inert = _apply_breaks(ET.fromstring(TESTSCORE.read_bytes()), {},
                             {5: PageBreak.FORCE})
    assert inert == (5,)


def test_no_overrides_leaves_the_canonical_xml_untouched() -> None:
    """Why the goldens cannot move: no fixture has overrides."""
    plain = prepare(TESTSCORE).canonical_xml
    assert prepare(TESTSCORE, system_breaks={},
                   page_breaks={}).canonical_xml == plain


# ---------------------------------------------------------------------------
# §3.4's collision matrix, cell by cell — the pure rule
# ---------------------------------------------------------------------------

def test_page_force_beats_a_coincident_system_suppress() -> None:
    """§3.4 row 2, the incoherent pair. It resolved in OPPOSITE
    directions under the two pass orderings, so the answer is stated:
    the positive assertion wins, because a page break that refuses its
    own system break is not a layout."""
    attrs = _rewritten(system={9: SystemBreak.SUPPRESS},
                       page={9: PageBreak.FORCE})
    assert attrs[8]["new-page"] == "yes"
    assert attrs[8]["new-system"] == "yes"


def test_both_forced_at_one_ordinal_is_coherent_and_neither_is_inert() -> None:
    """§3.4 row 1. Under `pre` this row manufactured a spurious
    break-override-inert; one pass cannot."""
    root = ET.fromstring(TESTSCORE.read_bytes())
    inert_sys, inert_page = _apply_breaks(root, {3: SystemBreak.FORCE},
                                          {3: PageBreak.FORCE})
    assert inert_sys == () and inert_page == ()


def test_system_force_with_page_suppress_is_coherent() -> None:
    """§3.4 row 3: "start a system here, but not a page" — the pair says
    exactly what it means, and m3 has no encoded page break to remove,
    so the page half writes nothing and is inert. (Dorico spells the
    negative out, so m3 arrives carrying new-page="no" already; the test
    is that the pass leaves that alone rather than re-asserting it.)"""
    root = ET.fromstring(TESTSCORE.read_bytes())
    encoded = dict(root.findall("part")[0].findall("measure")[2]
                   .find("print").attrib)
    inert_sys, inert_page = _apply_breaks(root, {3: SystemBreak.FORCE},
                                          {3: PageBreak.SUPPRESS})
    attrs = dict(root.findall("part")[0].findall("measure")[2]
                 .find("print").attrib)
    assert attrs["new-system"] == "yes"
    assert attrs.get("new-page") == encoded.get("new-page") == "no"
    assert inert_sys == () and inert_page == (3,)


def test_both_suppressed_at_one_ordinal_reads_as_system_alone() -> None:
    """§3.4 row 4. Two NEGATIVE assertions do not contradict, so the
    page suppression does not assert the implied system break here —
    the user asked for that break to go too. Under `pre` this row also
    manufactured a spurious inert warning; neither half is inert now."""
    root = ET.fromstring(TESTSCORE.read_bytes())
    inert_sys, inert_page = _apply_breaks(root, {5: SystemBreak.SUPPRESS},
                                          {5: PageBreak.SUPPRESS})
    pr = root.findall("part")[0].findall("measure")[4].find("print")
    assert pr.get("new-system") == "no"
    assert pr.get("new-page") == "no"
    assert inert_sys == () and inert_page == ()


def test_an_overruled_system_suppress_is_reported_inert() -> None:
    """The honest consequence of the precedence: a system SUPPRESS that
    page FORCE overrules wrote nothing of its own, so it says so. Only
    reachable from a hand-edited file — the toggles clear the
    contradicting override in the same gesture (D3's prevention half)."""
    root = ET.fromstring(TESTSCORE.read_bytes())
    inert_sys, inert_page = _apply_breaks(root, {9: SystemBreak.SUPPRESS},
                                          {9: PageBreak.FORCE})
    assert inert_sys == (9,)
    assert inert_page == ()


# ---------------------------------------------------------------------------
# end to end through the whole pipeline
# ---------------------------------------------------------------------------

def test_force_splits_a_page(engraved) -> None:
    """§3.1 A1: a forced page break mid-system splits the system too."""
    out = _load(page_breaks={3: PageBreak.FORCE})
    assert _starts(out) == (1, 3, 5, 13)
    assert len(out.layout.pages) == 4
    assert len(_spans(out)) == 6                     # 5 systems → 6
    assert not _clipped(out)


def test_force_on_an_existing_system_start(engraved) -> None:
    """§3.1 A2: m9 already starts a system, so only the page splits."""
    out = _load(page_breaks={9: PageBreak.FORCE})
    assert _starts(out) == (1, 5, 9, 13)
    assert _spans(out) == BASE_SYSTEMS
    assert not _clipped(out)


def test_suppress_merges_pages_without_merging_systems() -> None:
    """§3.1 A3, with its damage repaired. Before the D3 rule this same
    edit took the score from five systems to three, because m5's page
    break was also its system break."""
    out = _load(page_breaks={5: PageBreak.SUPPRESS})
    assert _spans(out) == BASE_SYSTEMS               # NOT merged
    assert 5 not in _starts(out)
    assert not _clipped(out)


def test_force_and_suppress_compose_at_the_seam() -> None:
    """§3.1 A6, at the seam. Both are written; whether the FORCE
    SURVIVES a load that repaginates is D1's question, and belongs to
    the never-clip composition below, not to this pass."""
    attrs = _rewritten(page={3: PageBreak.FORCE, 13: PageBreak.SUPPRESS})
    assert attrs[2]["new-page"] == "yes"
    assert attrs[12]["new-page"] == "no"
    assert attrs[12]["new-system"] == "yes"          # the A3/A4 fix


def test_the_beat_authority_does_not_move(engraved) -> None:
    """Rule 12 (§3.3): a page break is a LAYOUT choice, so score_end and
    every measure start are unaffected in BOTH directions."""
    for overrides in ({3: PageBreak.FORCE}, {5: PageBreak.SUPPRESS}):
        out = _load(page_breaks=overrides)
        assert out.timeline.score_end == engraved.timeline.score_end
        assert out.timeline.starts == engraved.timeline.starts
        assert len(out.note_records) == len(engraved.note_records)


# ---------------------------------------------------------------------------
# the trap, times two: every re-preparing retry must carry BOTH maps
# ---------------------------------------------------------------------------

def test_repagination_retry_carries_both_maps() -> None:
    """Suppressing m13's page break overflows what is left and
    repaginates. The suppression is honored AT ITS OWN ORDINAL through
    that re-prepare — m13 does not come back — and, thanks to the D3
    rule, the five encoded systems survive it intact. The planner
    re-broke elsewhere, which is rule 7 owning the page count.

    (§3.2 B2 measured 2 pages here. That number was taken with the
    spike's prototype, which cleared `new-page` alone and so silently
    destroyed two SYSTEM breaks; with them preserved the same music
    needs three pages. The measurement moved because the ruled fix
    changed the input, not because never-clip did.)"""
    out = _load(page_breaks={13: PageBreak.SUPPRESS})
    assert "repaginated" in {w.code for w in out.warnings}
    assert 13 not in _starts(out)
    assert _starts(out) == (1, 9, 17)
    assert _spans(out) == BASE_SYSTEMS
    assert not _clipped(out)


def test_scale_to_fit_retry_carries_both_maps() -> None:
    """The deepest retry (§3.5): tall_system_min needs scale-to-fit, and
    the page break must survive that re-prepare too."""
    base = _load(TALL_SYSTEM_SCORE, strict=False)
    assert len(base.layout.pages) == 1
    out = _load(TALL_SYSTEM_SCORE, strict=False,
                page_breaks={2: PageBreak.FORCE})
    assert len(out.layout.pages) == 2
    assert _starts(out) == (1, 2)
    assert "scaled-to-fit" in {w.code for w in out.warnings}
    assert not _clipped(out)


def test_hide_unavailable_retry_carries_both_maps() -> None:
    """testscore's slash regions defeat hiding (rule 10), so this load
    re-engraves flat — re-using the same `prep` rather than re-preparing.
    Pinned here so it stays that way."""
    out = _load(hide_empty_staves=True, page_breaks={3: PageBreak.FORCE})
    codes = [w.code for w in out.warnings]
    assert codes.count("hide-unavailable") == 1
    assert _starts(out) == (1, 3, 5, 13)
    assert not _clipped(out)


# ---------------------------------------------------------------------------
# M6.3 — never-clip composition (D1). Authored intent is an INPUT to the
# plan, never a pass layered over it, and never-clip keeps the last word.
# ---------------------------------------------------------------------------

def _plan(*breaks_at, forced=frozenset()):
    """The planner over synthetic bands: three 400-high systems on a
    1000-high page, so the third always needs a new page."""
    bands = tuple(SystemBand(system=i, page=1,
                             rect=Rect(0, 50 + (i - 1) * 430, 1000, 400))
                  for i in (1, 2, 3))
    return plan_page_breaks(bands, 1000.0, {1: 1, 2: 5, 3: 9}, forced)


def test_the_planner_unions_forced_ordinals_into_its_plan() -> None:
    assert _plan() == (9,)
    assert _plan(forced={5}) == (5, 9)
    assert _plan(forced={9}) == (9,)                 # already needed


def test_the_planner_ignores_a_forced_ordinal_that_is_no_system_start() -> None:
    """Defence for a stale override (rule 5): the plan stays well-formed
    rather than naming a measure no system begins at."""
    assert _plan(forced={7}) == (9,)
    assert _plan(forced={9999}) == (9,)


def test_a_forced_page_break_survives_a_load_that_repaginates() -> None:
    """§3.2 B1/B3, the row the naive `pre` design LOSES — and loses
    rarely and silently, which is why `pre` was disqualified. The system
    FORCE at m19 makes the plan diverge from the encoded set, which is
    exactly the condition under which `_repaginate` destroys authored
    page intent written upstream of it."""
    out = _load(system_breaks={19: SystemBreak.FORCE},
                page_breaks={3: PageBreak.FORCE})
    assert "repaginated" in {w.code for w in out.warnings}
    assert _starts(out) == (1, 3, 5, 13, 19)
    assert _spans(out)[max(_spans(out))] == (19, 19)   # and the system break
    assert not _clipped(out)


def test_a_suppression_the_planner_does_not_need_is_honored() -> None:
    """§3.2 B2: the planner re-broke the score ELSEWHERE (5,13 → 9,17)
    and no suppressed ordinal came back. The user is never told "no" —
    they are told "yes, and here is where the pages fell instead"."""
    out = _load(page_breaks={5: PageBreak.SUPPRESS, 13: PageBreak.SUPPRESS})
    assert _starts(out) == (1, 9, 17)
    assert not _clipped(out)
    warning = _warning(out, "page-break-repaginated")
    assert "1, 9, 17" in warning.message
    assert "could not be honored" not in warning.message


def test_a_suppression_that_would_clip_is_overruled_and_says_so() -> None:
    """Rule 7 keeping the last word, and the ruled amendment's own
    words: "a suppressed one is overridden, and warned, whenever
    honoring it would clip ink". The planner is looking at the piled-up
    layout the suppression produced, so every break it emits is one it
    NEEDS — which is why the suppressed set is not subtracted from its
    plan (see plan_page_breaks). Dropping them instead measured as a
    two-page bigband1 rescued by scale-to-fit at 40%: legal, unclipped,
    and a much worse score than the extra page."""
    out = _load(BIGBAND, strict=False,
                page_breaks={12: PageBreak.SUPPRESS, 20: PageBreak.SUPPRESS})
    assert _starts(out) == (1, 12, 20, 26)
    assert not _clipped(out)
    assert "scaled-to-fit" not in {w.code for w in out.warnings}
    message = _warning(out, "page-break-repaginated").message
    assert "override(s) at measure 12, 20 could not be honored" in message


def test_the_two_page_warnings_say_different_things() -> None:
    """D8's whole point: "your override was stale" and "your override
    was overruled to avoid clipping ink" want different things from the
    user, so they are different codes."""
    stale = _load(page_breaks={99: PageBreak.FORCE})
    assert {w.code for w in stale.warnings} & {"page-break-override-inert"}
    assert "page-break-repaginated" not in {w.code for w in stale.warnings}
    assert "measure 99" in _warning(stale, "page-break-override-inert").message
    assert not _clipped(stale)

    overruled = _load(page_breaks={3: PageBreak.FORCE,
                                   13: PageBreak.SUPPRESS})
    codes = {w.code for w in overruled.warnings}
    assert "page-break-repaginated" in codes
    assert "page-break-override-inert" not in codes


def test_no_ordinal_is_reported_both_stale_and_overruled() -> None:
    """The two codes are read off the FINAL layout, so they partition
    rather than overlap. Here m20's page break IS cleared at the seam and
    then reinstated by the planner (overruled), while m30 — where the
    score has no page break at all — wrote nothing and was not overruled
    (stale). Reporting either one twice, or under the other's code,
    would tell the user to do the wrong thing about it."""
    out = _load(BIGBAND, strict=False,
                page_breaks={12: PageBreak.SUPPRESS,
                             20: PageBreak.SUPPRESS,
                             30: PageBreak.SUPPRESS})
    overruled = _warning(out, "page-break-repaginated").message
    stale = _warning(out, "page-break-override-inert").message
    assert overruled.endswith("override(s) at measure 12, 20 could not "
                              "be honored")
    assert stale == ("1 page-break override(s) had no effect (measure 30)")
    assert 30 in out.prepared.inert_page_breaks
    assert not _clipped(out)


def test_never_clip_holds_on_every_authored_page_edit() -> None:
    """The invariant this milestone is most able to break, asserted
    directly on every row §3 measured rather than inferred from the
    warning set."""
    cases = [
        (TESTSCORE, True, dict(page_breaks={3: PageBreak.FORCE})),
        (TESTSCORE, True, dict(page_breaks={9: PageBreak.FORCE})),
        (TESTSCORE, True, dict(page_breaks={5: PageBreak.SUPPRESS})),
        (TESTSCORE, True, dict(page_breaks={5: PageBreak.SUPPRESS,
                                            13: PageBreak.SUPPRESS})),
        (TESTSCORE, True, dict(system_breaks={19: SystemBreak.FORCE},
                               page_breaks={3: PageBreak.FORCE})),
        (BIGBAND, False, dict(page_breaks={7: PageBreak.FORCE})),
        (BIGBAND, False, dict(hide_empty_staves=True,
                              page_breaks={7: PageBreak.FORCE})),
        (BIGBAND, False, dict(page_breaks={12: PageBreak.SUPPRESS,
                                           20: PageBreak.SUPPRESS})),
        (TALL_SYSTEM_SCORE, False, dict(page_breaks={2: PageBreak.FORCE})),
    ]
    for path, strict, kw in cases:
        out = _load(path, strict=strict, **kw)
        assert not _clipped(out), (path.name, kw)


def test_the_downstream_sweep_survives_page_authoring() -> None:
    """§3.5 E1/E3/E6: hiding, condensing and scale-to-fit are unchanged
    by a page edit, and the warning set does not grow."""
    base = _load(BIGBAND, strict=False, hide_empty_staves=True)
    out = _load(BIGBAND, strict=False, hide_empty_staves=True,
                page_breaks={7: PageBreak.FORCE})
    assert _starts(out) == (1, 7, 12, 20)
    assert len(out.layout.pages) == len(base.layout.pages) + 1
    # the page edit adds no NEW kind of warning
    assert {w.code for w in out.warnings} <= {w.code for w in base.warnings}

    tall = _load(TALL_SYSTEM_SCORE, strict=False,
                 page_breaks={2: PageBreak.FORCE})
    assert "scaled-to-fit" in {w.code for w in tall.warnings}
    assert len(tall.layout.pages) == 2
