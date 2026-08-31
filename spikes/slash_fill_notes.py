"""Can Verovio place the slashes for us? (2026-08-31)

The synthesized slashes were positioned by our own arithmetic, and in
Nidelven bar 1 that put the first slash between the key signature and
the time signature — nothing in that bar anchors a beat (every other
part has a whole-bar rest), so the even-spacing fallback spread them
across the staff bbox, prefix and all.

Marcus's call: a slash should follow the same rules as a quarter note.
region_fill already puts ONE invisible whole-bar note in a slash measure
so optimize keeps the staff. This spike asks whether filling with one
invisible note PER SLASH UNIT works instead — Verovio then spaces them
as the quarter notes they are, and we read the x back off the SVG.

Questions:
  1. Does a print-object="no" note still get a <g class="note"> with
     real geometry in the SVG, or is it dropped?
  2. Where does the geometry live — a <use>, a <path>, an @x?
  3. Do the fill notes get timemap onsets we can key on?
  4. What does the bar-1 spacing look like next to the meter sig?
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import verovio                                                # noqa: E402

from scoreanim.core.engraving.types import EngravingParams    # noqa: E402
from scoreanim.core.engraving.verovio import kinds            # noqa: E402
from scoreanim.core.engraving.verovio.region_fill import (     # noqa: E402
    FILL_ID_PREFIX, _middle_line_pitches)
from scoreanim.core.score.musicxml_prep import prepare        # noqa: E402

SCORE = Path(__file__).resolve().parent.parent / "testdata" / "Nidelven.musicxml"
SVG_NS = "{http://www.w3.org/2000/svg}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def fill_per_slash_unit(xml: str, regions) -> str:
    """Every slash region measure's whole-bar <forward> replaced by one
    invisible note per slash unit, instead of one for the whole bar."""
    root = ET.fromstring(xml)
    parts = {p.get("id", ""): p for p in root.findall("part")}
    for region in regions:
        part = parts.get(str(region.part))
        if part is None:
            continue
        measures = part.findall("measure")
        pitches = _middle_line_pitches(measures)
        for ordinal in range(region.start_measure,
                             min(region.stop_measure, len(measures) + 1)):
            measure = measures[ordinal - 1]
            divisions = _divisions_at(measures, ordinal)
            unit = int(round(divisions * region.slash_unit_quarters))
            for k, fwd in enumerate(measure.findall("forward")):
                total = int(fwd.findtext("duration") or 0)
                if not total or unit <= 0:
                    continue
                count, rest = divmod(total, unit)
                if rest:
                    print(f"  !! m{ordinal}: {total} not a multiple of {unit}")
                    continue
                index = list(measure).index(fwd)
                measure.remove(fwd)
                for j in range(count):
                    measure.insert(index + j, _note(
                        f"{FILL_ID_PREFIX}{region.part}-m{ordinal}-{k}-{j}",
                        str(unit), pitches[ordinal - 1]))
    return ET.tostring(root, encoding="unicode")


def _divisions_at(measures, ordinal: int) -> int:
    divisions = 1
    for measure in measures[:ordinal]:
        for d in measure.iter("divisions"):
            divisions = int(d.text or 1)
    return divisions


def _note(note_id: str, duration: str, pitch) -> ET.Element:
    note = ET.Element("note", {"print-object": "no", "id": note_id})
    p = ET.SubElement(note, "pitch")
    ET.SubElement(p, "step").text = pitch[0]
    ET.SubElement(p, "octave").text = pitch[1]
    ET.SubElement(note, "duration").text = duration
    ET.SubElement(note, "voice").text = "1"
    return note


def main() -> None:
    prep = prepare(SCORE)
    filled = fill_per_slash_unit(prep.canonical_xml, prep.slash_regions)

    tk = verovio.toolkit()
    tk.setOptions({"scale": kinds._DEFAULT_SCALE, "xmlIdSeed": 1,
                   "adjustPageHeight": False, "breaks": "encoded",
                   "transposeToSoundingPitch": True,
                   "pageWidth": prep.page_width, "pageHeight": prep.page_height,
                   "pageMarginLeft": 0, "pageMarginRight": 0,
                   "pageMarginTop": 0, "pageMarginBottom": 0})
    if not tk.loadData(filled):
        raise SystemExit("Verovio refused the filled source")

    timemap = tk.renderToTimemap({"includeMeasures": True, "includeRests": True})
    onsets = {}
    for entry in timemap:
        for vid in entry.get("on", []):
            onsets[vid] = float(entry["qstamp"])
    fill_onsets = {k: v for k, v in onsets.items() if k.startswith(FILL_ID_PREFIX)}
    print(f"Q3. fill notes in the timemap: {len(fill_onsets)} "
          f"(of {sum(1 for _ in re.finditer(FILL_ID_PREFIX, filled))} inserted)")

    svg = tk.renderToSVG(1)
    root = ET.fromstring(svg)
    found = []
    for g in root.iter(f"{SVG_NS}g"):
        gid = g.get(XML_ID) or g.get("id")
        if not gid or not gid.startswith(FILL_ID_PREFIX):
            continue
        uses = list(g.iter(f"{SVG_NS}use"))
        paths = list(g.iter(f"{SVG_NS}path"))
        found.append((gid, g.get("class"), g.get("visibility"), uses, paths))
    print(f"\nQ1. fill <g> groups on page 1: {len(found)}")
    for gid, cls, vis, uses, paths in found[:6]:
        print(f"   {gid:34s} class={cls} visibility={vis} "
              f"uses={len(uses)} paths={len(paths)}")
        for u in uses[:2]:
            print(f"       Q2. <use x={u.get('x')} y={u.get('y')} "
                  f"height={u.get('height')}>")

    print("\nQ4. page-1 bar-1 landmarks (definition-scale x):")
    for g in root.iter(f"{SVG_NS}g"):
        cls = (g.get("class") or "").split()[0] if g.get("class") else ""
        if cls not in ("meterSig", "keySig", "clef"):
            continue
        u = next(iter(g.iter(f"{SVG_NS}use")), None)
        if u is not None:
            print(f"   {cls:10s} x={u.get('x')}")
            if cls == "meterSig":
                break


if __name__ == "__main__":
    main()
