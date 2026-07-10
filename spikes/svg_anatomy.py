"""Phase 0, task 0.4 — Verovio SVG anatomy spike.

Parses page 1 of the rendered test score and reports:
- every element class Verovio emits, with counts and id coverage
- whether noteheads and slurs are individually addressable
- the nesting path from page root down to one notehead
- overall SVG structure (nested svg, defs/use scheme, coordinate system)

Run: .venv/bin/python spikes/svg_anatomy.py   (after spikes/fidelity.py)
"""

from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
PAGE1 = ROOT / "spikes" / "out" / "page-1.svg"

NS = {"svg": "http://www.w3.org/2000/svg"}


def main() -> None:
    tree = ET.parse(PAGE1)
    root = tree.getroot()

    # --- overall structure --------------------------------------------------
    print("top-level children of outer <svg>:")
    for child in root:
        tag = child.tag.split('}')[-1]
        print(f"  <{tag}> class={child.get('class')!r} id={child.get('id')!r} "
              f"viewBox={child.get('viewBox')!r}")

    # --- class census -------------------------------------------------------
    counts: Counter[str] = Counter()
    with_id: Counter[str] = Counter()
    for g in root.iter():
        cls = g.get("class")
        if cls:
            counts[cls] += 1
            if g.get("id"):
                with_id[cls] += 1
    print(f"\nelement classes on page 1 ({sum(counts.values())} classed elements):")
    for cls, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {cls:20s} count={n:4d}  with_id={with_id[cls]:4d}")

    # --- addressability check ----------------------------------------------
    def ids_of(cls: str) -> list[str]:
        return [g.get("id") for g in root.iter()
                if g.get("class") == cls and g.get("id")]

    for cls in ("note", "notehead", "stem", "beam", "slur", "tie", "dynam",
                "chord", "verse", "hairpin"):
        ids = ids_of(cls)
        uniq = len(set(ids))
        print(f"addressable {cls:9s}: {len(ids):4d} elements, {uniq:4d} unique ids")

    # --- nesting path to the first notehead ---------------------------------
    parent_of = {c: p for p in root.iter() for c in p}
    target = next(g for g in root.iter() if g.get("class") == "notehead")
    path = []
    node = target
    while node is not None:
        tag = node.tag.split('}')[-1]
        path.append(f"<{tag} class={node.get('class')!r} id={node.get('id')!r}>")
        node = parent_of.get(node)
    print("\nnesting path from first notehead up to the SVG root:")
    for i, line in enumerate(reversed(path)):
        print("  " * i + line)

    # --- how is the glyph actually drawn? ------------------------------------
    print("\nchildren of that notehead:")
    for child in target:
        tag = child.tag.split('}')[-1]
        attrs = {k: v for k, v in child.attrib.items()}
        print(f"  <{tag}> {attrs}")

    # --- one slur: how is it drawn? ------------------------------------------
    slur = next((g for g in root.iter() if g.get("class") == "slur"), None)
    if slur is not None:
        print(f"\nfirst slur id={slur.get('id')!r}, children:")
        for child in slur:
            tag = child.tag.split('}')[-1]
            d = child.get("d", "")
            print(f"  <{tag}> d={d[:80]}{'...' if len(d) > 80 else ''}")


if __name__ == "__main__":
    main()
