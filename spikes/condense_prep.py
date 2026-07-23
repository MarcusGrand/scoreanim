"""Phase 12.0(a) spike — condense-merge prep rewrite (kept).

Decides whether v1 condensing is viable *as designed*: merge two like
complex2 wind parts (Flute 1 = P1, Flute 2 = P2) into ONE staff as two
voices in the canonical MusicXML, render, and judge stems/rests/
collisions on divergent rhythms.

v1 semantics (deliberately naive, per the brief): shared staff, one
voice per source player, combined label "Flute 1.2"; NO a2 unison
collapse, NO divisi logic. The user chooses which parts condense, so
they can pick sane pairs.

Renders BEFORE (P1, P2 on two staves) and AFTER (merged, one staff two
voices) to SVG in the scratchpad for visual review. Read-only w.r.t.
the repo (writes only to the scratchpad out dir).
"""
from __future__ import annotations
import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import verovio

SRC = Path("testdata/complex2.musicxml")
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("spikes/out")
OUT.mkdir(parents=True, exist_ok=True)


def _dur(note_or_el) -> int:
    d = note_or_el.findtext("duration")
    return int(d) if d else 0


def _voice_cursor(measure: ET.Element) -> int:
    """Net time-cursor advance of a measure's (assumed single-voice) flow."""
    cur = 0
    for el in measure:
        if el.tag == "note":
            if el.find("chord") is not None or el.find("grace") is not None:
                continue
            cur += _dur(el)
        elif el.tag == "forward":
            cur += _dur(el)
        elif el.tag == "backup":
            cur -= _dur(el)
    return cur


def build_subset(root: ET.Element, keep_ids: tuple[str, ...]) -> ET.ElementTree:
    """A valid MusicXML with only the given part ids (part-groups dropped)."""
    new = copy.deepcopy(root)
    pl = new.find("part-list")
    for child in list(pl):
        if child.tag == "part-group":
            pl.remove(child)
        elif child.tag == "score-part" and child.get("id") not in keep_ids:
            pl.remove(child)
    for p in list(new.findall("part")):
        if p.get("id") not in keep_ids:
            new.remove(p)
    return ET.ElementTree(new)


def merge_two(root: ET.Element, keep: str, absorb: str,
              label: str, abbr: str) -> ET.ElementTree:
    """Merge `absorb` into `keep` as voice 2 on the shared staff."""
    new = copy.deepcopy(root)
    pl = new.find("part-list")
    # part-list: drop groups + the absorbed score-part; relabel keep.
    keep_sp = None
    for child in list(pl):
        if child.tag == "part-group":
            pl.remove(child)
        elif child.tag == "score-part":
            if child.get("id") == absorb:
                pl.remove(child)
            elif child.get("id") == keep:
                keep_sp = child
    for tag, val in (("part-name", label), ("part-abbreviation", abbr)):
        el = keep_sp.find(tag)
        if el is not None:
            el.text = val
        disp = keep_sp.find(tag + "-display")
        if disp is not None:
            dt = disp.find("display-text")
            if dt is not None:
                dt.text = val

    keep_part = next(p for p in new.findall("part") if p.get("id") == keep)
    absorb_part = next(p for p in new.findall("part") if p.get("id") == absorb)
    new.remove(absorb_part)

    keep_ms = keep_part.findall("measure")
    absorb_ms = absorb_part.findall("measure")
    merged = 0
    for km, am in zip(keep_ms, absorb_ms):
        cursor = _voice_cursor(km)
        if cursor > 0:
            bk = ET.SubElement(km, "backup")
            d = ET.SubElement(bk, "duration")
            d.text = str(cursor)
        # append absorb's voice flow, relabel voice -> +1, force staff 1
        added = False
        for el in am:
            if el.tag not in ("note", "backup", "forward", "direction"):
                continue
            e = copy.deepcopy(el)
            v = e.find("voice")
            if v is not None and v.text and v.text.isdigit():
                v.text = str(int(v.text) + 1)
            st = e.find("staff")
            if st is not None:
                st.text = "1"
            km.append(e)
            added = added or el.tag == "note"
        merged += 1 if added else 0
    return ET.ElementTree(new)


