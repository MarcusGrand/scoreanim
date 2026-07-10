"""Phase 0, task 0.3 — Verovio timemap spike.

Loads testdata/testscore.musicxml, renders Verovio's timemap, prints
element_id -> onset_ms for the first 20 notes, and checks monotonicity.
Also dumps the raw first few timemap entries so the format is documented.

Run: .venv/bin/python spikes/timemap.py
"""

import json
from pathlib import Path

import verovio

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"


def main() -> None:
    tk = verovio.toolkit()
    tk.setOptions({"breaks": "encoded"})
    if not tk.loadFile(str(SCORE)):
        raise SystemExit("FAILED to load the MusicXML file")

    timemap = tk.renderToTimemap({"includeMeasures": True, "includeRests": True})
    print(f"timemap type: {type(timemap).__name__}, entries: {len(timemap)}")
    print("\nraw first 5 entries:")
    for entry in timemap[:5]:
        print(" ", json.dumps(entry))

    # flatten: (onset_ms, element_id) for every note-on
    onsets: list[tuple[float, str]] = []
    for entry in timemap:
        for elem_id in entry.get("on", []):
            onsets.append((entry["tstamp"], elem_id))

    print(f"\ntotal note-on events: {len(onsets)}")
    print("\nfirst 20 notes (element_id -> onset_ms):")
    for tstamp, elem_id in onsets[:20]:
        print(f"  {elem_id}  ->  {tstamp:8.1f} ms")

    stamps = [t for t, _ in onsets]
    monotone = all(a <= b for a, b in zip(stamps, stamps[1:]))
    print(f"\nonsets monotone non-decreasing: {monotone}")
    if not monotone:
        bad = [(i, stamps[i], stamps[i + 1]) for i in range(len(stamps) - 1)
               if stamps[i] > stamps[i + 1]]
        print("violations:", bad[:5])

    # what does an element's own time query say? (Phase 1 will want this)
    first_id = onsets[0][1]
    print(f"\ngetTimesForElement({first_id!r}):",
          tk.getTimesForElement(first_id))


if __name__ == "__main__":
    main()
