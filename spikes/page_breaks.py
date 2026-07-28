"""M6 spike — page-break authoring at the prep seam.

M5 proved the pattern for SYSTEM breaks: stored sparse intent, a
`<print>` rewrite on part 1 before Verovio, everything downstream
operating on the edited set. Page breaks look like the same problem and
are not, for one reason:

    **the app already OWNS the page-break set.**

Rule 7(a)'s never-clip repagination re-derives page breaks whenever a
system would overflow, and `_repaginate` implements that by STRIPPING
every encoded `new-page` and asserting its own plan. So a user's page
intent written upstream of it is destroyed exactly when the guard fires,
and a user's SUPPRESS can be what makes it fire. That collision is what
this spike measures.

Six sections:

  A  Does Verovio honor a forced / suppressed page break at all?
  B  How does user page intent compose with rule-7(a) repagination?
     THREE candidate designs, measured side by side.
  C  ElementId and beat stability under a page edit (rule 12).
  D  The collision matrix between the two override maps at one ordinal.
  E  The downstream sweep re-run for pages: hide-empty-staves,
     condensing, scale-to-fit, warning sets, re-engrave cost.
  F  BACKLOG 16: promote encoded new-page to new-system before the
     strip — is it a no-op on the fixtures, and does it make B tractable?

`bigband1` and `complex2`/`complex3` go through the APP path
(strict=False); `bigband1` raises `unknown SVG class 'gliss'` under
strict (ROADMAP §M5 fixture caveat). `testscore` loads strict.

Run: python spikes/page_breaks.py          (everything, slow)
     python spikes/page_breaks.py a b      (named sections only)
"""
from __future__ import annotations

import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoreanim.core.animation import (build_reveal_tracks,  # noqa: E402
                                      build_trigger_schedule,
                                      resolve_durations)
from scoreanim.core.engraving.systems import system_bands
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.engraving.verovio import provider as vprovider
from scoreanim.core.score import musicxml_prep
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.model import build_score_model
from scoreanim.core.score.musicxml_prep import SystemBreak
from scoreanim.core.selection.policy import measure_ordinal_of

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spikes" / "out"
TESTSCORE = ROOT / "testdata" / "testscore.musicxml"
BIGBAND = ROOT / "testdata" / "bigband1.musicxml"
COMPLEX2 = ROOT / "testdata" / "complex2.musicxml"
COMPLEX3 = ROOT / "testdata" / "complex3.musicxml"
TALL = ROOT / "testdata" / "tall_system_min.musicxml"

FORCE = "force"
SUPPRESS = "suppress"


# ---------------------------------------------------------------------------
# The prototype pass — the twin of `_apply_system_breaks` M6 would add.
# ---------------------------------------------------------------------------

def _apply_page_breaks(root: ET.Element, overrides: dict[int, str]) -> None:
    """Part 1 only, keyed by 1-based document ordinal, creating <print>
    when absent — `_repaginate`'s and `_apply_system_breaks`' shape.

    FORCE sets new-page="yes" AND new-system="yes": a page break implies
    a system start, and Verovio's break-respect mode wants both said (D3
    territory — section D measures whether the pair is required or
    merely tidy).  SUPPRESS clears new-page only, leaving any system
    break standing: "same system flow, don't start a page here".
    """
    if not overrides:
        return
    parts = root.findall("part")
    if not parts:
        return
    for ordinal, measure in enumerate(parts[0].findall("measure"), start=1):
        mode = overrides.get(ordinal)
        if mode is None:
            continue
        pr = measure.find("print")
        if mode == FORCE:
            if pr is None:
                pr = ET.Element("print")
                measure.insert(0, pr)
            pr.set("new-page", "yes")
            pr.set("new-system", "yes")
        elif mode == SUPPRESS:
            if pr is not None and pr.get("new-page") == "yes":
                pr.set("new-page", "no")
        else:
            raise ValueError(mode)