_ATTR_ORDER = ("divisions", "key", "time", "staves", "clef")


def excerpt(tree: ET.ElementTree, lo: int, hi: int) -> ET.ElementTree:
    """Keep measures [lo, hi]; seed the first with prevailing attributes."""
    new = copy.deepcopy(tree.getroot())
    for part in new.findall("part"):
        prevailing: dict[str, ET.Element] = {}
        kept: list[ET.Element] = []
        for m in part.findall("measure"):
            attr = m.find("attributes")
            if attr is not None:
                for tag in _ATTR_ORDER:
                    el = attr.find(tag)
                    if el is not None:
                        prevailing[tag] = copy.deepcopy(el)
            num = int(m.get("number"))
            if lo <= num <= hi:
                kept.append(m)
            part.remove(m)
        for i, m in enumerate(kept):
            for pr in m.findall("print"):
                m.remove(pr)          # let it flow
            if i == 0 and prevailing:
                if m.find("attributes") is None:
                    a = ET.Element("attributes")
                    m.insert(0, a)
                a = m.find("attributes")
                for tag in reversed(_ATTR_ORDER):
                    if a.find(tag) is None and tag in prevailing:
                        a.insert(0, copy.deepcopy(prevailing[tag]))
            part.append(m)
    return ET.ElementTree(new)


def render(tree: ET.ElementTree):
    """Load into Verovio; return (page_count, notehead-density-per-page, tk)."""
    xml = ET.tostring(tree.getroot(), encoding="unicode")
    tk = verovio.toolkit()
    tk.setOptions({
        "breaks": "auto", "transpose": "", "adjustPageHeight": True,
        "pageWidth": 2000, "scale": 40, "footer": "none", "header": "none",
    })
    tk.loadData(xml)
    pages = tk.getPageCount()
    # notehead density per page
    dens = []
    for p in range(1, pages + 1):
        svg = tk.renderToSVG(p)
        dens.append(svg.count("notehead"))
    return pages, dens, tk


def main() -> None:
    root = ET.parse(SRC).getroot()

    # note density per measure to find a divergent-rhythm passage
    def notes_in(pid):
        p = next(x for x in root.findall("part") if x.get("id") == pid)
        return [sum(1 for n in m.iter("note") if n.find("rest") is None)
                for m in p.findall("measure")]
    n1, n2 = notes_in("P1"), notes_in("P2")
    both = [(i + 1, a, b) for i, (a, b) in enumerate(zip(n1, n2)) if a and b]
    both.sort(key=lambda t: -(t[1] + t[2]))
    print("densest measures where BOTH flutes play (measure, P1notes, P2notes):")
    for t in both[:8]:
        print("  ", t)

    before = build_subset(root, ("P1", "P2"))
    # merge on the FULL score, then isolate the merged flute staff for the
    # visual (merge_two keeps every other part — that is the real feature).
    after = build_subset(
        merge_two(root, "P1", "P2", "Flute 1.2", "Fl. 1.2").getroot(), ("P1",))

    bp, bd, _ = render(before)
    ap, ad, _ = render(after)
    print(f"\nBEFORE (2 staves): {bp} pages, notehead density/page: {bd}")
    print(f"AFTER  (1 merged): {ap} pages, notehead density/page: {ad}")

    saved = []
    # focused excerpt of the divergent-rhythm passage (both flutes busy)
    for lo, hi, label in ((60, 68, "mm60-68"), (84, 92, "mm84-92")):
        bx, ax = excerpt(before, lo, hi), excerpt(after, lo, hi)
        _, _, btkx = render(bx)
        _, _, atkx = render(ax)
        fb = OUT / f"condense_before_{label}.svg"
        fa = OUT / f"condense_after_{label}.svg"
        fb.write_text(btkx.renderToSVG(1))
        fa.write_text(atkx.renderToSVG(1))
        saved += [fb, fa]
    print("\nsaved:")
    for s in saved:
        print("  ", s)


if __name__ == "__main__":
    main()
