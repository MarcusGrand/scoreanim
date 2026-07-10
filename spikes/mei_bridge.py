"""Phase 1, task T0 — MEI bridge spike.

Confirms the assumptions behind the identity join (plan D2):
1. Within one load, ids agree across timemap / SVG / getMEI().
2. A per-note table (measure, staff, layer, pitch, grace, chord parent,
   document order) is extractable from the MEI.
3. What Verovio emits inside slash (forward-only) measures — mRest or
   nothing — for the drum part (P7 = staff 7), mm 3-9, 11-17.

Loads with the adapter's real options (concert pitch, encoded breaks,
fixed xmlIdSeed) so findings match production behavior.

Run: .venv/bin/python spikes/mei_bridge.py
"""

from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

import verovio

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"

MEI_NS = {"mei": "http://www.music-encoding.org/ns/mei"}
SVG_NS = {"svg": "http://www.w3.org/2000/svg"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def main() -> None:
    tk = verovio.toolkit()
    tk.setOptions({
        "breaks": "encoded",
        "font": "Bravura",
        "transposeToSoundingPitch": True,
        "xmlIdSeed": 42,
    })
    if not tk.loadFile(str(SCORE)):
        raise SystemExit("FAILED to load the MusicXML file")

    # --- gather ids from all three sources -----------------------------------
    timemap = tk.renderToTimemap({"includeMeasures": True, "includeRests": True})
    timemap_note_ids = {i for e in timemap for i in e.get("on", [])}

    svg_ids_by_class: dict[str, set[str]] = {}
    for page in range(1, tk.getPageCount() + 1):
        root = ET.fromstring(tk.renderToSVG(page))
        for g in root.iter():
            cls, gid = g.get("class"), g.get("id")
            if cls and gid:
                svg_ids_by_class.setdefault(cls, set()).add(gid)

    mei = ET.fromstring(tk.getMEI())
    mei_notes = mei.findall(".//mei:note", MEI_NS)
    mei_note_ids = {n.get(XML_ID) for n in mei_notes}

    svg_note_ids = svg_ids_by_class.get("note", set())
    print(f"note ids: timemap={len(timemap_note_ids)} svg={len(svg_note_ids)} "
          f"mei={len(mei_note_ids)}")
    print(f"timemap ⊆ mei: {timemap_note_ids <= mei_note_ids}")
    print(f"svg == mei:    {svg_note_ids == mei_note_ids}")
    if svg_note_ids != mei_note_ids:
        print("  only in svg:", sorted(svg_note_ids - mei_note_ids)[:5])
        print("  only in mei:", sorted(mei_note_ids - svg_note_ids)[:5])
    if not timemap_note_ids <= mei_note_ids:
        print("  timemap-only:", sorted(timemap_note_ids - mei_note_ids)[:5])

    # --- staffDef structure: how do MEI staves map to MusicXML parts? --------
    print("\nstaffDefs (staff n -> label):")
    for sd in mei.findall(".//mei:staffDef", MEI_NS):
        label = sd.find("mei:label", MEI_NS)
        label_text = "".join(label.itertext()).strip() if label is not None else None
        print(f"  n={sd.get('n')} lines={sd.get('lines')} label={label_text!r}")

    # --- note table extractability -------------------------------------------
    parent_of = {c: p for p in mei.iter() for c in p}

    def ancestor(el: ET.Element, tag: str) -> ET.Element | None:
        node = parent_of.get(el)
        want = f"{{{MEI_NS['mei']}}}{tag}"
        while node is not None:
            if node.tag == want:
                return node
            node = parent_of.get(node)
        return None

    print("\nfirst 8 notes as a join table row "
          "(measure, staff, layer, pitch, grace, chord):")
    for n in mei_notes[:8]:
        measure = ancestor(n, "measure")
        staff = ancestor(n, "staff")
        layer = ancestor(n, "layer")
        chord = ancestor(n, "chord")
        accid = n.find("mei:accid", MEI_NS)
        accid_val = (n.get("accid") or n.get("accid.ges")
                     or (accid is not None and (accid.get("accid")
                                                or accid.get("accid.ges"))))
        print(f"  {n.get(XML_ID)}: m={measure.get('n')} "
              f"staff={staff.get('n')} layer={layer.get('n')} "
              f"pitch={n.get('pname')}{accid_val or ''}{n.get('oct')} "
              f"grace={n.get('grace')} chord={chord.get(XML_ID) if chord is not None else None}")

    # attribute census over all notes — what can the table rely on?
    attr_counts = Counter(k for n in mei_notes for k in n.attrib)
    print("\nnote attribute census:", dict(attr_counts))

    # --- what lives in the slash measures? (staff 7 = drums) -----------------
    print("\ndrum staff (n=7) contents per measure:")
    for m in mei.findall(".//mei:measure", MEI_NS):
        for st in m.findall("mei:staff", MEI_NS):
            if st.get("n") == "7":
                kids = [c.tag.split("}")[-1] for layer in st for c in layer]
                print(f"  m{m.get('n')}: {kids or 'EMPTY layer'}")

    # --- id determinism across loads (with seed) ------------------------------
    tk2 = verovio.toolkit()
    tk2.setOptions({"breaks": "encoded", "font": "Bravura",
                    "transposeToSoundingPitch": True, "xmlIdSeed": 42})
    tk2.loadFile(str(SCORE))
    mei2_ids = {n.get(XML_ID)
                for n in ET.fromstring(tk2.getMEI()).findall(".//mei:note", MEI_NS)}
    print(f"\nsame ids on second load with same seed: {mei_note_ids == mei2_ids}")


if __name__ == "__main__":
    main()
