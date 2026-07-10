"""Phase 1 exit criteria: print, for a real score, every notehead (and
synthesized slash) with (part, onset_beats, page, x, y).

Run: python -m scoreanim.tools.dump_notes testdata/testscore.musicxml
"""

from __future__ import annotations

import sys
from pathlib import Path

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio_adapter import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    layout = VerovioEngravingProvider().load(Path(sys.argv[1]),
                                             EngravingParams())
    rows = [e for e in layout.elements
            if e.identity.kind in (ElementKind.NOTEHEAD, ElementKind.SLASH)]
    rows.sort(key=lambda e: (e.identity.onset or 0.0, e.page, e.y, e.x))
    print(f"{'element_id':38s} {'part':22s} {'onset':>8s} {'page':>4s} "
          f"{'x':>8s} {'y':>8s}")
    for e in rows:
        print(f"{str(e.identity.element_id):38s} "
              f"{(e.identity.part_name or ''):22s} "
              f"{e.identity.onset:8.3f} {e.page:4d} {e.x:8.1f} {e.y:8.1f}")
    print(f"\n{len(rows)} noteheads/slashes "
          f"({sum(1 for e in rows if e.identity.kind is ElementKind.SLASH)} "
          f"slashes) across {len(layout.pages)} pages")


if __name__ == "__main__":
    main()
