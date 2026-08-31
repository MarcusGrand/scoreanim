"""M5.2 — the system-break prep-seam pass.

The user's break intent rewrites `<print new-system>` on part 1 of the
canonical MusicXML BEFORE Verovio, so hiding, condensing, repagination
and scale-to-fit all operate on the edited break set exactly as they do
on the encoded one. Numbers here reproduce the measurements in
`spikes/system_breaks.py` (brief §3.1–§3.3).

The trap this file exists to pin: `load_detailed` re-`prepare()`s on the
repagination and scale-to-fit retries, and re-engraves the same `prep`
on the hide-unavailable retry. All three paths must carry the overrides,
or a score that repaginates silently loses the user's breaks.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_prep import SystemBreak, prepare
from scoreanim.core.score.musicxml_breaks import _apply_breaks

from .conftest import (BIGBAND_SCORE, TALL_SYSTEM_SCORE, TESTSCORE,
                       VIDEO_SCORE)

# testscore, baseline (spike §3.1): 5 systems of 4, 4, 4, 4, 3 measures.
# Its encoded breaks are m9 / m17 as `new-system="yes"` and m5 / m13 as
# `new-page="yes"` (a page break implies a system break — the fact D7
# turns on).
BASE = {1: (1, 4), 2: (5, 8), 3: (9, 12), 4: (13, 16), 5: (17, 19)}


def _load(path, strict=True, **kw):
    return VerovioEngravingProvider().load_detailed(
        path, EngravingParams(), strict=strict, **kw)


def _spans(engraved) -> dict[int, tuple[int, int]]:
    """System index → (first measure, last measure)."""
    per: dict[int, list[int]] = defaultdict(list)
    for measure, system in sorted(engraved.system_of_measure.items()):
        per[system].append(measure)
    return {s: (ms[0], ms[-1]) for s, ms in sorted(per.items())}


def _starts_a_system(engraved, ordinal: int) -> bool:
    return any(first == ordinal for first, _ in _spans(engraved).values())


# ---------------------------------------------------------------------------
# the pass itself
# ---------------------------------------------------------------------------

def _rewritten(overrides) -> list[dict[str, str]]:
    """Part 1's <print> attributes per measure ordinal, after the pass."""
    root = ET.fromstring(TESTSCORE.read_bytes())
    _apply_breaks(root, overrides)
    out = []
    for measure in root.findall("part")[0].findall("measure"):
        pr = measure.find("print")
        out.append(dict(pr.attrib) if pr is not None else {})
    return out


def test_force_writes_new_system_yes_at_the_target_ordinal() -> None:
    attrs = _rewritten({3: SystemBreak.FORCE})
    assert attrs[2]["new-system"] == "yes"           # ordinal 3 → index 2
    # sparse: every other measure keeps exactly what the file encodes
    assert attrs[8]["new-system"] == "yes"           # m9, encoded
    assert attrs[5]["new-system"] == "no"            # m6, encoded


def _bare() -> ET.Element:
    """Two measures with no <print> at all. Every measure of every Dorico
    fixture carries one, so the absent case needs a synthetic tree — but
    it is the case `_repaginate` handles too, and a hand-written or
    non-Dorico MusicXML will hit it."""
    return ET.fromstring(
        "<score-partwise><part id='P1'>"
        "<measure number='1'><note/></measure>"
        "<measure number='2'><note/></measure>"
        "</part></score-partwise>")


def test_force_creates_a_print_element_when_absent() -> None:
    root = _bare()
    second = root.findall("part")[0].findall("measure")[1]
    _apply_breaks(root, {2: SystemBreak.FORCE})
    pr = second.find("print")
    assert pr is not None and pr.get("new-system") == "yes"
    assert list(second).index(pr) == 0               # inserted first


def test_suppress_writes_new_system_no() -> None:
    attrs = _rewritten({9: SystemBreak.SUPPRESS})
    assert attrs[8]["new-system"] == "no"


def test_suppress_clears_a_coincident_page_break() -> None:
    """D7: a page break implies a system break, so suppressing the system
    break must drop the page break too — otherwise the suppression is a
    lie and the systems simply do not merge (spike F2)."""
    attrs = _rewritten({5: SystemBreak.SUPPRESS})
    assert attrs[4]["new-system"] == "no"
    assert attrs[4]["new-page"] == "no"              # was "yes"


def test_suppress_without_an_encoded_print_writes_nothing() -> None:
    """No encoded break to suppress → the canonical XML stays a true
    delta. Verovio would honor it identically either way (spike A3)."""
    root = _bare()
    before = ET.tostring(root)
    _apply_breaks(root, {2: SystemBreak.SUPPRESS})
    assert ET.tostring(root) == before


