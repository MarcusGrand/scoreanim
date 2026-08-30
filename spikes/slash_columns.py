"""Do the synthesized slashes line up with the beats the other staves
sit on? (2026-08-31)

Loads testscore, then for every slash measure prints the beat columns
the engraved noteheads/rests make — onset → smallest bbox left edge,
across every part — next to where the slashes actually landed. The
drift the bug report describes should be visible as a growing gap in
the last column.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoreanim.core.engraving.types import EngravingParams          # noqa: E402
from scoreanim.core.engraving.verovio import VerovioEngravingProvider  # noqa: E402
from scoreanim.core.score.identity import ElementKind               # noqa: E402

SCORE = Path(__file__).resolve().parent.parent / "testdata" / "testscore.musicxml"


def measure_of(eid: str) -> int | None:
    parts = str(eid).split(":")
    for tok in parts:
        if tok.startswith("m") and tok[1:].isdigit():
            return int(tok[1:])
    return None


def main() -> None:
    provider = VerovioEngravingProvider()
    engraved = provider.load_detailed(SCORE, EngravingParams())

    cols: dict[tuple[int, int], dict[float, float]] = defaultdict(dict)
    for el in engraved.layout.elements:
        if el.identity.kind not in (ElementKind.NOTEHEAD, ElementKind.REST):
            continue
        m = measure_of(el.identity.element_id)
        if m is None or el.identity.onset is None:
            continue
        key = (el.page, m)
        o = round(el.identity.onset, 6)
        x = el.bbox.x
        if o not in cols[key] or x < cols[key][o]:
            cols[key][o] = x

    slashes = [e for e in engraved.layout.elements
               if e.identity.kind is ElementKind.SLASH]
    by_measure: dict[int, list] = defaultdict(list)
    for s in slashes:
        by_measure[measure_of(s.identity.element_id)].append(s)

    for m in sorted(by_measure):
        group = sorted(by_measure[m], key=lambda e: e.identity.onset)
        page = group[0].page
        column = cols.get((page, m), {})
        print(f"\n--- m{m} (page {page}, system {group[0].system}) ---")
        print("  columns:", ", ".join(
            f"{o:g}@{x:.1f}" for o, x in sorted(column.items())))
        for s in group:
            o = round(s.identity.onset, 6)
            have = column.get(o)
            drift = "" if have is None else f"  drift {s.bbox.x - have:+.1f}"
            print(f"  slash onset {o:g}: left={s.bbox.x:.1f} "
                  f"column={'-' if have is None else f'{have:.1f}'}{drift}")


if __name__ == "__main__":
    main()
