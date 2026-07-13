"""Phase 10, task 10.0 — video_test.musicxml triage spike (kept).

Freezes the enumeration that established the Phase 10 root causes: which
features the prior two fixtures (testscore, broken_hairpin_and_slur_test)
never exercised, and exactly how each one breaks the loader today. After
the 10.1-10.4 fixes land, section F reports "no longer raises" and
sections A-E remain the durable library documentation.

Questions, against testdata/video_test.musicxml (real production score,
7 score-parts, P5 Piano <staves>2</staves>) and testscore:

A. How does music21 split a multi-staff part, and does the split
   reconcile with prep's PartInfo staff geometry by construction?
B. Which SVG classes does video_test introduce that the decomposer does
   not know, and are they drawable (guard-fatal) or empty?
C. The m12 "ledger dash matches no notehead" failure: what actually owns
   that dash? (Answer: a displaced two-voice REST — not cross-staff.)
D. Tie continuation ink: which systems does Verovio draw it in, and do
   the counts close under an end-system rule? Which MEI spanners produce
   no ink at all (Verovio's "ties left open" / "tie ignored" warnings)?
E. What does Verovio's `condense` option (default "auto") do to a score
   with two staff groups, and does "encoded" restore the encoded layout?
F. Reproduce the four Phase 10 failure points, in order.

Run: .venv/bin/python spikes/video_test_triage.py
"""

import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import music21 as m21
import verovio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoreanim.core.engraving import verovio_adapter          # noqa: E402
from scoreanim.core.engraving.types import EngravingParams    # noqa: E402
from scoreanim.core.engraving.verovio_adapter import (        # noqa: E402
    _CONTAINER_CLASSES, _KIND_BY_CLASS, VerovioEngravingProvider)
from scoreanim.core.score.model import build_score_model      # noqa: E402
from scoreanim.core.score.musicxml_prep import (              # noqa: E402
    PartGroupSpec, prepare)
VIDEO = ROOT / "testdata" / "video_test.musicxml"
TESTSCORE = ROOT / "testdata" / "testscore.musicxml"

_MEI_NS = "{http://www.music-encoding.org/ns/mei}"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_DRAWABLE = {"use", "path", "rect", "line", "polygon", "polyline",
             "ellipse", "circle", "text"}


def tag_of(el: ET.Element) -> str:
    return el.tag.split("}")[-1]


def first_cls(el: ET.Element) -> str:
    tokens = (el.get("class") or "").split()
    return tokens[0] if tokens else ""


def render(score: Path, groups: tuple[PartGroupSpec, ...] = (),
           condense: str = "auto"):
    """Engrave with the production adapter options (+ a condense knob);
    return (prep, page ET roots, raw page strings, mei string)."""
    prep = prepare(score, groups)
    tk = verovio.toolkit()
    tk.setOptions({
        "breaks": "encoded", "font": "Bravura",
        "pageWidth": round(prep.page_width),
        "pageHeight": round(prep.page_height),
        "scaleToPageSize": True,
        "header": "none", "footer": "encoded",
        "svgHtml5": False, "svgViewBox": True,
        "transposeToSoundingPitch": True,
        "xmlIdSeed": 42,
        "condense": condense,
    })
    if not tk.loadData(prep.canonical_xml):
        raise SystemExit(f"Verovio failed to load {score.name}")
    raw = [tk.renderToSVG(p) for p in range(1, tk.getPageCount() + 1)]
    return prep, [ET.fromstring(s) for s in raw], raw, tk.getMEI()


def systems_of(pages) -> list[list[ET.Element]]:
    """Score-wide system list; each entry = the system <g> elements
    (document order matches the adapter's score-wide system index)."""
    out = []
    for page in pages:
        for g in page.iter():
            if g.get("class") == "system":
                out.append(g)
    return out


def measure_system_map(pages, mei_measure_by_id) -> dict[int, int]:
    m2s: dict[int, int] = {}
    for sys_n, sys_g in enumerate(systems_of(pages), start=1):
        for g in sys_g.iter():
            if g.get("class") == "measure" and g.get("id") in mei_measure_by_id:
                m2s.setdefault(mei_measure_by_id[g.get("id")], sys_n)
    return m2s


