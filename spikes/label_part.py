"""BACKLOG 14 — can a part label be attributed to its part?

Direct editing of a staff label is blocked on one fact: the adapter
mints labels with `part=None`, and `SetPartText` is keyed by `PartId`,
so the double-click route cannot be completed at all. M3 named the
plausible fix — reach the part through the MEI index, since a label's
xml:id should lead to a `staffDef` — but never measured it, and marked
geometry and vertical order as rejected alternatives.

This spike measures it, because "plausibly" is not enough to justify an
adapter change that moves 12 goldens.

MEASURED ANSWER (2026-07-29), 129 labels over 6 configurations:

  A. by id      0/129   the M3 hypothesis — DEAD
  B. by order   101/129 naive; 28 unpairable
  C. by text    129/129 here, but ambiguous by construction
  D. by order over LABELLED staves   129/129, 0 disagreements

**The M3 hypothesis is false.** A rendered label's SVG id does not exist
in the MEI at all — Verovio mints a throwaway id for the drawn object,
and `getElementAttr` answers "Element not found". Notes join fine (the
control), so this is specific to labels: there is no id join to a
`staffDef`, and the cheap path M3 imagined is not available.

What IS true: the MEI side is clean. Every `<label>`/`<labelAbbr>` hangs
on a `staffDef` carrying `@n`, the GLOBAL staff number, and
`PreparedScore.part_for_staff` turns that into a part for free. So the
data exists and only the join is missing.

The joins measured here, on the fixtures that break naive approaches —
hidden empty staves, condensing, 14 parts, several systems per page:

  A. by id      — the M3 hypothesis (control).
  B. by ORDER in the system — the k-th label group against the k-th
     VISIBLE staff. Not geometry: the staff groups' ids DO join to MEI
     (the adapter already builds `staff_n_by_id` from them), so this
     reads document order, which is how the SVG is emitted. It fails
     whenever a system draws labels for only SOME staves — measured on
     4 of testscore's 5 systems, because a part with an empty
     abbreviation draws nothing after system 1. A naive zip would not
     merely fail there, it would mis-attribute silently.
  C. by TEXT content — the drawn string against the staffDef's own
     label text. Perfect on every fixture here, but that is luck:
     duplicate part names (two "Horn in F") are ambiguous by
     construction, and these fixtures have none.
  D. by ORDER over the staves whose staffDef actually carries a label
     OF THE CLASS BEING DRAWN (`label` on system 1, `labelAbbr` after).
     This is B with the one filter it was missing, and it is exact:
     129/129 paired with zero text disagreements, including under
     hidden staves and condensing.

D is also SELF-CHECKING, which is what makes it safe to build on: every
pairing it makes can be verified against the staffDef's own label text,
so the adapter can attribute only when the text agrees and leave the
label part-less otherwise. A wrong attribution renames the wrong
instrument; refusing to attribute merely leaves the action disabled, so
the failure mode is the harmless one.

A condensed label names the KEPT part (`parts[0]`), measured — which is
also what `SetPartText` would need to write, so condensing raises no
extra decision.

Run: PYTHONPATH=. .venv/bin/python spikes/label_part.py
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoreanim.core.engraving.types import EngravingParams  # noqa: E402
from scoreanim.core.engraving.verovio import mei_index  # noqa: E402
from scoreanim.core.engraving.verovio.kinds import _MEI_NS, _XML_ID  # noqa: E402
from scoreanim.core.engraving.verovio.provider import (  # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.score import musicxml_prep  # noqa: E402

TESTDATA = ROOT / "testdata"
_SVG_NS = "{http://www.w3.org/2000/svg}"
_LABEL_CLASSES = ("label", "labelAbbr")

# (name, file, condense?, hide_empty_staves?)
CASES = [
    ("testscore", "testscore.musicxml", False, False),
    ("testscore + hidden staves", "testscore.musicxml", False, True),
    ("bigband1 + hidden staves", "bigband1.musicxml", False, True),
    ("condense_min", "condense_min.musicxml", False, False),
    ("condense_min CONDENSED", "condense_min.musicxml", True, False),
    ("complex1", "complex1.musicxml", False, False),
]


# -- MEI side ---------------------------------------------------------------

def mei_labels(mei_text: str) -> list[dict]:
    """Every <label>/<labelAbbr>, where it hangs, and the staff number
    that place implies."""
    root = ET.fromstring(mei_text)
    parents = {child: parent for parent in root.iter() for child in parent}
    out = []
    for el in root.iter():
        tag = el.tag.replace(_MEI_NS, "")
        if tag not in _LABEL_CLASSES:
            continue
        parent = parents.get(el)
        ptag = parent.tag.replace(_MEI_NS, "") if parent is not None else None
        out.append({
            "tag": tag,
            "id": el.get(_XML_ID),
            "text": "".join(el.itertext()).strip(),
            "parent": ptag,
            "staff_n": int(parent.get("n")) if ptag == "staffDef"
                       and parent.get("n") else None,
        })
    return out


# -- SVG side ---------------------------------------------------------------

def systems(svg: str) -> list[dict]:
    """Per system, in document order: its label groups and its staff
    groups. Both are read as ORDER, not position."""
    root = ET.fromstring(svg)
    out = []
    for system in root.iter(f"{_SVG_NS}g"):
        if system.get("class") != "system":
            continue
        labels, staves = [], []
        for node in system.iter(f"{_SVG_NS}g"):
            cls = node.get("class")
            if cls in _LABEL_CLASSES:
                text = "".join(t.strip() for t in node.itertext() if t.strip())
                labels.append({"class": cls, "id": node.get("id"),
                               "text": text})
            elif cls == "staff":
                staves.append(node.get("id"))
        out.append({"labels": labels, "staves": staves})
    return out


# -- one fixture ------------------------------------------------------------

def run_case(name: str, filename: str, condense: bool, hide: bool) -> None:
    print(f"\n{'=' * 74}\n{name}   ({filename}, condense={condense}, "
          f"hide_empty_staves={hide})\n{'=' * 74}")
    path = TESTDATA / filename
    provider = VerovioEngravingProvider()
    params = EngravingParams()

    if condense:
        flat = musicxml_prep.prepare(path)
        spec = musicxml_prep.PartCondenseSpec(
            parts=tuple(p.part_id for p in flat.parts),
            name="Condensed 1.2", abbreviation="Cond. 1.2")
        prep = musicxml_prep.prepare(path, condense=(spec,))
    else:
        prep = musicxml_prep.prepare(path)

    print("parts:", ", ".join(f"{p.part_id}(staff {p.first_staff}"
                              f"{'+' if p.staff_count > 1 else ''})"
                              for p in prep.parts))

    # mirror _engrave_prepared, including the hide round-trip
    tk = provider._make_toolkit(prep, params, None, False)
    if not tk.loadData(prep.canonical_xml):
        raise ValueError("Verovio failed to load")
    if hide:
        optimized = mei_index._set_scoredef_optimize(tk.getMEI())
        tk = provider._make_toolkit(prep, params, None, False)
        if not tk.loadData(optimized):
            raise ValueError("Verovio failed to reload optimized MEI")

    mei_text = tk.getMEI()
    labels = mei_labels(mei_text)
    staff_n_by_id = mei_index._container_ns(mei_text, "staff")
    label_text_by_staff: dict[int, set[str]] = {}
    # staff number -> the text of its <label> / its <labelAbbr>, kept
    # apart: system 1 draws the full name, later systems the abbrev,
    # and a part with no abbreviation draws NOTHING on later systems
    text_by_staff_class: dict[tuple[int, str], str] = {}
    for lab in labels:
        if lab["staff_n"] is not None:
            label_text_by_staff.setdefault(lab["staff_n"], set()).add(
                lab["text"])
            text_by_staff_class[(lab["staff_n"], lab["tag"])] = lab["text"]

    hangs = sorted({lab["parent"] for lab in labels})
    print(f"MEI: {len(labels)} labels, all hanging on {hangs}; "
          f"staff numbers seen: "
          f"{sorted(n for n in label_text_by_staff)}")

    pages = tk.getPageCount()
    a_hits = a_total = 0
    b_hits = b_total = b_mismatch = 0
    c_hits = c_ambiguous = c_miss = 0
    d_hits = d_total = d_mismatch = d_skipped = 0
    shown = 0

    for page in range(1, pages + 1):
        for sys_i, system in enumerate(systems(tk.renderToSVG(page)), 1):
            svg_labels = system["labels"]
            if not svg_labels:
                continue
            # -- A: the M3 hypothesis
            for lab in svg_labels:
                a_total += 1
                if lab["id"] in {m["id"] for m in labels}:
                    a_hits += 1

            # -- B: order within the system, against JOINING staff ids.
            # A staff group is emitted once per MEASURE, so the system's
            # staves are the DISTINCT @n values in first-appearance order.
            visible, seen = [], set()
            for sid in system["staves"]:
                n = staff_n_by_id.get(sid)
                if n is not None and n not in seen:
                    seen.add(n)
                    visible.append(n)
            b_total += len(svg_labels)
            if len(svg_labels) == len(visible):
                for lab, staff_n in zip(svg_labels, visible):
                    texts = label_text_by_staff.get(staff_n, set())
                    ok = lab["text"] in texts
                    b_hits += 1
                    b_mismatch += 0 if ok else 1
                    if shown < 8:
                        part = prep.part_for_staff(staff_n)
                        flag = "" if ok else "   << TEXT DISAGREES"
                        print(f"   p{page} sys{sys_i}: {lab['text']!r:26} "
                              f"-> staff {staff_n} -> {part.part_id} "
                              f"({part.name}){flag}")
                        shown += 1
            elif shown < 12:
                print(f"   p{page} sys{sys_i}: COUNT MISMATCH — "
                      f"{len(svg_labels)} labels vs {len(visible)} "
                      f"visible staves")
                shown += 1

            # -- D: order within the system, against the visible staves
            # FILTERED to those whose staffDef actually carries a label
            # of the class being drawn. This is what B was missing.
            cls = svg_labels[0]["class"]
            expected = [n for n in visible
                        if (n, cls) in text_by_staff_class]
            d_total += len(svg_labels)
            if len(svg_labels) == len(expected):
                for lab, staff_n in zip(svg_labels, expected):
                    d_hits += 1
                    if lab["text"] != text_by_staff_class[(staff_n, cls)]:
                        d_mismatch += 1
            else:
                d_skipped += len(svg_labels)
                if shown < 14:
                    print(f"   p{page} sys{sys_i}: D MISMATCH — "
                          f"{len(svg_labels)} drawn vs {len(expected)} "
                          f"expected ({cls})")
                    shown += 1

            # -- C: by text content
            for lab in svg_labels:
                owners = [n for n, texts in label_text_by_staff.items()
                          if lab["text"] in texts]
                if len(owners) == 1:
                    c_hits += 1
                elif len(owners) > 1:
                    c_ambiguous += 1
                else:
                    c_miss += 1

    print(f"\n   A by id      : {a_hits}/{a_total} joined"
          f"   {'(the M3 hypothesis)' if a_hits == 0 else ''}")
    print(f"   B by order   : {b_hits}/{b_total} paired, "
          f"{b_mismatch} whose text disagrees with the staffDef")
    print(f"   C by text    : {c_hits} unique, {c_ambiguous} AMBIGUOUS "
          f"(duplicate names), {c_miss} not found")
    print(f"   D by order over LABELLED staves : {d_hits}/{d_total} paired, "
          f"{d_mismatch} text disagreements, {d_skipped} unpairable")


def main() -> None:
    for name, filename, condense, hide in CASES:
        try:
            run_case(name, filename, condense, hide)
        except Exception as exc:                      # keep the sweep going
            print(f"\n!! {name}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