def test_the_pass_touches_part_1_only() -> None:
    """Verovio reads print layout from the first part (spike section D),
    and _repaginate already keys the same way."""
    root = ET.fromstring(TESTSCORE.read_bytes())
    parts = root.findall("part")
    assert len(parts) > 1
    others_before = [ET.tostring(p) for p in parts[1:]]
    _apply_breaks(root, {3: SystemBreak.FORCE, 9: SystemBreak.SUPPRESS})
    assert [ET.tostring(p) for p in root.findall("part")[1:]] == others_before


def test_no_overrides_leaves_the_canonical_xml_untouched() -> None:
    """Why the goldens cannot move: no fixture has overrides."""
    plain = prepare(TESTSCORE).canonical_xml
    assert prepare(TESTSCORE, system_breaks={}).canonical_xml == plain
    assert prepare(TESTSCORE, system_breaks=None).canonical_xml == plain
    assert prepare(TESTSCORE, page_breaks={}).canonical_xml == plain
    assert prepare(TESTSCORE, page_breaks=None).canonical_xml == plain


# ---------------------------------------------------------------------------
# end to end through the whole pipeline
# ---------------------------------------------------------------------------

def test_baseline_systems(engraved) -> None:
    assert _spans(engraved) == BASE


def test_force_splits_a_system(engraved) -> None:
    """Spike §3.1 A1: FORCE at m3 splits system 1 into [1,2] and [3,4]
    and shifts the rest down by one."""
    out = _load(TESTSCORE, system_breaks={3: SystemBreak.FORCE})
    assert _spans(out) == {1: (1, 2), 2: (3, 4), 3: (5, 8), 4: (9, 12),
                           5: (13, 16), 6: (17, 19)}
    assert len(out.layout.pages) == len(engraved.layout.pages)


def test_suppress_merges_systems() -> None:
    """Spike §3.1 A2: SUPPRESS at m9 merges systems 2 and 3."""
    out = _load(TESTSCORE, system_breaks={9: SystemBreak.SUPPRESS})
    assert _spans(out) == {1: (1, 4), 2: (5, 12), 3: (13, 16), 4: (17, 19)}


def test_force_and_suppress_compose() -> None:
    """Spike §3.1 A6: both edits land in one load."""
    out = _load(TESTSCORE, system_breaks={3: SystemBreak.FORCE,
                                          9: SystemBreak.SUPPRESS})
    assert _spans(out) == {1: (1, 2), 2: (3, 4), 3: (5, 12), 4: (13, 16),
                           5: (17, 19)}


def test_suppress_where_there_is_no_encoded_break_is_inert() -> None:
    """D5: never written through the UI, and harmless when a document
    holds one anyway (hand-edited file, or a score swapped underneath)."""
    out = _load(TESTSCORE, system_breaks={3: SystemBreak.SUPPRESS})
    assert _spans(out) == BASE


def test_an_ordinal_past_the_end_is_inert() -> None:
    """Spike §3.6 F1 — the rewrite loop never reaches it, exactly as
    _repaginate behaves for an out-of-range plan entry. D10 warns."""
    out = _load(TESTSCORE, system_breaks={20: SystemBreak.FORCE})
    assert _spans(out) == BASE


def test_force_on_a_measure_that_already_starts_a_system_is_inert() -> None:
    """Spike §3.1 A4: asserting a break where one already holds."""
    out = _load(TESTSCORE, system_breaks={1: SystemBreak.FORCE})
    assert _spans(out) == BASE


def test_suppressing_a_page_encoded_break_merges_end_to_end() -> None:
    """D7 through the whole pipeline (spike F2): m5's break is encoded
    only as new-page="yes", so without clearing it nothing would merge.
    The page COUNT is unchanged — rule 7(a)'s repagination re-derives
    the page breaks, so we own the page count rather than clipping."""
    out = _load(TESTSCORE, system_breaks={5: SystemBreak.SUPPRESS})
    assert _spans(out)[1] == (1, 8)                  # merged
    assert len(out.layout.pages) == 3


def test_the_beat_authority_does_not_move(engraved) -> None:
    """Rule 12 (spike §3.4): a break is a LAYOUT choice, so the engraved
    timemap — score_end and every trigger — is unaffected."""
    for overrides in ({3: SystemBreak.FORCE}, {9: SystemBreak.SUPPRESS}):
        out = _load(TESTSCORE, system_breaks=overrides)
        assert out.timeline.score_end == engraved.timeline.score_end
        assert out.timeline.starts == engraved.timeline.starts


