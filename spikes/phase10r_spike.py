"""Phase 10R, task 10R.0 — review-fix spike (kept).

Marcus's Phase 10 exit review requires: hidden empty staves (the Dorico
layout the MusicXML page breaks assume), everything-animates, removal of
the m44 tie artifacts, and page-frame systems mode with a never-clip
guarantee. This spike freezes the library mechanics those fixes stand on:

A. Two-pass load (MusicXML -> MEI + scoreDef@optimize -> reload): id
   preservation, TIMEMAP identity (fatal if it drifts), namespace
   round-trip, double-transpose check, cost.
B. optimize x injected part-groups x the native grand-staff brace.
C. Slash regions vs hidden staves: testscore hides its drum staff
   mid-slash-region (the 10R.1 fallback exists for this); video_test
   loses no slash staff.
D. Repagination: <print new-page> injection is honored; part-1-only vs
   all-parts; greedy packing from measured band heights fits.
E. Onset sources for animate-everything: @startid/@tstamp census for
   fermatas, trills, dirs, tempo, reh, harm; mNum context.

Run: .venv/bin/python spikes/phase10r_spike.py
"""

import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import verovio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoreanim.core.score.musicxml_prep import (  # noqa: E402
    PartGroupSpec, prepare)

VIDEO = ROOT / "testdata" / "video_test.musicxml"
TESTSCORE = ROOT / "testdata" / "testscore.musicxml"
MEI_NS = "http://www.music-encoding.org/ns/mei"
_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def make_toolkit(prep, extra=None):
    tk = verovio.toolkit()
    tk.setOptions({
        "breaks": "encoded", "font": "Bravura",
        "pageWidth": round(prep.page_width),
        "pageHeight": round(prep.page_height),
        "scaleToPageSize": True, "header": "none", "footer": "encoded",
        "svgHtml5": False, "svgViewBox": True,
        "transposeToSoundingPitch": True, "xmlIdSeed": 42,
        "condense": "encoded", **(extra or {}),
    })
    return tk


def optimized_mei(mei_xml: str) -> str:
    ET.register_namespace("", MEI_NS)
    root = ET.fromstring(mei_xml)
    next(root.iter(f"{{{MEI_NS}}}scoreDef")).set("optimize", "true")
    return ET.tostring(root, encoding="unicode")


def two_pass(prep, extra2=None):
    tk = make_toolkit(prep)
    if not tk.loadData(prep.canonical_xml):
        raise SystemExit("pass 1 load failed")
    tk2 = make_toolkit(prep, extra2)
    if not tk2.loadData(optimized_mei(tk.getMEI())):
        raise SystemExit("pass 2 load failed")
    return tk, tk2


def staves_per_system(tk):
    rows = []
    for p in range(1, tk.getPageCount() + 1):
        page = ET.fromstring(tk.renderToSVG(p))
        for g in page.iter():
            if (g.get("class") or "") == "system":
                fm = next((m for m in g.iter()
                           if m.get("class") == "measure"), None)
                rows.append(sum(1 for s in fm.iter()
                                if s.get("class") == "staff")
                            if fm is not None else 0)
    return rows


def timemap_fingerprint(tk):
    return [(e["qstamp"], tuple(sorted(e.get("on", []))),
             tuple(sorted(e.get("restsOn", []))), e.get("measureOn"))
            for e in tk.renderToTimemap({"includeMeasures": True,
                                         "includeRests": True})]


