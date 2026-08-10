"""Can a staff be hidden for ONE system? (2026-08-10.)

Marcus wants a manual per-system override: hide the drum staff in this
system, keep it in the next. The Phase 10R spike (older Verovio) found
`staffDef@visible` ignored; the pip toolkit is 6.2.1 now, so this
re-measures before any fallback design.

Candidate: inject an MEI milestone
    <scoreDef><staffGrp><staffDef n="N" visible="false"/></staffGrp></scoreDef>
right before the target system's first measure, and the visible="true"
twin before the next system's first measure — at the two-pass seam the
optimize reload already owns.

Measured, through the REAL provider pipeline where possible:
  (a) does the staff disappear in the target system only;
  (b) do the other systems and pages hold their shape;
  (c) what happens to the hidden staff's notes in the timemap and the
      SVG (note_records / join impact);
  (d) does it compose with scoreDef@optimize (hide_empty_staves on).

Run: python spikes/system_staff_visibility.py
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import verovio

from scoreanim.core.score.musicxml_prep import prepare

VIDEO = Path("testdata/video_test.musicxml")
_MEI_NS = "{http://www.music-encoding.org/ns/mei}"


def _toolkit():
    tk = verovio.toolkit()
    tk.setOptions({"breaks": "encoded", "font": "Bravura",
                   "scaleToPageSize": True, "svgViewBox": True,
                   "xmlIdSeed": 42, "condense": "encoded",
                   "pageWidth": 2100, "pageHeight": 2970})
    return tk


def _inject(mei: str, system_index: int, staff_n: int) -> str:
    """Hide staff `staff_n` for the `system_index`-th system (1-based)
    by bracketing it with visible=false/true milestone scoreDefs.
    Systems are delimited by <sb/> and <pb/> in Verovio's MEI."""

    def milestone(visible: str) -> str:
        return (f'<scoreDef xmlns="http://www.music-encoding.org/ns/mei">'
                f'<staffGrp><staffDef n="{staff_n}" '
                f'visible="{visible}"/></staffGrp></scoreDef>')

    # split on system boundaries: <sb .../> and <pb .../>
    parts = re.split(r"(<[sp]b\b[^>]*/>)", mei)
    # parts alternate: chunk, break, chunk, break, ... chunk i belongs
    # to system i//2 + 1
    out = []
    system = 1
    for i, chunk in enumerate(parts):
        if i % 2 == 1:                       # a break marker
            system += 1
            out.append(chunk)
            if system == system_index:
                out.append(milestone("false"))
            elif system == system_index + 1:
                out.append(milestone("true"))
            continue
        out.append(chunk)
    return "".join(out)


def _staves_per_system(svg_pages: list[str]) -> list[set]:
    """Per system, the set of staff @n values that DRAW (from the MEI
    ids Verovio stamps: each staff g's first path is a staff line; we
    read the count of distinct staff groups per measure instead)."""
    rows = []
    for svg in svg_pages:
        root = ET.fromstring(svg)
        for g in root.iter("{http://www.w3.org/2000/svg}g"):
            if (g.get("class") or "") != "system":
                continue
            per_measure: dict[str, int] = {}
            first_measure_staves = None
            for m in g.iter("{http://www.w3.org/2000/svg}g"):
                if (m.get("class") or "") != "measure":
                    continue
                staves = [c for c in m.iter(
                    "{http://www.w3.org/2000/svg}g")
                    if (c.get("class") or "") == "staff"]
                if first_measure_staves is None:
                    first_measure_staves = len(staves)
            rows.append(first_measure_staves)
    return rows


def main() -> None:
    prep = prepare(VIDEO)
    tk = _toolkit()
    assert tk.loadData(prep.canonical_xml)
    mei = tk.getMEI()
    print("sb/pb markers:", len(re.findall(r"<[sp]b\b[^>]*/>", mei)))

    # baseline
    tk2 = _toolkit()
    assert tk2.loadData(mei)
    base = [tk2.renderToSVG(p) for p in range(1, tk2.getPageCount() + 1)]
    base_rows = _staves_per_system(base)
    print("baseline staves/system:", base_rows)

    # hide staff 8 (Drums) in system 2 only
    injected = _inject(mei, system_index=2, staff_n=8)
    tk3 = _toolkit()
    ok = tk3.loadData(injected)
    print("injected load ok:", ok)
    if not ok:
        return
    out = [tk3.renderToSVG(p) for p in range(1, tk3.getPageCount() + 1)]
    rows = _staves_per_system(out)
    print("injected staves/system:", rows)
    print("pages:", tk2.getPageCount(), "->", tk3.getPageCount())

    # do the hidden staff's notes still hit the timemap?
    t_base = tk2.renderToTimemap({"includeMeasures": True,
                                  "includeRests": True})
    t_inj = tk3.renderToTimemap({"includeMeasures": True,
                                 "includeRests": True})
    ons = lambda t: sorted(v for e in t for v in e.get("on", []))
    print("timemap on-events identical:",
          ons(t_base) == ons(t_inj),
          f"({len(ons(t_base))} vs {len(ons(t_inj))})")

    # is the hidden staff's ink truly absent from the SVG?
    def staff8_groups(svgs):
        n = 0
        for svg in svgs:
            n += len(re.findall(r'class="staff"[^>]*data-n="8"', svg))
        return n
    print("staff-8 groups drawn:", staff8_groups(base), "->",
          staff8_groups(out))


if __name__ == "__main__":
    main()
