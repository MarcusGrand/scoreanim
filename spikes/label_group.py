"""M7 follow-up — where does a MULTI-STAFF part's label sit, and when is
it drawn?

`spikes/label_part.py` measured the label→part join over 6 configurations
and found order-over-labelled-staves exact, 129/129. Building it surfaced
a case those 6 did not contain: a part with more than one staff.

A single-staff part hangs its label on its own `<staffDef>`. A multi-staff
part (video_test's Piano, `<staves>2</staves>`) hangs it on the
`<staffGrp>` that holds its two staffDefs instead — so the label is
invisible to a staffDef-only index, and the count check refuses the whole
system. That part is why video_test placed 0 of 7 labels.

Worse for a pure order join: Verovio drew 'Piano' FIRST, ahead of the
staff-1 label, even though the Piano is the 5th part. So the drawn order
is not staff order when groups are involved, and the fix needs to know
what the real emission order IS.

This spike measures exactly that, on the only two fixtures that have group
labels at all (video_test: Piano; complex2: Synth) plus the ordinary ones
as controls, across every system of every page so the `labelAbbr` tier is
measured too, and under hiding and condensing.

Run: PYTHONPATH=. .venv/bin/python spikes/label_group.py
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoreanim.core.engraving.types import EngravingParams  # noqa: E402
from scoreanim.core.engraving.verovio import mei_index  # noqa: E402
from scoreanim.core.engraving.verovio.provider import (  # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.score import musicxml_prep  # noqa: E402

TESTDATA = ROOT / "testdata"
_MEI = "{http://www.music-encoding.org/ns/mei}"
_SVG = "{http://www.w3.org/2000/svg}"
_CLASSES = ("label", "labelAbbr")

# (name, file, hide_empty_staves?)
CASES = [
    ("video_test", "video_test.musicxml", False),
    ("video_test + hidden", "video_test.musicxml", True),
    ("complex2", "complex2.musicxml", False),
    ("complex2 + hidden", "complex2.musicxml", True),
    ("testscore (control)", "testscore.musicxml", False),
    ("bigband1 + hidden (control)", "bigband1.musicxml", True),
]


def mei_side(mei_text: str) -> dict[str, list[tuple[int, str, str]]]:
    """Per class, the labels in MEI DOCUMENT order as
    (first staff number, where it hangs, text)."""
    root = ET.fromstring(mei_text)
    parents = {c: p for p in root.iter() for c in p}
    out: dict[str, list[tuple[int, str, str]]] = {c: [] for c in _CLASSES}
    for el in root.iter():
        cls = el.tag.removeprefix(_MEI)
        if cls not in _CLASSES:
            continue
        host = parents.get(el)
        if host is None:
            continue
        htag = host.tag.removeprefix(_MEI)
        # a staffGrp's label belongs to the part its FIRST staffDef starts
        first = (host if htag == "staffDef"
                 else next(host.iter(f"{_MEI}staffDef"), None))
        n = int(first.get("n")) if first is not None and first.get("n") else 0
        out[cls].append((n, htag, "".join(el.itertext()).strip()))
    return out


def svg_side(svg: str) -> list[list[tuple[str, str]]]:
    """Per system, its drawn labels in document order as (class, text)."""
    root = ET.fromstring(svg)
    systems = []
    for system in root.iter(f"{_SVG}g"):
        if system.get("class") != "system":
            continue
        drawn = []
        for node in system.iter(f"{_SVG}g"):
            if node.get("class") in _CLASSES:
                drawn.append((node.get("class"),
                              "".join(t.strip() for t in node.itertext()
                                      if t.strip())))
        systems.append(drawn)
    return systems


def run_case(name: str, filename: str, hide: bool) -> None:
    print(f"\n{'=' * 76}\n{name}   ({filename}, hide_empty_staves={hide})\n"
          f"{'=' * 76}")
    prep = musicxml_prep.prepare(TESTDATA / filename)
    provider = VerovioEngravingProvider()
    params = EngravingParams()
    tk = provider._make_toolkit(prep, params, None, False)
    if not tk.loadData(prep.canonical_xml):
        raise ValueError("Verovio failed to load")
    if hide:
        optimized = mei_index._set_scoredef_optimize(tk.getMEI())
        tk = provider._make_toolkit(prep, params, None, False)
        if not tk.loadData(optimized):
            raise ValueError("Verovio failed to reload optimized MEI")

    mei_text = tk.getMEI()
    mei = mei_side(mei_text)
    for cls in _CLASSES:
        if mei[cls]:
            print(f"  MEI {cls:9} order: " + ", ".join(
                f"{t!r}@{h}(staff {n})" for n, h, t in mei[cls]))

    total = groups_first = staff_order = 0
    for page in range(1, tk.getPageCount() + 1):
        for sys_i, drawn in enumerate(svg_side(tk.renderToSVG(page)), 1):
            if not drawn:
                continue
            cls = drawn[0][0]
            assert all(c == cls for c, _ in drawn), "mixed classes in a system"
            texts = [t for _, t in drawn]
            # Where do the group-hosted labels land in the drawn order?
            hosts = {t: h for _, h, t in mei[cls]}
            positions = [i for i, t in enumerate(texts)
                         if hosts.get(t) == "staffGrp"]
            n_groups = len(positions)
            total += 1
            if positions == list(range(n_groups)):
                groups_first += 1
            # And is the drawn order the plain MEI/staff order?
            by_staff = [t for _, _, t in sorted(mei[cls])]
            if texts == [t for t in by_staff if t in texts]:
                staff_order += 1
            if n_groups and sys_i <= 2:
                print(f"    p{page} sys{sys_i} ({cls}): {texts}")
                print(f"      group-hosted at positions {positions} "
                      f"of {len(texts)}")

    print(f"\n  systems with labels: {total}")
    print(f"  group labels drawn FIRST : {groups_first}/{total}")
    print(f"  drawn order == staff order: {staff_order}/{total}")


def main() -> None:
    for name, filename, hide in CASES:
        if not (TESTDATA / filename).exists():
            print(f"\n!! {name}: {filename} not present, skipped")
            continue
        try:
            run_case(name, filename, hide)
        except Exception as exc:                      # keep the sweep going
            print(f"\n!! {name}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