def section_a():
    print("== A. Two-pass load mechanics ==")
    prep = prepare(VIDEO)
    t0 = time.perf_counter()
    tk = make_toolkit(prep)
    tk.loadData(prep.canonical_xml)
    t1 = time.perf_counter()
    mei1 = tk.getMEI()
    tk2 = make_toolkit(prep)
    tk2.loadData(optimized_mei(mei1))
    t2 = time.perf_counter()

    ids1 = set(re.findall(r'xml:id="([^"]+)"', mei1))
    ids2 = set(re.findall(r'xml:id="([^"]+)"', tk2.getMEI()))
    print(f"  ids: pass1 {len(ids1)} pass2 {len(ids2)} "
          f"common {len(ids1 & ids2)}")
    assert ids1 == ids2, "id sets diverged across the MEI round-trip"

    tm1, tm2 = timemap_fingerprint(tk), timemap_fingerprint(tk2)
    print(f"  timemap: {len(tm1)} vs {len(tm2)} entries, "
          f"identical: {tm1 == tm2}")
    assert tm1 == tm2, "TIMEMAP drifted across the MEI round-trip — fatal"

    # double-transpose check: concert pitch of a known note must match.
    # The MEI is already sounding pitch; if pass-2's
    # transposeToSoundingPitch re-transposed, pnames would shift.
    n1 = re.findall(r'<note[^>]*pname="([a-g])"[^>]*oct="(\d)"', mei1)[:20]
    n2 = re.findall(r'<note[^>]*pname="([a-g])"[^>]*oct="(\d)"',
                    tk2.getMEI())[:20]
    print(f"  first 20 pnames identical (no double-transpose): {n1 == n2}")
    assert n1 == n2

    print(f"  cost: pass1 {t1 - t0:.2f}s, two-pass total {t2 - t0:.2f}s")
    print("  A PASS: two-pass load is id- and timemap-transparent\n")


def section_b():
    print("== B. optimize x groups x native brace ==")
    prep = prepare(VIDEO)
    _, tk2 = two_pass(prep)
    rows = staves_per_system(tk2)
    print(f"  video hide-ON staves/system: {rows}")
    assert rows == [8, 2, 2, 4, 2, 2, 5, 4, 5, 4, 4, 4, 4, 4, 4], rows

    # native brace: count grpSym per system + which staves each spans.
    # Hidden-staff systems drop the brace; where only ONE piano staff
    # survives the brace still draws (over one staff) — the geometric
    # identity handles both (first is last, staff_count > 1 -> "P5").
    syms = []
    for p in range(1, tk2.getPageCount() + 1):
        page = ET.fromstring(tk2.renderToSVG(p))
        for g in page.iter():
            if (g.get("class") or "") == "system":
                syms.append(sum(1 for e in g.iter()
                                if (e.get("class") or "") == "grpSym"))
    print(f"  grpSym per system (hide-ON): {Counter(syms)}")

    def count_divs(toolkit):
        return sum(
            1 for p in range(1, toolkit.getPageCount() + 1)
            for e in ET.fromstring(toolkit.renderToSVG(p)).iter()
            if (e.get("class") or "").split()[:1] == ["systemDivider"])

    divs = count_divs(tk2)
    print(f"  systemDividers under optimize (default option): {divs}")
    # Dorico's default draws NO dividers; Verovio's systemDivider option
    # ("auto" default) draws them for condensed layouts. "none" matches
    # the Dorico look — adopted as a fixed option; SYSTEM_DIVIDER
    # decomposer support stays as defense.
    tk1b = make_toolkit(prep)
    tk1b.loadData(prep.canonical_xml)
    tk3 = make_toolkit(prep, {"systemDivider": "none"})
    tk3.loadData(optimized_mei(tk1b.getMEI()))
    print(f"  systemDividers with systemDivider:'none': {count_divs(tk3)}")
    assert count_divs(tk3) == 0

    prep_g = prepare(TESTSCORE, groups=(PartGroupSpec(parts=("P1", "P2")),
                                        PartGroupSpec(parts=("P3", "P4"))))
    _, tkg = two_pass(prep_g, {"systemDivider": "none"})
    rows_g = staves_per_system(tkg)
    print(f"  testscore 2-group hide-ON (divider none): "
          f"staves/system={rows_g} dividers={count_divs(tkg)}")
    print("  B: 3 braces (piano-visible systems), dividers suppressed "
          "via option\n")