def _promote_page_to_system(root: ET.Element) -> int:
    """BACKLOG 16's proposed fix, as a probe (section F): before anything
    can strip new-page, say the system break it implies out loud."""
    promoted = 0
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            pr = measure.find("print")
            if pr is not None and pr.get("new-page") == "yes" \
                    and pr.get("new-system") != "yes":
                pr.set("new-system", "yes")
                promoted += 1
    return promoted


# ---------------------------------------------------------------------------
# The three candidate designs for composing with rule-7(a) repagination
# ---------------------------------------------------------------------------
#
#   "pre"   the naive M5 twin: the page pass runs where the system pass
#           runs, i.e. BEFORE _repaginate. Whatever _repaginate does to
#           it, it does.
#   "post"  the page pass runs AFTER _repaginate, over its output, so
#           user intent always wins. (Modelled by rewriting the prepared
#           canonical XML — a real build would reorder the passes.)
#   "plan"  user intent is an INPUT to plan_page_breaks: forced ordinals
#           are unioned into the never-clip plan, suppressed ones are
#           dropped from it unless dropping would clip.
#
# Each is a `mode=` to `load()`, so B can measure all three on one score.
# ---------------------------------------------------------------------------

def _patch_prepare(page_overrides: dict[int, str], mode: str,
                   promote: bool = False):
    real = musicxml_prep.prepare

    def patched(score_path, groups=(), texts=(), condense=(),
                page_break_measures=(), system_breaks=None):
        if mode == "post":
            prep = real(score_path, groups, texts, condense,
                        page_break_measures, system_breaks)
            root = ET.fromstring(prep.canonical_xml)
            _apply_page_breaks(root, page_overrides)
            return replace(prep,
                           canonical_xml=ET.tostring(root, encoding="unicode"))
        root = ET.fromstring(Path(score_path).read_bytes())
        if promote:
            _promote_page_to_system(root)
        _apply_page_breaks(root, page_overrides)
        OUT.mkdir(parents=True, exist_ok=True)
        tmp = OUT / f"_pg_{Path(score_path).stem}.musicxml"
        tmp.write_bytes(ET.tostring(root, encoding="utf-8",
                                    xml_declaration=True))
        return real(tmp, groups, texts, condense, page_break_measures,
                    system_breaks)

    return real, patched


def _patch_plan(page_overrides: dict[int, str]):
    """The "plan" design: the never-clip planner is told about user
    intent instead of overwriting it."""
    real = vprovider.plan_page_breaks
    forced = {m for m, v in page_overrides.items() if v == FORCE}
    suppressed = {m for m, v in page_overrides.items() if v == SUPPRESS}

    def patched(bands, page_height, first_measure_by_system):
        plan = set(real(bands, page_height, first_measure_by_system))
        # never-clip owns the plan: a suppression is honored only where
        # the planner did not need that break.
        kept = (plan - suppressed) | (forced & set(
            first_measure_by_system.values()))
        return tuple(sorted(kept))

    return real, patched


def load(path: Path, page_overrides: dict[int, str] | None = None,
         mode: str = "pre", system_breaks: dict[int, SystemBreak] | None = None,
         promote: bool = False, strict: bool = False, **kw):
    """One full load with the given page overrides under one design."""
    page_overrides = page_overrides or {}
    real_prep, patched_prep = _patch_prepare(page_overrides, mode, promote)
    real_plan, patched_plan = _patch_plan(page_overrides)
    musicxml_prep.prepare = patched_prep
    vprovider.prepare = patched_prep
    if mode == "plan":
        vprovider.plan_page_breaks = patched_plan
    try:
        return VerovioEngravingProvider().load_detailed(
            path, EngravingParams(), strict=strict,
            system_breaks=system_breaks, **kw)
    finally:
        musicxml_prep.prepare = real_prep
        vprovider.prepare = real_prep
        vprovider.plan_page_breaks = real_plan


# ---------------------------------------------------------------------------
# helpers over an EngravedScore
# ---------------------------------------------------------------------------

def system_of_measure(engraved) -> dict[int, int]:
    return dict(sorted(engraved.system_of_measure.items()))