def mei_measures_and_spanners(mei: str):
    """measure_by_id, note id → (measure, staff), spanner id → (tag,
    startid, endid) for the drawn-spanner tags."""
    root = ET.fromstring(mei)
    measure_by_id: dict[str, int] = {}
    note_pos: dict[str, tuple[int, int]] = {}
    spanners: dict[str, tuple[str, str | None, str | None]] = {}
    ordinal = 0
    for measure in root.iter(f"{_MEI_NS}measure"):
        ordinal += 1
        m_n = int(measure.get("n", ordinal))
        if measure.get(_XML_ID):
            measure_by_id[measure.get(_XML_ID)] = m_n
        for staff in measure.findall(f"{_MEI_NS}staff"):
            s_n = int(staff.get("n", 0))
            for note in staff.iter(f"{_MEI_NS}note"):
                if note.get(_XML_ID):
                    note_pos[note.get(_XML_ID)] = (m_n, s_n)
        for sp in measure:
            tag = tag_of(sp)
            if tag in ("tie", "slur", "hairpin", "lv") and sp.get(_XML_ID):
                ref = lambda v: v.lstrip("#") if v else None
                spanners[sp.get(_XML_ID)] = (tag, ref(sp.get("startid")),
                                             ref(sp.get("endid")))
    return measure_by_id, note_pos, spanners


def ink_x_range(group: ET.Element) -> tuple[float, float] | None:
    xs = []
    for el in group.iter():
        t = tag_of(el)
        if t in ("path", "polyline", "line"):
            xs += [float(v) for v in _NUM.findall(
                el.get("d") or el.get("points") or "")][0::2]
        elif t == "use":
            m = _NUM.findall(el.get("transform") or "")
            if m:
                xs.append(float(m[0]))
    return (min(xs), max(xs)) if xs else None


def section_a():
    print("== A. Part/staff structure ==")
    prep = prepare(VIDEO)
    for p in prep.parts:
        print(f"  prep: index={p.index} id={p.part_id} name={p.name!r} "
              f"staff_count={p.staff_count} first_staff={p.first_staff}")
    assert len(prep.parts) == 7
    p5 = next(p for p in prep.parts if p.part_id == "P5")
    assert (p5.staff_count, p5.first_staff) == (2, 5), \
        f"P5 geometry changed: {p5}"

    score = m21.converter.parse(prep.canonical_xml, format="musicxml")
    score.toSoundingPitch(inPlace=True)
    parts = list(score.parts)
    print(f"  music21: {len(parts)} parts "
          f"(prep {len(prep.parts)}, sum(staff_count) "
          f"{sum(p.staff_count for p in prep.parts)})")
    for i, part in enumerate(parts):
        n_measures = len(part.getElementsByClass(m21.stream.Measure))
        n_notes = len(list(part.recurse().notes))
        print(f"    [{i}] {type(part).__name__:10s} id={str(part.id)!r} "
              f"measures={n_measures} note-els={n_notes}")
    # The load-bearing music21 contract for 10.1: a multi-staff part
    # splits into adjacent PartStaff objects, in document order, in the
    # score-part's slot, ids '<score-part-id>-Staff<k>' (unlike plain
    # Parts, whose id is replaced by the part NAME).
    assert sum(p.staff_count for p in prep.parts) == len(parts)
    assert isinstance(parts[4], m21.stream.PartStaff)
    assert isinstance(parts[5], m21.stream.PartStaff)
    assert parts[4].id == "P5-Staff1" and parts[5].id == "P5-Staff2", \
        (parts[4].id, parts[5].id)
    assert not any(isinstance(p, m21.stream.PartStaff)
                   for p in parts[:4] + parts[6:])
    groups = [sp for sp in score.recurse()
              if isinstance(sp, m21.layout.StaffGroup)]
    for g in groups:
        print(f"  m21 StaffGroup: symbol={g.symbol!r} over "
              f"{[str(p.id) for p in g.getSpannedElements()]}")
    print("  A PASS: PartStaff split reconciles with prep by construction\n")