def test_unaffected_measures_keep_their_barline_ids(engraved) -> None:
    """Spike §3.2: the 19 measure-scoped barline ids are byte-identical
    under both edits — which is what lets M5.5 restore the selection
    after the re-engrave (D9)."""
    def barlines(e):
        return {x.identity.element_id for x in e.layout.elements
                if x.identity.kind is ElementKind.BARLINE
                and str(x.identity.element_id).startswith("score:m")}

    base = barlines(engraved)
    assert len(base) == 19
    for overrides in ({3: SystemBreak.FORCE}, {9: SystemBreak.SUPPRESS}):
        assert barlines(_load(TESTSCORE, system_breaks=overrides)) == base


# ---------------------------------------------------------------------------
# the trap: all three retry paths must carry the overrides
# ---------------------------------------------------------------------------

def test_repagination_retry_carries_the_overrides() -> None:
    """`repaginated` fires (the forced final system overflows) and the
    forced break is STILL there afterwards — the retry re-prepares, so
    it has to pass system_breaks through."""
    out = _load(TESTSCORE, system_breaks={19: SystemBreak.FORCE})
    assert "repaginated" in {w.code for w in out.warnings}
    assert _starts_a_system(out, 19)
    assert _spans(out)[max(_spans(out))] == (19, 19)


def test_scale_to_fit_retry_carries_the_overrides() -> None:
    """The deepest retry: tall_system_min needs scale-to-fit, and the
    forced break must survive that re-prepare too."""
    base = _load(TALL_SYSTEM_SCORE, strict=False)
    assert _spans(base) == {1: (1, 2)}
    out = _load(TALL_SYSTEM_SCORE, strict=False,
                system_breaks={2: SystemBreak.FORCE})
    assert _spans(out) == {1: (1, 1), 2: (2, 2)}
    assert "scaled-to-fit" in {w.code for w in out.warnings}


def test_hide_unavailable_retry_carries_the_overrides(monkeypatch) -> None:
    """The rule-10 fallback re-engraves flat, re-using the same `prep`
    rather than re-preparing — pinned here so it stays that way. Since
    2026-08-09 the region fill keeps the fallback from firing on
    testscore at all, so this pin disables the fill to reach it."""
    from scoreanim.core.engraving.verovio import region_fill
    monkeypatch.setattr(region_fill, "fill_region_measures",
                        lambda xml, *regions: xml)
    out = _load(TESTSCORE, hide_empty_staves=True,
                system_breaks={3: SystemBreak.FORCE})
    codes = [w.code for w in out.warnings]
    assert codes.count("hide-unavailable") == 1
    assert _spans(out) == {1: (1, 2), 2: (3, 4), 3: (5, 8), 4: (9, 12),
                           5: (13, 16), 6: (17, 19)}
    # and the slash synthesis the fallback exists to protect is intact
    assert sum(1 for x in out.layout.elements
               if x.identity.kind is ElementKind.SLASH) == 52


def test_a_break_isolating_a_slash_measure_keeps_hiding() -> None:
    """THE regression the region fill exists for (2026-08-09): a user
    break that isolates a slash measure into its own system used to
    trip the rule-10 fallback and silently un-hide the WHOLE score —
    every system snapped back to all 8 staves. With the fill, hiding
    stays per-system and no fallback fires."""
    out = _load(VIDEO_SCORE, hide_empty_staves=True, strict=False,
                system_breaks={21: SystemBreak.FORCE})
    assert "hide-unavailable" not in {w.code for w in out.warnings}
    by_system: dict[int, set] = {}
    for e in out.layout.elements:
        if e.identity.kind is ElementKind.STAFF_LINES:
            by_system.setdefault(e.system, set()).add(
                (e.identity.part, e.identity.staff))
    rows = [len(by_system[s]) for s in sorted(by_system)]
    # non-vacuous: hiding genuinely ran (before the fill, every row
    # read 8), and the forced break took (one system more than the 15
    # the encoded layout carries)
    assert any(r < 8 for r in rows)
    assert len(rows) == 16


# ---------------------------------------------------------------------------
# bigband1 (app path — strict raises on 'gliss'), spike §3.3 C1/C2
# ---------------------------------------------------------------------------

