"""Hide-empty-staves on the FIRST system too (kept) — Marcus request
2026-07-24 during M1: the Phase 10R optimize round-trip deliberately
leaves the first system full (engraving convention, Verovio default).
Verovio's knob for the exception is `condenseFirstPage` (bool, default
false): with condense semantics active it also condenses/optimizes the
first page. This spike freezes:

A. staves/system with optimize alone vs optimize+condenseFirstPage on
   video_test and bigband1 — does the first system actually hide?
B. id + timemap transparency: the option must not disturb xml:ids or
   the timemap (goldens/overrides depend on deterministic ids).

Run: .venv/bin/python spikes/hide_first_system.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "spikes"))

from phase10r_spike import (  # noqa: E402
    make_toolkit, optimized_mei, staves_per_system, timemap_fingerprint)

from scoreanim.core.score.musicxml_prep import prepare  # noqa: E402

VIDEO = ROOT / "testdata" / "video_test.musicxml"
BIGBAND = ROOT / "testdata" / "bigband1.musicxml"


def two_pass(prep, extra=None):
    """Both passes get the same options (the provider builds pass-2
    toolkits with _make_toolkit too)."""
    tk = make_toolkit(prep, extra)
    assert tk.loadData(prep.canonical_xml)
    tk2 = make_toolkit(prep, extra)
    assert tk2.loadData(optimized_mei(tk.getMEI()))
    return tk2


def ids_of(tk):
    import re
    return set(re.findall(r'xml:id="([^"]+)"', tk.getMEI()))


def main() -> None:
    for name, path in (("video", VIDEO), ("bigband1", BIGBAND)):
        prep = prepare(path)
        plain = two_pass(prep)
        first = two_pass(prep, {"condenseFirstPage": True})
        print(f"== {name} ==")
        print(f"  optimize only:        {staves_per_system(plain)}"
              f" ({plain.getPageCount()}p)")
        print(f"  + condenseFirstPage:  {staves_per_system(first)}"
              f" ({first.getPageCount()}p)")
        same_ids = ids_of(plain) == ids_of(first)
        same_tm = timemap_fingerprint(plain) == timemap_fingerprint(first)
        print(f"  ids identical: {same_ids} · timemap identical: {same_tm}")


if __name__ == "__main__":
    main()