def section_b():
    print("== B. SVG class census (video_test, adapter options) ==")
    _, pages, _, _ = render(VIDEO)
    counts, with_id, drawable = Counter(), Counter(), Counter()
    samples: dict[str, ET.Element] = {}
    for page in pages:
        for g in page.iter():
            cls = first_cls(g)
            if not cls or tag_of(g) != "g":
                continue
            counts[cls] += 1
            if g.get("id"):
                with_id[cls] += 1
            if any(tag_of(e) in _DRAWABLE for e in g.iter() if e is not g):
                drawable[cls] += 1
            samples.setdefault(cls, g)
    known = set(_KIND_BY_CLASS) | _CONTAINER_CLASSES
    novel = sorted(c for c in counts if c not in known)
    print(f"  pages={len(pages)}, classes={len(counts)}, novel={novel}")
    for c in novel:
        kids = Counter(tag_of(e) for e in samples[c].iter()
                       if e is not samples[c])
        print(f"    {c}: x{counts[c]}, with_id={with_id[c]}, "
              f"drawable={drawable[c]}, sample children={dict(kids)}")
    # bracketSpan / mSpace: id-bearing, EMPTY groups today — they never
    # hit the unknown-drawable guard, but 10.4 registers them so a future
    # drawable one never does.
    for c in ("bracketSpan", "mSpace"):
        assert c in counts, f"{c} vanished from video_test render"
        assert drawable[c] == 0, f"{c} became drawable — 10.4 must map it"
        assert with_id[c] == counts[c], f"{c} lost its ids"
    assert "systemDivider" not in counts, \
        "video_test now draws systemDividers (condense kicked in?)"
    print("  B PASS: novel classes are empty (non-guard-fatal) on this "
          "fixture\n")


def section_c():
    print("== C. Ledger census: the m12 staff-2 dash ==")
    _, pages, _, mei = render(VIDEO)
    root = ET.fromstring(mei)
    # locate measure 12's SVG subtree via its MEI id
    m12_id = next(m.get(_XML_ID) for m in root.iter(f"{_MEI_NS}measure")
                  if m.get("n") == "12")
    m12 = next(g for page in pages for g in page.iter()
               if g.get("class") == "measure" and g.get("id") == m12_id)
    staff_n_by_id = {st.get(_XML_ID): st.get("n")
                     for st in root.iter(f"{_MEI_NS}staff") if st.get(_XML_ID)}
    staves = [g for g in m12.iter() if g.get("class") == "staff"]
    needs_rest_total = 0
    for staff_g in staves:
        s_n = staff_n_by_id.get(staff_g.get("id"), "?")
        ledgers = [g for g in staff_g.iter()
                   if (g.get("class") or "").startswith("ledgerLines")]
        if not ledgers:
            continue
        notes = [(g.get("id"), ink_x_range(g)) for g in staff_g.iter()
                 if g.get("class") == "note"]
        rests = [(g.get("id"), ink_x_range(g)) for g in staff_g.iter()
                 if g.get("class") == "rest"]
        for lg in ledgers:
            for dash in lg:
                xr = ink_x_range_of_path(dash)
                overlaps = lambda r: r and not (r[1] <= xr[0] or xr[1] <= r[0])
                note_hits = [i for i, r in notes if overlaps(r)]
                rest_hits = [i for i, r in rests if overlaps(r)]
                print(f"  m12 staff {s_n} dash x={xr[0]:.0f}..{xr[1]:.0f} "
                      f"cls={lg.get('class')!r}: note-overlap={note_hits} "
                      f"rest-overlap={rest_hits}")
                if not note_hits:
                    needs_rest_total += 1
                    assert rest_hits, "dash matches neither notes nor rests"
                    # the owning rest is a two-voice displaced rest: show it
                    layer = None
                    for st in root.iter(f"{_MEI_NS}staff"):
                        for ly in st.findall(f"{_MEI_NS}layer"):
                            for r in ly.iter(f"{_MEI_NS}rest"):
                                if r.get(_XML_ID) == rest_hits[0]:
                                    layer = (st.get("n"), ly.get("n"),
                                             r.get("dur"))
                    print(f"    -> owner is REST {rest_hits[0]} "
                          f"(staff/layer/dur = {layer}) — a two-voice "
                          f"displaced rest, NOT cross-staff notation")
    assert needs_rest_total >= 1, "the rest-owned dash disappeared"

    # score-wide: how many dashes attribute to noteheads vs only to rests
    note_owned = rest_only = 0
    for page in pages:
        for mg in page.iter():
            if mg.get("class") != "measure":
                continue
            for staff_g in mg.iter():
                if staff_g.get("class") != "staff":
                    continue
                notes = [ink_x_range(g) for g in staff_g.iter()
                         if g.get("class") == "note"]
                rests = [ink_x_range(g) for g in staff_g.iter()
                         if g.get("class") == "rest"]
                for lg in staff_g.iter():
                    if not (lg.get("class") or "").startswith("ledgerLines"):
                        continue
                    for dash in lg:
                        xr = ink_x_range_of_path(dash)
                        ov = lambda r: r and not (r[1] <= xr[0]
                                                  or xr[1] <= r[0])
                        if any(ov(r) for r in notes):
                            note_owned += 1
                        elif any(ov(r) for r in rests):
                            rest_only += 1
                        else:
                            raise AssertionError(
                                f"dash x={xr} matches nothing")
    print(f"  score-wide: {note_owned} dashes note-owned, "
          f"{rest_only} attributable only to a rest")
    print("  C PASS: the failing dash is REST ink — 10.2 adds a rest "
          "candidate tier\n")


