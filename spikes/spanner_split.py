"""Phase 5 spike: how does Verovio represent spanners broken across
systems (and pages)?

Questions (must be answered before the adapter grows per-segment
spanner splitting for clip-reveal, PHASES 5.2):

1. SVG shape: is a system-broken slur/tie/hairpin ONE <g> with several
   path children, or SEVERAL <g>s (one per segment)? If several, do they
   share the same id (SVG id collision) and which system/measure subtree
   hosts each segment?
2. MEI shape: do hairpins carry startid/endid like slurs, or
   tstamp/tstamp2 + @staff? (The adapter today resolves spanner identity
   only via startid — verovio_adapter.py:864 — so tstamp-only hairpins
   would get part=None, onset=None.)

Fixture: testdata/broken_hairpin_and_slur_test.musicxml (Dorico export,
2 parts, 10 measures, 3 systems on one page): hairpin broken across the
m4->m5 system break, slur broken across m8->m9, ties broken across
m8->m9.

Run: python spikes/spanner_split.py
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import verovio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoreanim.core.score.musicxml_prep import prepare  # noqa: E402

MEI_NS = "{http://www.music-encoding.org/ns/mei}"
SVG_NS = "{http://www.w3.org/2000/svg}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

SPANNER_CLASSES = ("slur", "tie", "hairpin", "lv")


def main() -> None:
    score = Path(__file__).resolve().parent.parent / \
        "testdata" / "broken_hairpin_and_slur_test.musicxml"
    prep = prepare(score)
    tk = verovio.toolkit()
    tk.setOptions({
        "breaks": "encoded",
        "font": "Bravura",
        "pageWidth": round(prep.page_width),
        "pageHeight": round(prep.page_height),
        "scaleToPageSize": True,
        "header": "none",
        "footer": "encoded",
        "svgHtml5": False,
        "svgViewBox": True,
        "transposeToSoundingPitch": True,
        "xmlIdSeed": 42,
    })
    if not tk.loadData(prep.canonical_xml):
        raise SystemExit("Verovio failed to load the fixture")

    print(f"pages: {tk.getPageCount()}")

    # ---- MEI: spanner attribute census -------------------------------
    mei = ET.fromstring(tk.getMEI())
    print("\n== MEI spanners (per measure) ==")
    measure_n: dict[str, str] = {}
    for measure in mei.iter(f"{MEI_NS}measure"):
        n = measure.get("n", "?")
        for sp in measure:
            tag = sp.tag.removeprefix(MEI_NS)
            if tag not in SPANNER_CLASSES:
                continue
            sp_id = sp.get(XML_ID)
            measure_n[sp_id or ""] = n
            attrs = {k: v for k, v in sp.attrib.items() if k != XML_ID}
            print(f"  m{n} <{tag}> id={sp_id} {attrs}")

    # ---- SVG: segment shape per page ----------------------------------
    print("\n== SVG spanner groups ==")
    id_pages: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    for page in range(1, tk.getPageCount() + 1):
        root = ET.fromstring(tk.renderToSVG(page))
        systems: list[ET.Element] = []

        def walk(el: ET.Element, sys_idx: int | None) -> None:
            cls = (el.get("class") or "").split()[0] if el.get("class") else ""
            if cls == "system":
                systems.append(el)
                sys_idx = len(systems) - 1
            if cls in SPANNER_CLASSES:
                paths = el.findall(f".//{SVG_NS}path")
                gid = el.get("id") or el.get(XML_ID) or "?"
                # which measure subtree hosts this group?
                host = hosting_measure(root, el)
                print(f"  page {page} sys{sys_idx} <g class={cls!r} "
                      f"id={gid}> paths={len(paths)} "
                      f"host_measure={host} mei_measure=m"
                      f"{measure_n.get(gid, '?')}")
                for p in el.findall(f"{SVG_NS}path"):
                    d = p.get("d", "")
                    print(f"      direct path d[:60]={d[:60]!r}")
                id_pages[gid].append((page, sys_idx if sys_idx is not None
                                      else -1, len(paths)))
            for child in el:
                walk(child, sys_idx)

        walk(root, None)

    print("\n== duplicate-id check (same id on several pages/systems) ==")
    dups = {gid: locs for gid, locs in id_pages.items() if len(locs) > 1}
    if not dups:
        print("  none — every spanner <g> id appears exactly once")
    for gid, locs in dups.items():
        print(f"  id={gid}: {locs}")

    multi = {gid: locs for gid, locs in id_pages.items()
             if any(n > 1 for _, _, n in locs)}
    print("\n== multi-path groups (one <g>, several segments?) ==")
    if not multi:
        print("  none — every spanner <g> holds exactly one path")
    for gid, locs in multi.items():
        print(f"  id={gid}: {locs}")


def hosting_measure(root: ET.Element, target: ET.Element) -> str | None:
    """Measure id whose subtree contains target (ElementTree has no parent
    pointers; scan)."""
    for measure in root.iter(f"{SVG_NS}g"):
        if (measure.get("class") or "").split()[:1] == ["measure"]:
            if target in measure.iter():
                return measure.get("id")
    return None


if __name__ == "__main__":
    main()