def systems(engraved) -> dict[int, tuple[int, int]]:
    """system → (first measure, last measure) — compact enough to diff."""
    out: dict[int, list[int]] = defaultdict(list)
    for m, s in system_of_measure(engraved).items():
        out[s].append(m)
    return {s: (min(v), max(v)) for s, v in sorted(out.items())}


def page_of_system(engraved) -> dict[int, int]:
    return {b.system: b.page for b in system_bands(engraved.layout)}


def pages_of_measure(engraved) -> dict[int, int]:
    """measure → page, derived the way the APP can derive it: through
    system_of_measure and the system bands. No adapter change needed."""
    pos = page_of_system(engraved)
    return {m: pos[s] for m, s in system_of_measure(engraved).items()
            if s in pos}


def page_starts(engraved) -> tuple[int, ...]:
    """The measure ordinals that START a page — the set a page-break
    override map is a delta on."""
    first: dict[int, int] = {}
    for m, p in pages_of_measure(engraved).items():
        first[p] = min(first.get(p, 1 << 30), m)
    return tuple(v for _, v in sorted(first.items()))


def clipped(engraved) -> list[int]:
    """Systems whose ink runs past the bottom of their page — the
    never-clip guarantee, checked rather than trusted."""
    ph = engraved.layout.pages[0].height
    return [b.system for b in system_bands(engraved.layout)
            if b.rect.y + b.rect.h > ph + 0.5]


def warnings_of(engraved) -> list[str]:
    return [w.code for w in engraved.warnings]


def ids_by_measure(engraved) -> dict[int | None, set[str]]:
    out: dict[int | None, set[str]] = defaultdict(set)
    for el in engraved.layout.elements:
        eid = str(el.identity.element_id)
        out[measure_ordinal_of(eid)].add(eid)
    return out


def animation(engraved):
    model = build_score_model(engraved.prepared, engraved.timeline)
    report = join_notes(model, engraved.note_records)
    durations = resolve_durations(engraved.layout, report.mapping,
                                  engraved.note_durations, model.measures)
    schedule = build_trigger_schedule(engraved.layout, report.mapping,
                                      model.measures, durations)
    score_end = max((m.start + m.quarter_length for m in model.measures),
                    default=0.0)
    tracks = build_reveal_tracks(engraved.layout, schedule, score_end)
    return report, schedule, tracks


def encoded_prints(path: Path) -> dict[int, dict[str, str]]:
    """What part 1 of a fixture actually encodes, per ordinal — the
    ground truth every "is this measure a page start" claim rests on."""
    root = ET.fromstring(path.read_bytes())
    part = root.find("part")
    out: dict[int, dict[str, str]] = {}
    for ordinal, measure in enumerate(part.findall("measure"), start=1):
        pr = measure.find("print")
        if pr is None:
            continue
        attrs = {k: v for k, v in pr.attrib.items()
                 if k in ("new-system", "new-page") and v == "yes"}
        if attrs:
            out[ordinal] = attrs
    return out


def describe(label: str, engraved) -> None:
    print(f"   {label:<28} pages={len(engraved.layout.pages)} "
          f"page_starts={page_starts(engraved)} "
          f"systems={len(systems(engraved))} "
          f"clipped={clipped(engraved)} warnings={warnings_of(engraved)}")


