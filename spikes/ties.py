"""Phase 0 follow-up — investigate Verovio's "5 ties left open" warning.

The MusicXML's <tie> elements balance to zero per part, so the warning is
about Verovio's importer failing to MATCH specific ties. Strategy: convert
to MEI and find <tie> elements whose @endid is missing, then map their
@startid back to part/measure/pitch via the MEI tree.

Run: .venv/bin/python spikes/ties.py
"""

from pathlib import Path
import xml.etree.ElementTree as ET

import verovio

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"
MEI_NS = {"mei": "http://www.music-encoding.org/ns/mei"}


def main() -> None:
    tk = verovio.toolkit()
    tk.setOptions({"breaks": "encoded", "xmlIdSeed": 1})
    if not tk.loadFile(str(SCORE)):
        raise SystemExit("load failed")

    mei = ET.fromstring(tk.getMEI())

    # index: note id -> (pitch, octave), and note id -> enclosing measure/staff
    note_info: dict[str, str] = {}
    context: dict[str, tuple[str, str]] = {}
    for measure in mei.iter("{http://www.music-encoding.org/ns/mei}measure"):
        m_n = measure.get("n")
        for staff in measure.findall(".//mei:staff", MEI_NS):
            s_n = staff.get("n")
            for note in staff.iter("{http://www.music-encoding.org/ns/mei}note"):
                nid = note.get("{http://www.w3.org/XML/1998/namespace}id")
                note_info[nid] = f"{note.get('pname', '?')}{note.get('oct', '?')}"
                context[nid] = (m_n, s_n)

    ties = list(mei.iter("{http://www.music-encoding.org/ns/mei}tie"))
    open_ties = [t for t in ties if not t.get("endid")]
    print(f"MEI ties total: {len(ties)}, without @endid: {len(open_ties)}")
    for t in open_ties:
        startid = (t.get("startid") or "").lstrip("#")
        m, s = context.get(startid, ("?", "?"))
        print(f"  tie from {startid} (pitch {note_info.get(startid)}) "
              f"in measure {m}, staff {s}")


if __name__ == "__main__":
    main()