def ink_x_range_of_path(el: ET.Element) -> tuple[float, float]:
    xs = [float(v) for v in _NUM.findall(el.get("d") or "")][0::2]
    return min(xs), max(xs)


def section_d():
    print("== D. Tie continuation systems + dropped spanners ==")
    _, pages, raw, mei = render(VIDEO)
    measure_by_id, note_pos, spanners = mei_measures_and_spanners(mei)
    m2s = measure_system_map(pages, measure_by_id)

    # continuation segments: id-less spanner-class <g> per system
    segs_by_sys: dict[int, Counter] = defaultdict(Counter)
    drawn_ids: set[str] = set()
    for sys_n, sys_g in enumerate(systems_of(pages), start=1):
        for g in sys_g.iter():
            cls = first_cls(g)
            if cls in ("tie", "slur", "hairpin", "lv"):
                if g.get("id"):
                    drawn_ids.add(g.get("id"))
                else:
                    segs_by_sys[sys_n][cls] += 1

    # sources: drawn, id-bearing, with known start/end systems
    src_spans: dict[str, tuple[str, int, int]] = {}
    for vid, (tag, start_id, end_id) in spanners.items():
        if vid not in drawn_ids:
            continue
        s = note_pos.get(start_id or "")
        e = note_pos.get(end_id or "")
        if s and e and m2s.get(s[0]) and m2s.get(e[0]):
            src_spans[vid] = (tag, m2s[s[0]], m2s[e[0]])

    print("  per-system tie continuation counts: "
          "drawn vs old predicate (start<n<=end) vs end-system (end==n)")
    mismatch_old = mismatch_end = 0
    for sys_n in sorted(segs_by_sys):
        drawn = segs_by_sys[sys_n].get("tie", 0)
        if not drawn:
            continue
        old = sum(1 for t, s, e in src_spans.values()
                  if t == "tie" and s < sys_n <= e)
        new = sum(1 for t, s, e in src_spans.values()
                  if t == "tie" and s < sys_n and e == sys_n)
        flag = "" if new == drawn else "  <-- STILL OFF"
        if old != drawn:
            mismatch_old += 1
        if new != drawn:
            mismatch_end += 1
        print(f"    system {sys_n:2d}: drawn={drawn:2d} old={old:2d} "
              f"end-rule={new:2d}{flag}")
    print(f"  old predicate mismatches: {mismatch_old}, "
          f"end-system mismatches: {mismatch_end}")
    assert mismatch_end == 0, "end-system rule does not close the counts"
    assert mismatch_old > 0, \
        "old predicate suddenly closes — re-check the 10.3 design"

    # MEI spanners with no ink anywhere. Two structural shapes (Phase 1
    # already saw the first on testscore): an id-bearing <g> with ZERO
    # drawable descendants (open/unmatched ties), or no <g> at all.
    ink_by_id: dict[str, int] = {}
    for page in pages:
        for g in page.iter():
            if tag_of(g) == "g" and g.get("id") in spanners:
                ink_by_id[g.get("id")] = sum(
                    1 for e in g.iter()
                    if e is not g and tag_of(e) in _DRAWABLE)
    dropped = [(vid, tag, note_pos.get(s or ""), note_pos.get(e or ""),
                ink_by_id.get(vid))
               for vid, (tag, s, e) in spanners.items()
               if not ink_by_id.get(vid)]
    print(f"  MEI spanners with NO drawn ink: {len(dropped)} "
          f"(empty <g>: {sum(1 for d in dropped if d[4] == 0)}, "
          f"absent: {sum(1 for d in dropped if d[4] is None)})")
    for vid, tag, s, e, ink in dropped:
        shape = "empty <g>" if ink == 0 else "no <g>"
        cross = " CROSS-STAFF" if s and e and s[1] != e[1] else ""
        pos = (f"start m{s[0]} staff {s[1]} -> end m{e[0]} staff {e[1]}"
               if s and e else f"start={s} end={e}")
        print(f"    {tag} {vid} ({shape}): {pos}{cross}")
    print("  D: dropped spanners are structural (MEI-vs-ink) — 10.3 flags "
          "them as LoadWarnings, never absorbs\n")