def hr(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


# ---------------------------------------------------------------------------
# A — does Verovio honor an authored page break?
# ---------------------------------------------------------------------------

def section_a() -> dict:
    hr("A — Verovio honors forced and suppressed page breaks (testscore)")
    print(f"A0 encoded <print> on part 1: {encoded_prints(TESTSCORE)}")
    base = load(TESTSCORE, strict=True)
    describe("baseline", base)
    print(f"   systems={systems(base)}")
    print(f"   pages_of_measure={pages_of_measure(base)}")

    cases = {
        "A1 force page at m3 (mid-system)": {3: FORCE},
        "A2 force page at m9 (a system start)": {9: FORCE},
        "A3 suppress encoded page at m5": {5: SUPPRESS},
        "A4 suppress encoded page at m13": {13: SUPPRESS},
        "A5 suppress at m9 (no encoded page)": {9: SUPPRESS},
        "A6 force m3 + suppress m13": {3: FORCE, 13: SUPPRESS},
    }
    out = {}
    for label, ov in cases.items():
        ed = load(TESTSCORE, ov, strict=True)
        print(f"\n{label}")
        describe("->", ed)
        print(f"   systems={systems(ed)}")
        out[label.split()[0]] = ed

    print(f"\nA7 force past the end (ordinal 20 of 19): ")
    past = load(TESTSCORE, {20: FORCE}, strict=True)
    describe("->", past)
    print(f"   identical to baseline: "
          f"{page_starts(past) == page_starts(base)}")
    return {"base": base, **out}


# ---------------------------------------------------------------------------
# B — composition with rule-7(a) repagination  (THE sharp question)
# ---------------------------------------------------------------------------

def section_b() -> None:
    hr("B — user page intent vs rule-7(a) never-clip repagination")

    print("B0 which fixtures repaginate at BASELINE (so the collision is "
          "reachable at all)")
    for name, path, strict in (("testscore", TESTSCORE, True),
                               ("bigband1", BIGBAND, False),
                               ("complex2", COMPLEX2, False),
                               ("complex3", COMPLEX3, False),
                               ("tall_system_min", TALL, False)):
        try:
            e = load(path, strict=strict)
            print(f"   {name:<16} {warnings_of(e)}  pages="
                  f"{len(e.layout.pages)} page_starts={page_starts(e)}")
        except Exception as exc:                              # noqa: BLE001
            print(f"   {name:<16} FAILED {type(exc).__name__}: {exc}")

    print("\nB1 does a FORCE survive a load that repaginates?")
    print("   (complex3 repaginates at baseline; testscore is pushed into "
          "it with a system FORCE at m19 — the M5 finding)")
    # NB: the forced ordinal must NOT already start a page at baseline,
    # or "HONORED" is vacuous. complex3 starts pages at 6/11/16/…, so
    # probe 8; complex2 starts at 11/19/…, so probe 6.
    for name, path, ov, sysbrk, strict in (
            ("complex3", COMPLEX3, {8: FORCE}, None, False),
            ("testscore+sysbrk", TESTSCORE, {3: FORCE},
             {19: SystemBreak.FORCE}, True),
            ("complex2", COMPLEX2, {6: FORCE}, None, False)):
        print(f"\n   -- {name}, page FORCE at {sorted(ov)} --")
        for mode in ("pre", "post", "plan"):
            try:
                e = load(path, ov, mode=mode, system_breaks=sysbrk,
                         strict=strict)
                honored = all(m in page_starts(e) for m in ov)
                print(f"      {mode:<5} page_starts={page_starts(e)} "
                      f"HONORED={honored} clipped={clipped(e)} "
                      f"warnings={warnings_of(e)}")
            except Exception as exc:                          # noqa: BLE001
                print(f"      {mode:<5} FAILED {type(exc).__name__}: {exc}")

    print("\nB2 does a SUPPRESS that CREATES overflow get overridden?")
    print("   (suppress every encoded page break, so all systems pile onto "
          "page 1 — never-clip must win)")
    for name, path, strict in (("testscore", TESTSCORE, True),
                               ("bigband1", BIGBAND, False),
                               ("complex3", COMPLEX3, False)):
        enc = [m for m, a in encoded_prints(path).items()
               if a.get("new-page") == "yes"]
        ov = {m: SUPPRESS for m in enc}
        print(f"\n   -- {name}, SUPPRESS all encoded page breaks {enc} --")
        for mode in ("pre", "post", "plan"):
            try:
                e = load(path, ov, mode=mode, strict=strict)
                re_added = sorted(set(page_starts(e)) & set(enc))
                print(f"      {mode:<5} pages={len(e.layout.pages)} "
                      f"page_starts={page_starts(e)} "
                      f"suppressed-but-back={re_added} "
                      f"clipped={clipped(e)} warnings={warnings_of(e)}")
            except Exception as exc:                          # noqa: BLE001
                print(f"      {mode:<5} FAILED {type(exc).__name__}: {exc}")

    print("\nB3 WHERE a 'pre' FORCE is lost: is it the strip in _repaginate?")
    print("   Probed on the case B1 shows DIVERGING (testscore + a system "
          "FORCE at m19, which repaginates into a plan unlike the encoded "
          "set). On complex3 the re-derived plan happens to equal the "
          "encoded one — BACKLOG 16's latency condition — so the strip "
          "there is a no-op in effect and proves nothing.")
    real_rep = musicxml_prep._repaginate
    seen: list[tuple] = []

    def spy(root, break_measures):
        before = sorted(
            o for o, m in enumerate(root.findall("part")[0].findall("measure"),
                                    start=1)
            if (m.find("print") is not None
                and m.find("print").get("new-page") == "yes"))
        real_rep(root, break_measures)
        after = sorted(
            o for o, m in enumerate(root.findall("part")[0].findall("measure"),
                                    start=1)
            if (m.find("print") is not None
                and m.find("print").get("new-page") == "yes"))
        seen.append((before, tuple(break_measures), after))

    musicxml_prep._repaginate = spy
    try:
        load(TESTSCORE, {3: FORCE}, mode="pre",
             system_breaks={19: SystemBreak.FORCE}, strict=True)
    finally:
        musicxml_prep._repaginate = real_rep
    for before, plan, after in seen:
        print(f"   _repaginate: new-page before={before} plan={plan} "
              f"after={after}")
        print(f"      user's forced page at m3 survived: {3 in after}")


# ---------------------------------------------------------------------------
# C — id and beat stability (rule 12)
# ---------------------------------------------------------------------------

def section_c(a: dict) -> None:
    hr("C — ElementId and beat stability under a page edit (rule 12)")
    base = a["base"]
    for label, edited in (("force page m3", a.get("A1")),
                          ("suppress page m5", a.get("A3"))):
        if edited is None:
            continue
        b, e = ids_by_measure(base), ids_by_measure(edited)
        all_m = sorted((set(b) | set(e)) - {None})
        same = [m for m in all_m if b.get(m, set()) == e.get(m, set())]
        diff = [m for m in all_m if m not in same]
        print(f"\nC1 {label}")
        print(f"   measures with byte-identical id sets: "
              f"{len(same)}/{len(all_m)}   differing: {diff}")
        for m in diff[:3]:
            print(f"     m{m}: -{sorted(b.get(m, set()) - e.get(m, set()))[:3]}"
                  f" +{sorted(e.get(m, set()) - b.get(m, set()))[:3]}")
        pb, pe = b.get(None, set()), e.get(None, set())
        print(f"   page-scoped (measure-less) ids: {len(pb)} -> {len(pe)} "
              f"identical={pb == pe}  (shift is the rule-7(a) precedent)")

        _, bs, bt = animation(base)
        _, es, et = animation(edited)
        bk, ek = dict(bs.beats_by_element), dict(es.beats_by_element)
        moved = [k for k in set(bk) & set(ek) if bk[k] != ek[k]]
        print(f"   triggers {len(bs.triggers)} -> {len(es.triggers)}; "
              f"score_end {base.timeline.score_end} -> "
              f"{edited.timeline.score_end}")
        print(f"   shared ids with a CHANGED beat: {len(moved)} "
              f"{[str(x) for x in moved[:3]]}")
        bad = [t.system for t in et
               if [x for _, x in getattr(t, 'anchors', [])]
               != sorted(x for _, x in getattr(t, 'anchors', []))]
        print(f"   reveal tracks {len(bt)} -> {len(et)}; "
              f"non-monotonic edge x: {len(bad)}")


# ---------------------------------------------------------------------------
# D — the collision matrix
# ---------------------------------------------------------------------------

def section_d() -> None:
    hr("D — the two override maps at the SAME ordinal")
    print("Both maps are keyed by measure ordinal, so every combination is "
          "reachable. A page break implies a system start, and M5's D7 "
          "already couples them one way (system SUPPRESS clears new-page).")
    enc = encoded_prints(TESTSCORE)
    print(f"testscore encoded: {enc}")

    # m9 encodes new-system="yes"; m5/m13 encode new-page="yes"
    matrix = [
        ("sysFORCE + pgFORCE   @m3", {3: SystemBreak.FORCE}, {3: FORCE}),
        ("sysSUPPRESS + pgFORCE@m9", {9: SystemBreak.SUPPRESS}, {9: FORCE}),
        ("sysFORCE + pgSUPPRESS@m3", {3: SystemBreak.FORCE}, {3: SUPPRESS}),
        ("sysSUPPRESS+pgSUPPRESS@m5", {5: SystemBreak.SUPPRESS}, {5: SUPPRESS}),
        ("sysSUPPRESS @m5 alone", {5: SystemBreak.SUPPRESS}, {}),
        ("pgFORCE @m5 alone", None, {5: FORCE}),
    ]
    base = load(TESTSCORE, strict=True)
    print(f"\nbaseline: systems={systems(base)} "
          f"page_starts={page_starts(base)}")
    for label, sysbrk, pgbrk in matrix:
        for mode in ("pre", "post"):
            try:
                e = load(TESTSCORE, pgbrk, mode=mode, system_breaks=sysbrk,
                         strict=True)
                ords = sorted(set(pgbrk) | set(sysbrk or {}))
                starts_sys = [m for m in ords
                              if m in {v[0] for v in systems(e).values()}]
                starts_pg = [m for m in ords if m in page_starts(e)]
                print(f"\n   {label} [{mode}]")
                print(f"      starts a system: {starts_sys}   "
                      f"starts a page: {starts_pg}")
                print(f"      systems={systems(e)}")
                print(f"      page_starts={page_starts(e)} "
                      f"clipped={clipped(e)} warnings={warnings_of(e)}")
            except Exception as exc:                          # noqa: BLE001
                print(f"   {label} [{mode}] FAILED "
                      f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# E — the downstream sweep, re-run for pages
# ---------------------------------------------------------------------------

def section_e() -> None:
    hr("E — downstream: hide-empty-staves, condensing, scale-to-fit, cost")

    print("E1 bigband1 (app path) + hide_empty_staves")
    enc = [m for m, a in encoded_prints(BIGBAND).items()
           if a.get("new-page") == "yes"]
    print(f"   encoded page breaks: {enc}")
    for hide in (False, True):
        print(f"   -- hide_empty_staves={hide} --")
        describe("baseline", load(BIGBAND, hide_empty_staves=hide))
        describe("force page m7", load(BIGBAND, {7: FORCE},
                                       hide_empty_staves=hide))
        if enc:
            describe(f"suppress page m{enc[0]}",
                     load(BIGBAND, {enc[0]: SUPPRESS},
                          hide_empty_staves=hide))

    print("\nE2 complex2 + condensing + a page break (scale-to-fit lives here)")
    from scoreanim.core.score.musicxml_prep import PartCondenseSpec
    try:
        root = ET.fromstring(COMPLEX2.read_bytes())
        pids = [sp.get("id") for sp in root.findall("./part-list/score-part")]
        spec = (PartCondenseSpec(parts=(pids[0], pids[1]), name="Condensed",
                                 abbreviation="Cond."),)
        describe("condensed baseline", load(COMPLEX2, condense=spec))
        describe("condensed + page m6",
                 load(COMPLEX2, {6: FORCE}, condense=spec))
        describe("condensed + page m6 [plan]",
                 load(COMPLEX2, {6: FORCE}, mode="plan", condense=spec))
    except Exception as exc:                                  # noqa: BLE001
        print(f"   SKIPPED/FAILED: {type(exc).__name__}: {exc}")

    print("\nE3 tall_system_min — the scale-to-fit fixture, with a page break")
    try:
        describe("baseline", load(TALL))
        describe("force page m2", load(TALL, {2: FORCE}))
    except Exception as exc:                                  # noqa: BLE001
        print(f"   SKIPPED/FAILED: {type(exc).__name__}: {exc}")

    print("\nE4 re-engrave cost of one page toggle (full load_detailed)")
    for name, path, strict in (("testscore", TESTSCORE, True),
                               ("bigband1", BIGBAND, False)):
        t0 = time.perf_counter()
        load(path, {3: FORCE}, strict=strict)
        print(f"   {name}: {time.perf_counter() - t0:.2f}s")


# ---------------------------------------------------------------------------
# F — BACKLOG 16
# ---------------------------------------------------------------------------

def section_f() -> None:
    hr("F — BACKLOG 16: promote encoded new-page to new-system before "
       "the strip")
    print("The claim: _repaginate strips ALL new-page, so a measure whose "
          "ONLY break marker was new-page loses its system break whenever "
          "the re-derived plan differs from the encoded one.")
    for name, path in (("testscore", TESTSCORE), ("bigband1", BIGBAND),
                       ("complex3", COMPLEX3)):
        enc = encoded_prints(path)
        page_only = [m for m, a in enc.items()
                     if a.get("new-page") == "yes"
                     and a.get("new-system") != "yes"]
        print(f"   {name:<12} page-only break markers: {page_only}")

    print("\nF1 does promotion change anything at BASELINE? "
          "(must be a no-op or the goldens move)")
    for name, path, strict in (("testscore", TESTSCORE, True),
                               ("bigband1", BIGBAND, False),
                               ("complex2", COMPLEX2, False),
                               ("complex3", COMPLEX3, False)):
        try:
            plain = load(path, strict=strict)
            promoted = load(path, promote=True, strict=strict)
            same_sys = systems(plain) == systems(promoted)
            same_pg = page_starts(plain) == page_starts(promoted)
            same_ids = ({str(e.identity.element_id)
                         for e in plain.layout.elements}
                        == {str(e.identity.element_id)
                            for e in promoted.layout.elements})
            print(f"   {name:<12} systems_same={same_sys} "
                  f"pages_same={same_pg} ids_same={same_ids} "
                  f"warnings={warnings_of(promoted)}")
            if not same_sys:
                print(f"      plain   ={systems(plain)}")
                print(f"      promoted={systems(promoted)}")
        except Exception as exc:                              # noqa: BLE001
            print(f"   {name:<12} FAILED {type(exc).__name__}: {exc}")

    print("\nF2 the M5 case: system FORCE at testscore m19 repaginates and "
          "merges systems whose breaks are page-encoded")
    for promote in (False, True):
        e = load(TESTSCORE, system_breaks={19: SystemBreak.FORCE},
                 promote=promote, strict=True)
        print(f"   promote={promote}: systems={systems(e)}")
        print(f"      page_starts={page_starts(e)} "
              f"warnings={warnings_of(e)}")

    print("\nF3 does promotion make B1 tractable? "
          "(page FORCE through a repaginating load; m8 on complex3 and m3 "
          "on the testscore case — neither already starts a page)")
    for mode in ("pre", "plan"):
        e = load(COMPLEX3, {8: FORCE}, mode=mode, promote=True)
        print(f"   complex3 [{mode}] promote=True: "
              f"HONORED={8 in page_starts(e)} "
              f"clipped={clipped(e)} warnings={warnings_of(e)}")
    for mode in ("pre", "plan"):
        e = load(TESTSCORE, {3: FORCE}, mode=mode, promote=True,
                 system_breaks={19: SystemBreak.FORCE}, strict=True)
        print(f"   testscore+sysbrk [{mode}] promote=True: "
              f"page_starts={page_starts(e)} HONORED={3 in page_starts(e)} "
              f"systems={systems(e)}")


SECTIONS = {"a": section_a, "b": section_b, "c": section_c,
            "d": section_d, "e": section_e, "f": section_f}


def main() -> int:
    wanted = [s.lower() for s in sys.argv[1:]] or list(SECTIONS)
    a: dict = {}
    if "a" in wanted or "c" in wanted:
        a = section_a()
    for name in wanted:
        if name == "a":
            continue
        fn = SECTIONS.get(name)
        if fn is None:
            print(f"unknown section {name!r}; have {sorted(SECTIONS)}")
            continue
        fn(a) if name == "c" else fn()
    print("\ndone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