def test_bigband_force_and_suppress_with_hiding_on() -> None:
    """C2: hide_empty_staves ON, both directions honored, and hiding is
    still APPLIED (no hide-unavailable fallback) — the break edit does
    not cost the score its hidden staves."""
    flat_force = _load(BIGBAND_SCORE, strict=False,
                       system_breaks={3: SystemBreak.FORCE})
    hidden_force = _load(BIGBAND_SCORE, strict=False, hide_empty_staves=True,
                         system_breaks={3: SystemBreak.FORCE})
    hidden_suppress = _load(BIGBAND_SCORE, strict=False,
                            hide_empty_staves=True,
                            system_breaks={5: SystemBreak.SUPPRESS})

    assert _spans(hidden_force)[1] == (1, 2)         # the forced split
    assert _spans(hidden_force) == _spans(flat_force)
    assert _spans(hidden_suppress)[1] == (1, 8)      # m5's break gone
    for out in (hidden_force, hidden_suppress):
        assert "hide-unavailable" not in {w.code for w in out.warnings}


def test_bigband_warning_set_does_not_grow_beyond_the_spike() -> None:
    """The one thing §3.3 flagged to watch: C2's force-m3 run emits
    spanner-attribution diagnostics the flat run does not, as a
    hidden-staff system re-lays out. Expected under flag-and-continue —
    pinned at the counts the spike recorded so a real leak would show."""
    out = _load(BIGBAND_SCORE, strict=False, hide_empty_staves=True,
                system_breaks={3: SystemBreak.FORCE})
    counts = Counter(w.code for w in out.warnings)
    assert counts["segment-count-mismatch"] == 1
    assert counts["unattributed-continuation"] == 1
    assert counts["unknown-class"] == 3              # the 'gliss' class
    assert set(counts) == {"dropped-spanner", "unknown-class", "stray-path",
                           "reclaimed-spanner-ink", "segment-count-mismatch",
                           "unattributed-continuation", "repaginated"}


# ---------------------------------------------------------------------------
# M5.7 — the move-up composition, end to end (brief §M5.7.2)
# ---------------------------------------------------------------------------

def test_move_up_composition_lands_on_testscore() -> None:
    """The policy's entry set for "move m6 to the previous system",
    through the whole pipeline: m5-6 join system 1 and the remainder
    m7-8 stays a system of its own."""
    out = _load(TESTSCORE, system_breaks={5: SystemBreak.SUPPRESS,
                                          7: SystemBreak.FORCE})
    assert _spans(out) == {1: (1, 6), 2: (7, 8), 3: (9, 12), 4: (13, 16),
                           5: (17, 19)}
    assert "break-override-inert" not in {w.code for w in out.warnings}


def test_move_up_of_a_last_measure_needs_only_the_merge_half() -> None:
    """Why D11 omits an entry rather than writing it for symmetry: m9
    already encodes new-system="yes", so a FORCE there rewrites nothing
    at the seam and D10 reports an override that had no effect — for a
    gesture that worked. The merge half alone gives the same layout."""
    merge_only = _load(TESTSCORE, system_breaks={5: SystemBreak.SUPPRESS})
    with_split = _load(TESTSCORE, system_breaks={5: SystemBreak.SUPPRESS,
                                                 9: SystemBreak.FORCE})
    assert _spans(with_split) == _spans(merge_only)
    assert "break-override-inert" not in {w.code for w in merge_only.warnings}
    assert "break-override-inert" in {w.code for w in with_split.warnings}


def test_move_up_on_bigband_leaves_the_rest_of_the_score_alone() -> None:
    """The M5.7 exit check, on the app path: a mid-system bar moves up,
    the remainder stays a system of its own, systems 3-9 are untouched,
    and the warning set is IDENTICAL to the baseline load — no
    repagination, no new spanner diagnostics."""
    base = _load(BIGBAND_SCORE, strict=False)
    assert _spans(base)[2] == (5, 8) and _spans(base)[3] == (9, 11)

    out = _load(BIGBAND_SCORE, strict=False,
                system_breaks={5: SystemBreak.SUPPRESS,
                               7: SystemBreak.FORCE})
    assert _spans(out)[1] == (1, 6) and _spans(out)[2] == (7, 8)
    assert {s: span for s, span in _spans(out).items() if s >= 3} \
        == {s: span for s, span in _spans(base).items() if s >= 3}
    assert Counter(w.code for w in out.warnings) \
        == Counter(w.code for w in base.warnings)


def test_move_up_leaves_a_one_measure_remainder_when_that_is_what_it_is() -> None:
    """bigband1 system 3 is m9-11: moving m10 up leaves m11 alone on its
    own system. Ugly, and exactly what was asked for."""
    out = _load(BIGBAND_SCORE, strict=False,
                system_breaks={9: SystemBreak.SUPPRESS,
                               11: SystemBreak.FORCE})
    assert _spans(out)[2] == (5, 10) and _spans(out)[3] == (11, 11)
