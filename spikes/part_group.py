"""Phase 8, task 8.1 — <part-group> injection spike (proper re-do of the
v2 scoping probe, which ran from a session scratchpad).

Questions, against testdata/testscore.musicxml (whose Dorico export has no
<part-group> at all — BACKLOG 1):

1. Does injecting <part-group> (group-symbol + group-barline) into the
   part-list make Verovio render a grpSym bracket AND join barlines
   through the group?
2. What NEW SVG classes does each group symbol (bracket/brace/line/square)
   introduce vs the baseline render — i.e. the complete list the adapter
   must register in _KIND_BY_CLASS?
3. grpSym anatomy: how many per page/system, where in the tree, does it
   carry an id, and does that id cross-reference an MEI staffGrp (which
   would give identity minting its part span)?
4. Where do the joined-barline CONNECTOR segments land — inside the
   existing id-bearing <g class="barLine"> groups (outcome A), in id-less
   barLine groups (B1, silently absorbed today), or as loose paths (B2,
   orphan raise)?
5. How far does the bracket shift the left margin (min-x of staff ink)?

Renders mirror the production adapter options (header suppressed,
xmlIdSeed fixed, concert pitch, octave-only transposes neutralized).

Run: .venv/bin/python spikes/part_group.py
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import verovio

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"
OUT = ROOT / "spikes" / "out"

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


# --- MusicXML prep (mirrors core/score/musicxml_prep + the 8.3 injection) ---

def neutralize_octave_transposes(root: ET.Element) -> None:
    for attributes in root.iter("attributes"):
        for tr in list(attributes.findall("transpose")):
            if (float(tr.findtext("chromatic", "0")) == 0
                    and float(tr.findtext("diatonic", "0")) == 0):
                attributes.remove(tr)


def inject_part_group(root: ET.Element, part_ids: tuple[str, ...],
                      symbol: str, barline: bool) -> None:
    plist = root.find("part-list")
    kids = list(plist)
    first = next(i for i, k in enumerate(kids)
                 if k.tag == "score-part" and k.get("id") == part_ids[0])
    last = next(i for i, k in enumerate(kids)
                if k.tag == "score-part" and k.get("id") == part_ids[-1])
    start = ET.Element("part-group", {"type": "start", "number": "1"})
    ET.SubElement(start, "group-symbol").text = symbol
    ET.SubElement(start, "group-barline").text = "yes" if barline else "no"
    stop = ET.Element("part-group", {"type": "stop", "number": "1"})
    plist.insert(last + 1, stop)   # insert stop first so `first` stays valid
    plist.insert(first, start)


def page_size(root: ET.Element) -> tuple[float, float]:
    scaling = root.find("./defaults/scaling")
    per_tenth = (float(scaling.findtext("millimeters"))
                 / float(scaling.findtext("tenths")) * 10)
    layout = root.find("./defaults/page-layout")
    return (float(layout.findtext("page-width")) * per_tenth,
            float(layout.findtext("page-height")) * per_tenth)


def render(name: str, group: tuple[str, ...] | None,
           symbol: str = "bracket", barline: bool = True):
    """Engrave one variant; return (pages-as-ET-roots, mei string)."""
    root = ET.fromstring(SCORE.read_bytes())
    neutralize_octave_transposes(root)
    if group:
        inject_part_group(root, group, symbol, barline)
    width, height = page_size(root)

    tk = verovio.toolkit()
    tk.setOptions({
        "breaks": "encoded", "font": "Bravura",
        "pageWidth": round(width), "pageHeight": round(height),
        "scaleToPageSize": True,
        "header": "none", "footer": "encoded",
        "svgHtml5": False, "svgViewBox": True,
        "transposeToSoundingPitch": True,
        "xmlIdSeed": 42,
    })
    if not tk.loadData(ET.tostring(root, encoding="unicode")):
        raise SystemExit(f"{name}: Verovio failed to load")

    pages = []
    for p in range(1, tk.getPageCount() + 1):
        svg = tk.renderToSVG(p)
        (OUT / f"partgroup-{name}-page-{p}.svg").write_text(svg)
        pages.append(ET.fromstring(svg))
    print(f"[{name}] loaded OK, {len(pages)} pages "
          f"-> spikes/out/partgroup-{name}-page-*.svg")
    return pages, tk.getMEI()


# --- census / geometry helpers ----------------------------------------------

def tag_of(el: ET.Element) -> str:
    return el.tag.split("}")[-1]


def census(pages) -> tuple[Counter, Counter]:
    counts, with_id = Counter(), Counter()
    for page in pages:
        for g in page.iter():
            cls = g.get("class")
            if cls:
                counts[cls] += 1
                if g.get("id"):
                    with_id[cls] += 1
    return counts, with_id


def nums(d: str) -> list[float]:
    return [float(m) for m in _NUM.findall(d or "")]


def path_yspans(group: ET.Element) -> list[tuple[float, float]]:
    """(ymin, ymax) per path/polyline child, from raw coordinate pairs."""
    spans = []
    for el in group.iter():
        if tag_of(el) in ("path", "polyline", "line"):
            ys = nums(el.get("d") or el.get("points") or "")[1::2]
            if ys:
                spans.append((min(ys), max(ys)))
    return spans


def ink_extent(group: ET.Element) -> tuple[float, float, float, float] | None:
    """(xmin, ymin, xmax, ymax) over path coords, rect attrs, use translates."""
    xs, ys = [], []
    for el in group.iter():
        t = tag_of(el)
        if t in ("path", "polyline", "line"):
            c = nums(el.get("d") or el.get("points") or "")
            xs += c[0::2]
            ys += c[1::2]
        elif t == "rect":
            x, y = float(el.get("x", "0")), float(el.get("y", "0"))
            xs += [x, x + float(el.get("width", "0"))]
            ys += [y, y + float(el.get("height", "0"))]
        elif t == "use":
            m = _NUM.findall(el.get("transform") or "")
            if len(m) >= 2:
                xs.append(float(m[0]))
                ys.append(float(m[1]))
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def staff_min_x(page: ET.Element) -> float:
    """Min x over staff-line paths (g[class=staff] path ink)."""
    lo = float("inf")
    for g in page.iter():
        if g.get("class") == "staff":
            for el in g.iter():
                if tag_of(el) == "path":
                    xs = nums(el.get("d"))[0::2]
                    if xs:
                        lo = min(lo, min(xs))
    return lo


def min_ink_x(page: ET.Element) -> float:
    """Min x over every drawn coordinate + <use> translate on the page."""
    lo = float("inf")
    for el in page.iter():
        t = tag_of(el)
        if t in ("path", "polyline", "line"):
            xs = nums(el.get("d") or el.get("points") or "")[0::2]
            if xs:
                lo = min(lo, min(xs))
        elif t == "use":
            m = _NUM.findall(el.get("transform") or "")
            if m:
                lo = min(lo, float(m[0]))
    return lo


def parent_map(page: ET.Element):
    return {c: p for p in page.iter() for c in p}


def chain(el: ET.Element, parents) -> str:
    parts = []
    node = el
    while node is not None:
        cls, cid = node.get("class"), node.get("id")
        if cls or cid:
            parts.append(f"{tag_of(node)}[{cls or '?'}"
                         + (f" id={cid}" if cid else "") + "]")
        node = parents.get(node)
    return " < ".join(parts)


def main() -> None:
    OUT.mkdir(exist_ok=True)

    base_pages, _ = render("baseline", None)
    sax_pages, sax_mei = render("P1-P2-bracket", ("P1", "P2"))
    probe_pages, _ = render("P1-P3-bracket", ("P1", "P2", "P3"))
    symbol_pages = {
        sym: render(f"P1-P2-{sym}", ("P1", "P2"), symbol=sym)[0]
        for sym in ("brace", "line", "square")
    }

    # --- Q2: class census diff per variant ----------------------------------
    base_counts, _ = census(base_pages)
    print("\n== Q2: class census diff vs baseline ==")
    for name, pages in [("P1-P2-bracket", sax_pages),
                        ("P1-P3-bracket", probe_pages),
                        *[(f"P1-P2-{s}", p) for s, p in symbol_pages.items()]]:
        counts, with_id = census(pages)
        new = {c: n for c, n in counts.items() if c not in base_counts}
        changed = {c: (base_counts[c], n) for c, n in counts.items()
                   if c in base_counts and base_counts[c] != n}
        gone = {c: n for c, n in base_counts.items() if c not in counts}
        print(f"  [{name}] new: "
              + (", ".join(f"{c} x{n} (with_id={with_id[c]})"
                           for c, n in sorted(new.items())) or "none")
              + (f" | count-changed: {changed}" if changed else "")
              + (f" | GONE: {gone}" if gone else ""))

    # --- Q3: grpSym anatomy (sax variant) ------------------------------------
    print("\n== Q3: grpSym anatomy (P1-P2 bracket) ==")
    for pno, page in enumerate(sax_pages, 1):
        parents = parent_map(page)
        syms = [g for g in page.iter() if g.get("class") == "grpSym"]
        print(f"  page {pno}: {len(syms)} grpSym")
        for g in syms:
            kids = Counter(tag_of(c) for c in g.iter() if c is not g)
            ext = ink_extent(g)
            span = (f"x={ext[0]:.0f}..{ext[2]:.0f} y={ext[1]:.0f}..{ext[3]:.0f}"
                    if ext else "no measurable ink")
            print(f"    id={g.get('id')!r} attrs={dict(g.attrib)} "
                  f"children={dict(kids)} {span}")
            print(f"      chain: {chain(g, parents)}")

    # do the grpSym y-extents line up with the grouped staves' y-extents?
    page1 = sax_pages[0]
    staves = [g for g in page1.iter() if g.get("class") == "staff"]
    print("  page-1 staff y-spans (first 3 staves):")
    for g in staves[:3]:
        spans = path_yspans(g)
        print(f"    staff id={g.get('id')} "
              f"y={min(a for a, _ in spans):.0f}"
              f"..{max(b for _, b in spans):.0f}")

    mei_root = ET.fromstring(sax_mei)
    grp_ids = []
    print("  MEI staffGrp structure (scoreDef):")
    for grp in mei_root.iter():
        if tag_of(grp) == "staffGrp":
            attrs = {k.split('}')[-1]: v for k, v in grp.attrib.items()}
            staves_n = [c.attrib.get("n") for c in grp
                        if tag_of(c) == "staffDef"]
            grp_ids.append(attrs.get("id"))
            print(f"    staffGrp {attrs} staffDefs n={staves_n}")
    svg_text = "".join(ET.tostring(p, encoding="unicode") for p in sax_pages)
    for gid in grp_ids:
        print(f"  MEI staffGrp id {gid!r} appears in SVG: {gid in svg_text}")

    # --- Q4: connector nesting (P1-P3, where the m1 split was observed) ------
    print("\n== Q4: barline anatomy, page 1 ==")
    for name, pages in [("baseline", base_pages), ("P1-P3-bracket", probe_pages)]:
        page = pages[0]
        parents = parent_map(page)
        print(f"  [{name}] id-bearing barLine groups (first measure only):")
        seen_measures = set()
        for g in page.iter():
            if g.get("class") == "barLine" and g.get("id"):
                node, measure = g, None
                while node is not None:
                    if node.get("class") == "measure":
                        measure = node.get("id")
                        break
                    node = parents.get(node)
                if measure in seen_measures or len(seen_measures) >= 1:
                    continue
                seen_measures.add(measure)
                spans = sorted(path_yspans(g))
                print(f"    barLine id={g.get('id')} in measure={measure}: "
                      f"{len(spans)} paths, y-spans "
                      + ", ".join(f"{a:.0f}-{b:.0f}" for a, b in spans))
        idless = [g for g in page.iter()
                  if g.get("class") == "barLine" and not g.get("id")]
        print(f"    id-less barLine groups on page 1: {len(idless)}")
        for g in idless[:6]:
            spans = sorted(path_yspans(g))
            print(f"      chain: {chain(g, parents)} | y-spans "
                  + ", ".join(f"{a:.0f}-{b:.0f}" for a, b in spans))

    # --- Q5: left-margin shift ----------------------------------------------
    print("\n== Q5: left-margin ink shift (page 1, definition units) ==")
    base_staff, base_ink = staff_min_x(base_pages[0]), min_ink_x(base_pages[0])
    print(f"  baseline: staff-lines min-x {base_staff:.0f}, "
          f"any-ink min-x {base_ink:.0f}")
    for name, pages in [("P1-P2-bracket", sax_pages),
                        ("P1-P3-bracket", probe_pages),
                        *[(f"P1-P2-{s}", p) for s, p in symbol_pages.items()]]:
        s, i = staff_min_x(pages[0]), min_ink_x(pages[0])
        print(f"  {name}: staff-lines min-x {s:.0f} "
              f"(delta {s - base_staff:+.0f}), any-ink min-x {i:.0f} "
              f"(delta {i - base_ink:+.0f})")


if __name__ == "__main__":
    main()
