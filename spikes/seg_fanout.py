"""M3.3 spike: the `:seg` fan-out question, against the real id grammar.

Open since Phase 5.3 (BACKLOG 9): a spanner broken across systems is
several elements, so a per-element style override targets ONE segment.
Should the Selection panel fan an override out to every segment of the
same source spanner? The roadmap recommends yes; this measures whether
the id grammar actually supports doing it, and what the fan-out sets
look like on real scores.

What has to be true for a fan-out to be well-defined:

  1. a segment id is exactly `<source id>:seg<k>` and nothing else in
     the score uses that suffix shape;
  2. segments never nest (no `…:seg1:seg2`), so stripping one suffix
     always lands on the source;
  3. a segment's identity is otherwise IDENTICAL to its source's (same
     kind, part, staff, voice, onset, extent) — i.e. the segments really
     are one musical object, which is the whole premise of fanning out;
  4. every segment's source is actually present as an element (so a
     fan-out from any member reaches the whole set).

Run: python spikes/seg_fanout.py
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoreanim.core.engraving.types import EngravingParams   # noqa: E402
from scoreanim.core.engraving.verovio import (               # noqa: E402
    VerovioEngravingProvider)

TESTDATA = Path(__file__).resolve().parent.parent / "testdata"
FIXTURES = ("testscore.musicxml", "video_test.musicxml",
            "complex1.musicxml", "complex3.musicxml", "bigband1.musicxml")

SEG_RE = re.compile(r"^(?P<source>.+):seg(?P<k>\d+)$")


def audit(path: Path) -> None:
    provider = VerovioEngravingProvider()
    layout = provider.load(path, EngravingParams())
    by_id = {str(el.identity.element_id): el.identity
             for el in layout.elements}

    families: dict[str, list[str]] = defaultdict(list)
    nested = []
    orphan = []
    mismatched = []
    for eid, identity in by_id.items():
        m = SEG_RE.match(eid)
        if m is None:
            continue
        source = m.group("source")
        families[source].append(eid)
        if SEG_RE.match(source):
            nested.append(eid)                      # invariant 2
        src = by_id.get(source)
        if src is None:
            orphan.append(eid)                      # invariant 4
            continue
        same = (src.kind == identity.kind
                and src.part == identity.part
                and src.staff == identity.staff
                and src.voice == identity.voice
                and src.onset == identity.onset
                and src.extent == identity.extent)
        if not same:
            mismatched.append(eid)                  # invariant 3

    # invariant 1: does ":seg<digits>" ever end an id that is NOT a
    # continuation segment? (i.e. could the suffix be minted by anything
    # else and get swept into a fan-out by accident)
    kinds = {by_id[s].kind.name for s in families}
    total_segs = sum(len(v) for v in families.values())
    sizes = sorted((len(v) + 1 for v in families.values()), reverse=True)

    print(f"\n{path.name}")
    print(f"  elements {len(by_id)} | broken spanners {len(families)} | "
          f"segment elements {total_segs}")
    print(f"  source kinds: {sorted(kinds) or '—'}")
    print(f"  family sizes (source + segments): {sizes or '—'}")
    print(f"  nested (…:segA:segB) : {len(nested)}   [want 0]")
    print(f"  orphan (no source)   : {len(orphan)}   [want 0]")
    print(f"  identity mismatch    : {len(mismatched)}   [want 0]")
    if families:
        src, segs = max(families.items(), key=lambda kv: len(kv[1]))
        print(f"  widest family: {src}")
        for s in sorted(segs):
            print(f"                 + {s}")


def main() -> None:
    print("Fan-out feasibility: is `<source>:seg<k>` a sound family key?")
    for name in FIXTURES:
        path = TESTDATA / name
        if not path.exists():
            print(f"\n{name}: missing, skipped")
            continue
        try:
            audit(path)
        except Exception as exc:                      # noqa: BLE001
            print(f"\n{name}: load failed — {exc}")


if __name__ == "__main__":
    main()
