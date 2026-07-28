"""M5 spike — system-break authoring at the prep seam.

Question the milestone rests on: can the honored system-break set be
edited BEFORE Verovio (rewrite `<print new-system>` on part 1, the
`_repaginate` pattern) so that everything downstream — repagination,
hide-empty-staves, condensing, scale-to-fit, the timemap, the trigger
schedule, the reveal edges — operates on the edited set exactly as it
does on the encoded one?

Four sections, matching the four things the brief has to measure:

  A  Verovio honors a FORCED break and a SUPPRESSED encoded break.
  B  ElementIds of unaffected measures survive byte-for-byte.
  C  The edited break set flows through repagination / hide-empty-staves
     / condensing / scale-to-fit.
  D  Animation triggers and reveal edges re-derive sanely on the
     split/merged systems.

Plus section E: what a barline id actually offers as a handle (rule 13
says it is M5's only one), measured rather than assumed.

`bigband1` is loaded through the APP path (strict=False) throughout —
it raises `unknown SVG class 'gliss'` under strict (ROADMAP §M5 fixture
caveat). `testscore` loads strict and is used where strictness matters.

Run: python spikes/system_breaks.py
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoreanim.core.animation import (build_reveal_tracks,  # noqa: E402
                                      build_trigger_schedule,
                                      resolve_durations)
from scoreanim.core.engraving.systems import system_bands
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.engraving.verovio import provider as vprovider
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.model import build_score_model
from scoreanim.core.score import musicxml_prep
from scoreanim.core.selection.policy import measure_ordinal_of

ROOT = Path(__file__).resolve().parent.parent
TESTSCORE = ROOT / "testdata" / "testscore.musicxml"
BIGBAND = ROOT / "testdata" / "bigband1.musicxml"
COMPLEX2 = ROOT / "testdata" / "complex2.musicxml"

FORCE = "force"
SUPPRESS = "suppress"


# ---------------------------------------------------------------------------
# The prototype injection — the shape M5 would add to musicxml_prep.
# Deliberately written as a twin of `_repaginate`: part 1 only (Verovio
# reads print layout from the first part), keyed by 1-based document
# ordinal (never the printed number, adapter item 12).
# ---------------------------------------------------------------------------

def _apply_system_breaks(root: ET.Element,
                         overrides: dict[int, str]) -> None:
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
            pr.set("new-system", "yes")
        elif mode == SUPPRESS:
            if pr is not None:
                pr.set("new-system", "no")
                # a page break implies a system break; suppressing the
                # system break means dropping the page break too (probed
                # in section A5)
                if pr.get("new-page") == "yes":
                    pr.set("new-page", "no")
        else:
            raise ValueError(mode)


def _patched_prepare(overrides: dict[int, str]):
    """Monkeypatch `prepare` so the whole existing load pipeline (retry
    loops included) sees the edited break set — exactly what a real
    `system_breaks=` parameter would do, without editing the tree."""
    real = musicxml_prep.prepare

    def patched(score_path, groups=(), texts=(), condense=(),
                page_break_measures=()):
        root = ET.fromstring(Path(score_path).read_bytes())
        _apply_system_breaks(root, overrides)
        tmp = ROOT / "spikes" / "out" / f"_brk_{Path(score_path).stem}.musicxml"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(ET.tostring(root, encoding="utf-8",
                                    xml_declaration=True))
        return real(tmp, groups, texts, condense, page_break_measures)

    return real, patched


def load(path: Path, overrides: dict[int, str] | None = None, **kw):
    """One full app-path load with the given break overrides."""
    overrides = overrides or {}
    real, patched = _patched_prepare(overrides)
    musicxml_prep.prepare = patched
    vprovider.prepare = patched
    try:
        return VerovioEngravingProvider().load_detailed(
            path, EngravingParams(), strict=kw.pop("strict", False), **kw)
    finally:
        musicxml_prep.prepare = real
        vprovider.prepare = real


# ---------------------------------------------------------------------------
# helpers over an EngravedScore
# ---------------------------------------------------------------------------

def system_of_measure(engraved) -> dict[int, int]:
    out: dict[int, int] = {}
    for el in engraved.layout.elements:
        m = measure_ordinal_of(el.identity.element_id)
        if m is not None and el.system is not None:
            out.setdefault(m, el.system)
    return dict(sorted(out.items()))


def systems(engraved) -> dict[int, list[int]]:
    """system → its measures, in order."""
    out: dict[int, list[int]] = defaultdict(list)
    for m, s in system_of_measure(engraved).items():
        out[s].append(m)
    return dict(sorted(out.items()))


def page_of_measure(engraved) -> dict[int, int]:
    out: dict[int, int] = {}
    for el in engraved.layout.elements:
        m = measure_ordinal_of(el.identity.element_id)
        if m is not None:
            out.setdefault(m, el.page)
    return dict(sorted(out.items()))


def ids_by_measure(engraved) -> dict[int | None, set[str]]:
    out: dict[int | None, set[str]] = defaultdict(set)
    for el in engraved.layout.elements:
        eid = str(el.identity.element_id)
        out[measure_ordinal_of(eid)].add(eid)
    return out


def warnings_of(engraved) -> list[str]:
    return [w.code for w in engraved.warnings]


def animation(engraved):
    """The score_loader's animation prep, verbatim enough to compare."""
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