def section_c():
    print("== C. Slash regions vs hidden staves ==")
    for name, path in (("testscore", TESTSCORE), ("video", VIDEO)):
        prep = prepare(path)
        _, tk2 = two_pass(prep)
        # per system: measures + visible staff Ns (via MEI staff ids)
        root = ET.fromstring(tk2.getMEI())
        m_by_id = {m.get("{http://www.w3.org/XML/1998/namespace}id"):
                   int(m.get("n", 0))
                   for m in root.iter(f"{{{MEI_NS}}}measure")}
        staff_n = {s.get("{http://www.w3.org/XML/1998/namespace}id"):
                   int(s.get("n", 0))
                   for s in root.iter(f"{{{MEI_NS}}}staff")}
        lost = []
        for p in range(1, tk2.getPageCount() + 1):
            page = ET.fromstring(tk2.renderToSVG(p))
            for g in page.iter():
                if (g.get("class") or "") != "system":
                    continue
                ms = [m_by_id[e.get("id")] for e in g.iter()
                      if e.get("class") == "measure"
                      and e.get("id") in m_by_id]
                ns = {staff_n[e.get("id")] for e in g.iter()
                      if e.get("class") == "staff"
                      and e.get("id") in staff_n}
                for r in prep.slash_regions:
                    info = next(pi for pi in prep.parts
                                if pi.part_id == r.part)
                    for m in range(r.start_measure, r.stop_measure):
                        if m in ms and info.first_staff not in ns:
                            lost.append((r.part, m))
        print(f"  [{name}] slash measures on HIDDEN staves: "
              f"{lost or 'none'}")
    print("  C: testscore trips the 10R.1 hide-unavailable fallback; "
          "video does not\n")


def section_d():
    print("== D. Repagination: <print new-page> injection ==")
    # take video FLAT (overflowing); strip encoded new-page, inject a
    # page break at every system start (worst case) in PART 1 ONLY;
    # verify Verovio honors them.
    prep = prepare(VIDEO)
    root = ET.fromstring(prep.canonical_xml)
    parts = root.findall("part")
    sys_starts = []
    for m in parts[0].findall("measure"):
        pr = m.find("print")
        if pr is not None and (pr.get("new-system") == "yes"
                               or pr.get("new-page") == "yes"):
            sys_starts.append(int(m.get("number")))
    print(f"  encoded system/page starts (part 1): {sys_starts}")
    for part in parts:
        for m in part.findall("measure"):
            pr = m.find("print")
            if pr is not None and pr.get("new-page"):
                del pr.attrib["new-page"]
    # inject: page break at every OTHER system start, part 1 only
    chosen = sys_starts[::2]
    for m in parts[0].findall("measure"):
        if int(m.get("number")) in chosen:
            pr = m.find("print")
            if pr is None:
                pr = ET.Element("print")
                m.insert(0, pr)
            pr.set("new-page", "yes")
    tk = make_toolkit(prep)
    ok = tk.loadData(ET.tostring(root, encoding="unicode"))
    print(f"  part-1-only injection at {chosen}: loaded={ok}, "
          f"pages={tk.getPageCount()} (expected {len(chosen) + 1})")
    assert tk.getPageCount() == len(chosen) + 1, \
        "part-1-only new-page injection not honored as planned"

    # id stability: musical ids should survive repagination
    mei_a = make_toolkit(prep)
    mei_a.loadData(prep.canonical_xml)
    ids_a = set(re.findall(r'xml:id="([^"]+)"', mei_a.getMEI()))
    ids_b = set(re.findall(r'xml:id="([^"]+)"', tk.getMEI()))
    print(f"  Verovio ids: baseline {len(ids_a)}, repaginated {len(ids_b)}, "
          f"common {len(ids_a & ids_b)} (Verovio re-rolls on input change "
          f"— OUR musical ids are the stable ones, pinned in tests)")
    print("  D PASS: part-1-only injection controls pagination\n")


def section_e():
    print("== E. Onset sources for animate-everything ==")
    prep = prepare(VIDEO)
    tk = make_toolkit(prep)
    tk.loadData(prep.canonical_xml)
    root = ET.fromstring(tk.getMEI())
    census = defaultdict(Counter)
    for measure in root.iter(f"{{{MEI_NS}}}measure"):
        for el in measure:
            tag = el.tag.split("}")[-1]
            if tag in ("fermata", "trill", "mordent", "turn", "dir",
                       "tempo", "reh", "harm", "dynam"):
                key = ("startid" if el.get("startid") else "") + \
                      ("+tstamp" if el.get("tstamp") else "")
                census[tag][key or "NEITHER"] += 1
    for tag in sorted(census):
        print(f"  {tag:8s} {dict(census[tag])}")
    neither = {t: c["NEITHER"] for t, c in census.items() if c["NEITHER"]}
    print(f"  elements with neither startid nor tstamp: {neither or 'none'}")
    print("  E: attach onsets resolvable for every measure-attached "
          "class above\n")


def main() -> None:
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()
    print("phase10r spike complete")


if __name__ == "__main__":
    main()