def section_e():
    print("== E. Verovio `condense` behavior (testscore, 0/1/2 groups) ==")
    two = (PartGroupSpec(parts=("P1", "P2")), PartGroupSpec(parts=("P3", "P4")))
    variants = [("0-group", ()), ("1-group", two[:1]), ("2-group", two)]
    raws = {}
    for name, groups in variants:
        for condense in ("auto", "encoded"):
            _, pages, raw, _ = render(TESTSCORE, groups, condense)
            raws[(name, condense)] = raw
            rows, syms, divs = [], 0, 0
            for sys_g in systems_of(pages):
                first_measure = next((g for g in sys_g.iter()
                                      if g.get("class") == "measure"), None)
                n_staves = sum(1 for g in first_measure.iter()
                               if g.get("class") == "staff") \
                    if first_measure is not None else 0
                rows.append(n_staves)
                syms += sum(1 for g in sys_g.iter()
                            if g.get("class") == "grpSym")
                divs += sum(1 for g in sys_g.iter()
                            if first_cls(g) == "systemDivider")
            print(f"  [{name} condense={condense}] staves/system={rows} "
                  f"grpSym={syms} systemDivider={divs}")
    for name in ("0-group", "1-group"):
        same = raws[(name, "auto")] == raws[(name, "encoded")]
        print(f"  {name}: auto == encoded byte-identical: {same}")
        assert same, f"condense=encoded changed the {name} render"

    print("  video_test native-brace suppression under an overlapping "
          "injected group:")
    for name, groups in [("plain", ()),
                         ("P4-P5", (PartGroupSpec(parts=("P4", "P5")),))]:
        _, pages, _, _ = render(VIDEO, groups, "encoded")
        per_sys = [sum(1 for g in sys_g.iter()
                       if g.get("class") == "grpSym")
                   for sys_g in systems_of(pages)]
        print(f"    [{name}] grpSym per system: {Counter(per_sys)}")
    print("  E: condense=auto hides empty staves + draws dividers at 2 "
          "groups; encoded restores the encoded layout (rule 7)\n")


def section_f():
    print("== F. The four Phase 10 failure points, in order ==")
    provider = VerovioEngravingProvider()
    params = EngravingParams()

    def attempt(label, fn):
        try:
            fn()
        except Exception as e:                       # noqa: BLE001 — spike
            print(f"  [{label}] reproduced: {type(e).__name__}: {e}")
            return
        print(f"  [{label}] no longer raises (fixed)")

    attempt("F1 build_score_model 8-vs-7",
            lambda: build_score_model(VIDEO))
    attempt("F2 ledger dash m12 staff 2",
            lambda: provider.load_detailed(VIDEO, params))

    # F3 sits behind F2 in the load pipeline; neutralize ledger
    # attribution for this one probe so the spanner pass is reached.
    original = verovio_adapter._attribute_ledger_dashes
    verovio_adapter._attribute_ledger_dashes = lambda accs, st: None
    try:
        attempt("F3 tie continuation mismatch (ledger pass stubbed)",
                lambda: provider.load_detailed(VIDEO, params))
    finally:
        verovio_adapter._attribute_ledger_dashes = original

    attempt("F4 two-group systemDivider guard",
            lambda: provider.load_detailed(
                TESTSCORE, params,
                groups=(PartGroupSpec(parts=("P1", "P2")),
                        PartGroupSpec(parts=("P3", "P4")))))
    print()


def main() -> None:
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()
    section_f()
    print("triage complete")


if __name__ == "__main__":
    main()