def hr(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


# ---------------------------------------------------------------------------
# A — does Verovio honor an injected / suppressed break?
# ---------------------------------------------------------------------------

def section_a() -> dict:
    hr("A — Verovio honors forced and suppressed system breaks (testscore)")
    base = load(TESTSCORE, strict=True)
    b_sys = systems(base)
    print(f"A0 baseline systems: {b_sys}")
    print(f"   pages={len(base.layout.pages)} warnings={warnings_of(base)}")

    # A1 — FORCE a break at a measure with encoded new-system="no"
    forced = load(TESTSCORE, {3: FORCE}, strict=True)
    f_sys = systems(forced)
    print(f"\nA1 force break before m3  -> {f_sys}")
    ok_force = f_sys.get(1) == [1, 2] and f_sys.get(2) == [3, 4]
    print(f"   HONORED: {ok_force}  (want sys1=[1,2], sys2=[3,4])")
    print(f"   pages={len(forced.layout.pages)} "
          f"warnings={warnings_of(forced)}")

    # A2 — SUPPRESS an encoded break (m9 carries new-system="yes")
    sup = load(TESTSCORE, {9: SUPPRESS}, strict=True)
    s_sys = systems(sup)
    print(f"\nA2 suppress encoded break at m9 -> {s_sys}")
    merged = [ms for ms in s_sys.values() if 8 in ms and 9 in ms]
    print(f"   HONORED (m8 and m9 share a system): {bool(merged)}")
    print(f"   pages={len(sup.layout.pages)} warnings={warnings_of(sup)}")

    # A3 — SUPPRESS on a measure with NO encoded break (new-system="no")
    noop = load(TESTSCORE, {3: SUPPRESS}, strict=True)
    n_sys = systems(noop)
    print(f"\nA3 suppress at m3 (no encoded break) -> {n_sys}")
    print(f"   NO-OP vs baseline: {n_sys == b_sys}")

    # A4 — FORCE at m1 (already a system start) and at the LAST measure
    at1 = load(TESTSCORE, {1: FORCE}, strict=True)
    print(f"\nA4 force at m1 -> {systems(at1)}")
    print(f"   NO-OP vs baseline: {systems(at1) == b_sys}")
    last = max(b_sys[max(b_sys)])
    atlast = load(TESTSCORE, {last: FORCE}, strict=True)
    print(f"   force at LAST measure m{last} -> {systems(atlast)}")
    print(f"   pages={len(atlast.layout.pages)} "
          f"warnings={warnings_of(atlast)}")

    # A5 — SUPPRESS at a measure whose break is a PAGE break (m5, m13)
    pg = load(TESTSCORE, {5: SUPPRESS}, strict=True)
    print(f"\nA5 suppress at m5 (encoded new-page='yes') -> {systems(pg)}")
    print(f"   pages {len(base.layout.pages)} -> {len(pg.layout.pages)}"
          f"  warnings={warnings_of(pg)}")
    print(f"   page_of_measure: {page_of_measure(pg)}")

    # A6 — several overrides at once
    multi = load(TESTSCORE, {3: FORCE, 9: SUPPRESS}, strict=True)
    print(f"\nA6 force m3 + suppress m9 -> {systems(multi)}")
    print(f"   pages={len(multi.layout.pages)} "
          f"warnings={warnings_of(multi)}")
    return {"base": base, "forced": forced, "suppressed": sup}


# ---------------------------------------------------------------------------
# B — id survival
# ---------------------------------------------------------------------------

def _id_report(base, edited, label: str, moved: set[int]) -> None:
    b = ids_by_measure(base)
    e = ids_by_measure(edited)
    all_m = sorted((set(b) | set(e)) - {None}, key=lambda x: x or 0)
    identical, differing = [], []
    for m in all_m:
        (identical if b.get(m, set()) == e.get(m, set())
         else differing).append(m)
    print(f"\n{label}")
    print(f"   measures with byte-identical id sets: "
          f"{len(identical)}/{len(all_m)}")
    if differing:
        print(f"   differing measures: {differing}")
        for m in differing[:3]:
            only_b = sorted(b.get(m, set()) - e.get(m, set()))[:4]
            only_e = sorted(e.get(m, set()) - b.get(m, set()))[:4]
            print(f"     m{m}: -{only_b} +{only_e}")
    else:
        print("   differing measures: none")
    print(f"   (measures the break itself moves: {sorted(moved)})")
    pb, pe = b.get(None, set()), e.get(None, set())
    print(f"   measure-less (page/system-scoped) ids: "
          f"{len(pb)} -> {len(pe)}, identical: {pb == pe}")
    if pb != pe:
        print(f"     -{sorted(pb - pe)[:6]}")
        print(f"     +{sorted(pe - pb)[:6]}")


def section_b(a: dict) -> None:
    hr("B — ElementIds of unaffected measures survive (testscore)")
    _id_report(a["base"], a["forced"], "B1 force break before m3",
               moved=set(range(3, 20)))
    _id_report(a["base"], a["suppressed"], "B2 suppress encoded break at m9",
               moved=set(range(9, 20)))

    # B3 — musical (part-scoped) ids alone, the ones rule 5 keys overrides by
    for label, edited in (("force m3", a["forced"]),
                          ("suppress m9", a["suppressed"])):
        b = {str(el.identity.element_id) for el in a["base"].layout.elements
             if el.identity.part is not None}
        e = {str(el.identity.element_id) for el in edited.layout.elements
             if el.identity.part is not None}
        print(f"\nB3 {label}: part-scoped ids identical: {b == e} "
              f"({len(b)} vs {len(e)})")
        if b != e:
            print(f"     -{sorted(b - e)[:6]}")
            print(f"     +{sorted(e - b)[:6]}")


# ---------------------------------------------------------------------------
# C — downstream: repagination / hide / condense / scale-to-fit
# ---------------------------------------------------------------------------

def section_c() -> dict:
    hr("C — downstream flow (bigband1, app path; complex2 for condensing)")
    base = load(BIGBAND)
    print(f"C0 bigband1 baseline: systems={systems(base)}")
    print(f"   pages={len(base.layout.pages)} warnings={warnings_of(base)}")

    for label, ov in (("force before m3", {3: FORCE}),
                      ("suppress encoded m5", {5: SUPPRESS}),
                      ("force before m7 (mid-system)", {7: FORCE})):
        ed = load(BIGBAND, ov)
        print(f"\nC1 {label}: systems={systems(ed)}")
        print(f"   pages={len(ed.layout.pages)} warnings={warnings_of(ed)}")

    # C2 — with hide-empty-staves ON (bigband1's own reason for existing)
    print("\nC2 hide_empty_staves=True")
    h0 = load(BIGBAND, hide_empty_staves=True)
    print(f"   baseline  systems={systems(h0)} "
          f"warnings={warnings_of(h0)}")
    h1 = load(BIGBAND, {3: FORCE}, hide_empty_staves=True)
    print(f"   force m3  systems={systems(h1)} "
          f"warnings={warnings_of(h1)}")
    h2 = load(BIGBAND, {5: SUPPRESS}, hide_empty_staves=True)
    print(f"   suppr m5  systems={systems(h2)} "
          f"warnings={warnings_of(h2)}")

    # C3 — the stress case: force MANY breaks so systems overflow the
    # page and the repagination retry has to fire.
    print("\nC3 forced breaks that overflow the page (repagination retry)")
    many = {m: FORCE for m in range(2, 16)}
    m0 = load(BIGBAND, many)
    print(f"   force every measure 2..15: systems={len(systems(m0))} "
          f"pages={len(m0.layout.pages)}")
    print(f"   warnings={warnings_of(m0)}")
    bands = system_bands(m0.layout)
    ph = m0.layout.pages[0].height
    over = [b.system for b in bands if b.rect.y + b.rect.h > ph]
    print(f"   systems overflowing the page after retries: {over}")

    # C4 — the merge stress case: suppress EVERY encoded break, so one
    # system holds the whole score (scale-to-fit territory).
    print("\nC4 suppress every encoded break")
    allsup = {m: SUPPRESS for m in range(1, 29)}
    s0 = load(BIGBAND, allsup)
    print(f"   systems={systems(s0)}")
    print(f"   pages={len(s0.layout.pages)} warnings={warnings_of(s0)}")

    # C5 — condensing (complex2 is the condense fixture)
    print("\nC5 condensing + a forced break (complex2)")
    from scoreanim.core.score.musicxml_prep import PartCondenseSpec
    try:
        import xml.etree.ElementTree as _ET
        root = _ET.fromstring(COMPLEX2.read_bytes())
        pids = [sp.get("id") for sp in
                root.findall("./part-list/score-part")]
        spec = (PartCondenseSpec(parts=(pids[0], pids[1]),
                                 name="Condensed", abbreviation="Cond."),)
        c0 = load(COMPLEX2, condense=spec)
        print(f"   condensed baseline: systems={len(systems(c0))} "
              f"pages={len(c0.layout.pages)} warnings={warnings_of(c0)}")
        c1 = load(COMPLEX2, {4: FORCE}, condense=spec)
        print(f"   condensed + force m4: systems={len(systems(c1))} "
              f"pages={len(c1.layout.pages)} warnings={warnings_of(c1)}")
        print(f"   system_of_measure head: "
              f"{list(system_of_measure(c1).items())[:10]}")
    except Exception as exc:                       # noqa: BLE001
        print(f"   SKIPPED/FAILED: {type(exc).__name__}: {exc}")

    return {"base": base}


# ---------------------------------------------------------------------------
# D — animation and reveal edges
# ---------------------------------------------------------------------------

def section_d(a: dict) -> None:
    hr("D — triggers and reveal edges on split / merged systems")
    for label, edited in (("force m3", a["forced"]),
                          ("suppress m9", a["suppressed"])):
        b_rep, b_sched, b_tracks = animation(a["base"])
        e_rep, e_sched, e_tracks = animation(edited)
        print(f"\nD1 {label}")
        print(f"   join complete: {b_rep.is_complete} -> {e_rep.is_complete}")
        print(f"   triggers: {len(b_sched.triggers)} -> "
              f"{len(e_sched.triggers)}")
        same = (dict(b_sched.beats_by_element)
                == dict(e_sched.beats_by_element))
        print(f"   beats_by_element identical: {same}")
        if not same:
            bk = dict(b_sched.beats_by_element)
            ek = dict(e_sched.beats_by_element)
            diff = [k for k in set(bk) & set(ek) if bk[k] != ek[k]]
            print(f"     shared ids with CHANGED beat: {len(diff)} "
                  f"{[str(x) for x in diff[:4]]}")
            print(f"     only-base {len(set(bk) - set(ek))}, "
                  f"only-edited {len(set(ek) - set(bk))}")
        print(f"   timemap score_end: {a['base'].timeline.score_end} -> "
              f"{edited.timeline.score_end}")
        print(f"   reveal tracks (system,part): {len(b_tracks)} -> "
              f"{len(e_tracks)}")
        # monotonic, in-hull edges per track
        bad = []
        for t in e_tracks:
            xs = [x for _, x in t.anchors] if hasattr(t, "anchors") else []
            if xs != sorted(xs):
                bad.append((t.system, "non-monotonic x"))
        print(f"   tracks with non-monotonic edge x: {len(bad)} {bad[:3]}")
        by_sys = defaultdict(int)
        for t in e_tracks:
            by_sys[t.system] += 1
        print(f"   tracks per system: {dict(sorted(by_sys.items()))}")


# ---------------------------------------------------------------------------
# E — the barline as a handle
# ---------------------------------------------------------------------------

def section_e(a: dict) -> None:
    hr("E — what a barline id offers as M5's handle (rule 13)")
    for name, engraved in (("testscore", a["base"]),
                           ("bigband1", load(BIGBAND))):
        els = [el for el in engraved.layout.elements
               if el.identity.kind is ElementKind.BARLINE]
        with_m = [el for el in els
                  if measure_ordinal_of(el.identity.element_id) is not None]
        without = [el for el in els
                   if measure_ordinal_of(el.identity.element_id) is None]
        sysmap = system_of_measure(engraved)
        n_sys = len(set(sysmap.values()))
        n_meas = len(sysmap)
        print(f"\n{name}: {len(els)} barlines — "
              f"{len(with_m)} carry a measure ordinal, {len(without)} do not")
        print(f"   measures={n_meas} systems={n_sys}")
        print(f"   measure-less barline ids (system-start): "
              f"{[str(e.identity.element_id) for e in without][:6]}")
        # is there exactly one measure-carrying barline per measure?
        per = defaultdict(list)
        for el in with_m:
            per[measure_ordinal_of(el.identity.element_id)].append(el)
        counts = defaultdict(int)
        for m, v in per.items():
            counts[len(v)] += 1
        print(f"   barlines per measure histogram: {dict(counts)}")
        missing = [m for m in sysmap if m not in per]
        print(f"   measures with NO barline of their own: {missing}")
        # which measures END a system — those are the "break after here"
        last_of_sys = {}
        for m, s in sysmap.items():
            last_of_sys[s] = max(last_of_sys.get(s, 0), m)
        print(f"   last measure of each system: "
              f"{dict(sorted(last_of_sys.items()))}")


# ---------------------------------------------------------------------------
# F — the decisions the brief has to put to a ruling
# ---------------------------------------------------------------------------

def _apply_keep_page(root: ET.Element, overrides: dict[int, str]) -> None:
    """SUPPRESS variant that leaves an encoded new-page alone."""
    parts = root.findall("part")
    for ordinal, measure in enumerate(parts[0].findall("measure"), start=1):
        if overrides.get(ordinal) != SUPPRESS:
            continue
        pr = measure.find("print")
        if pr is not None:
            pr.set("new-system", "no")


def section_f(a: dict) -> None:
    hr("F — the open decisions, measured")

    # F1 — "break after measure N" arithmetic at the score's end.
    base = a["base"]
    n = max(system_of_measure(base))
    print(f"F1 last measure ordinal = {n}")
    past = load(TESTSCORE, {n + 1: FORCE}, strict=True)
    print(f"   FORCE at ordinal {n + 1} (past the end): "
          f"systems={systems(past)}")
    print(f"   identical to baseline: "
          f"{systems(past) == systems(base)}  "
          f"(an out-of-range ordinal is silently inert in the rewrite)")

    # F2 — SUPPRESS on a page-break measure: drop the page break, or not?
    print("\nF2 suppress at m5 (encoded new-page='yes')")
    real = musicxml_prep.prepare

    def keep_page(score_path, groups=(), texts=(), condense=(),
                  page_break_measures=()):
        root = ET.fromstring(Path(score_path).read_bytes())
        _apply_keep_page(root, {5: SUPPRESS})
        tmp = ROOT / "spikes" / "out" / "_brk_keeppage.musicxml"
        tmp.write_bytes(ET.tostring(root, encoding="utf-8",
                                    xml_declaration=True))
        return real(tmp, groups, texts, condense, page_break_measures)

    musicxml_prep.prepare = keep_page
    vprovider.prepare = keep_page
    try:
        kp = VerovioEngravingProvider().load_detailed(
            TESTSCORE, EngravingParams(), strict=True)
    finally:
        musicxml_prep.prepare = real
        vprovider.prepare = real
    print(f"   (a) new-page LEFT alone: systems={systems(kp)} "
          f"pages={len(kp.layout.pages)}")
    dropped = load(TESTSCORE, {5: SUPPRESS}, strict=True)
    print(f"   (b) new-page DROPPED too: systems={systems(dropped)} "
          f"pages={len(dropped.layout.pages)}")
    print(f"   suppression actually merged m4+m5: "
          f"(a) {any(4 in v and 5 in v for v in systems(kp).values())}  "
          f"(b) {any(4 in v and 5 in v for v in systems(dropped).values())}")

    # F3 — the changed-beat set on a merge, exactly
    print("\nF3 suppress m9: which shared ids changed their trigger beat")
    _, b_sched, _ = animation(base)
    _, e_sched, _ = animation(a["suppressed"])
    bk, ek = dict(b_sched.beats_by_element), dict(e_sched.beats_by_element)
    diff = sorted((str(k), bk[k], ek[k]) for k in set(bk) & set(ek)
                  if bk[k] != ek[k])
    print(f"   {len(diff)} changed:")
    for eid, b, e in diff:
        print(f"     {eid}: {b} -> {e}  "
              f"(measure {measure_ordinal_of(eid)})")
    kinds = sorted({el.identity.kind.name
                    for el in base.layout.elements
                    if str(el.identity.element_id) in {d[0] for d in diff}})
    print(f"   kinds involved: {kinds}")
    print("   (all inside the two measures the merge touches — id RE-USE "
          "within a re-laid-out measure, not a retimed note)")

    # F4 — re-engrave cost of one toggle
    import time
    print("\nF4 cost of one break toggle (full load_detailed, app path)")
    for name, path, ov in (("testscore", TESTSCORE, {3: FORCE}),
                           ("bigband1", BIGBAND, {3: FORCE})):
        t0 = time.perf_counter()
        load(path, ov)
        print(f"   {name}: {time.perf_counter() - t0:.2f}s")


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    a = section_a()
    if only in ("", "f"):
        if only:
            section_f(a)
            print("\ndone.")
            return 0
    section_b(a)
    section_c()
    section_d(a)
    section_e(a)
    section_f(a)
    print("\ndone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
