"""Phase 9, task 9.3 — part-label override spike.

Questions, against testdata/testscore.musicxml (every part carries BOTH
<part-name>/<part-abbreviation> AND their -display twins; P1/P2
abbreviations are EMPTY with print-object="no"):

1. Which element does Verovio's label/labelAbbr read — <part-name> or
   <part-name-display>? (Decides what _apply_text_overrides must edit.)
2. Does giving P1 an abbreviation require clearing print-object="no" to
   emit labelAbbr on systems 2+? Does an empty-string name suppress the
   label?
3. Id stability through the PRODUCTION adapter: does a rename keep the
   full id set identical, and does adding a first P1 abbreviation shift
   the page-scoped `score:p{n}:text:{seq}` ids (the expected accepted
   limit)?
4. Does lengthening the longest name shift the staff ink right (the
   label column re-derives — rule 7's "score shifts to fit")?

Renders mirror the production adapter options. Run:
.venv/bin/python spikes/part_label.py
"""

import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import verovio

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def neutralize_octave_transposes(root: ET.Element) -> None:
    for attributes in root.iter("attributes"):
        for tr in list(attributes.findall("transpose")):
            if (float(tr.findtext("chromatic", "0")) == 0
                    and float(tr.findtext("diatonic", "0")) == 0):
                attributes.remove(tr)


def page_size(root: ET.Element) -> tuple[float, float]:
    scaling = root.find("./defaults/scaling")
    per_tenth = (float(scaling.findtext("millimeters"))
                 / float(scaling.findtext("tenths")) * 10)
    layout = root.find("./defaults/page-layout")
    return (float(layout.findtext("page-width")) * per_tenth,
            float(layout.findtext("page-height")) * per_tenth)


def score_part(root: ET.Element, part_id: str) -> ET.Element:
    return next(sp for sp in root.find("part-list").iter("score-part")
                if sp.get("id") == part_id)


def set_display(sp: ET.Element, tag: str, value: str) -> None:
    disp = sp.find(tag)
    if disp is None:
        return
    for dt in disp.findall("display-text"):
        dt.text = value


def render(name: str, mutate) -> list[ET.Element]:
    root = ET.fromstring(SCORE.read_bytes())
    neutralize_octave_transposes(root)
    mutate(root)
    width, height = page_size(root)
    tk = verovio.toolkit()
    tk.setOptions({
        "breaks": "encoded", "font": "Bravura",
        "pageWidth": round(width), "pageHeight": round(height),
        "scaleToPageSize": True,
        "header": "none", "footer": "encoded",
        "svgHtml5": False, "svgViewBox": True,
        "transposeToSoundingPitch": True,
        "xmlIdSeed": 42,
    })
    if not tk.loadData(ET.tostring(root, encoding="unicode")):
        raise SystemExit(f"{name}: Verovio failed to load")
    pages = [ET.fromstring(tk.renderToSVG(p))
             for p in range(1, tk.getPageCount() + 1)]
    print(f"[{name}] {len(pages)} pages")
    return pages


def tag_of(el: ET.Element) -> str:
    return el.tag.split("}")[-1]


def label_texts(pages, cls: str) -> list[list[str]]:
    """Per page: the flattened text of every <g class=cls>."""
    out = []
    for page in pages:
        texts = []
        for g in page.iter():
            if g.get("class") == cls:
                texts.append("".join(t.strip() for t in g.itertext()
                                     if t.strip()))
        out.append(texts)
    return out


def staff_min_x(page: ET.Element) -> float:
    xs = []
    for g in page.iter():
        if g.get("class") == "staff":
            for el in g.iter():
                if tag_of(el) == "path":
                    vals = [float(m) for m in
                            _NUM.findall(el.get("d") or "")]
                    if vals:
                        xs.append(vals[0])
    return min(xs) if xs else float("nan")


def adapter_ids(mutate) -> set[str]:
    """Full ElementId set through the PRODUCTION adapter (question 3)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from scoreanim.core.engraving.types import EngravingParams
    from scoreanim.core.engraving.verovio import \
        VerovioEngravingProvider

    root = ET.fromstring(SCORE.read_bytes())
    mutate(root)
    with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False,
                                     mode="w") as f:
        f.write(ET.tostring(root, encoding="unicode"))
        tmp = Path(f.name)
    try:
        e = VerovioEngravingProvider().load_detailed(tmp, EngravingParams())
        return {str(el.identity.element_id) for el in e.layout.elements}
    finally:
        tmp.unlink()


def main() -> None:
    # -- Q1: plain vs display element ------------------------------------
    def rename_plain_only(root):
        score_part(root, "P4").find("part-name").text = "Trombones"

    def rename_display_only(root):
        set_display(score_part(root, "P4"), "part-name-display", "Trombones")

    def rename_both(root):
        rename_plain_only(root)
        rename_display_only(root)

    base = render("baseline", lambda root: None)
    plain = render("plain-only", rename_plain_only)
    display = render("display-only", rename_display_only)
    both = render("both", rename_both)

    print("\nQ1 which element wins (page-1 label texts):")
    print("  baseline:    ", label_texts(base, "label")[0])
    print("  plain-only:  ", label_texts(plain, "label")[0])
    print("  display-only:", label_texts(display, "label")[0])
    print("  both:        ", label_texts(both, "label")[0])

    # -- Q2: P1 abbreviation + print-object; empty-string name -----------
    def abbr_keep_po(root):
        sp = score_part(root, "P1")
        sp.find("part-abbreviation").text = "S.A.T. 1"
        set_display(sp, "part-abbreviation-display", "S.A.T. 1")

    def abbr_clear_po(root):
        sp = score_part(root, "P1")
        ab = sp.find("part-abbreviation")
        ab.text = "S.A.T. 1"
        ab.attrib.pop("print-object", None)
        disp = sp.find("part-abbreviation-display")
        if disp is not None:
            disp.attrib.pop("print-object", None)
        set_display(sp, "part-abbreviation-display", "S.A.T. 1")

    def blank_name(root):
        sp = score_part(root, "P4")
        sp.find("part-name").text = ""
        set_display(sp, "part-name-display", "")

    keep = render("abbr-keep-po", abbr_keep_po)
    clear = render("abbr-clear-po", abbr_clear_po)
    blank = render("blank-name", blank_name)

    print("\nQ2 P1 abbreviation (page-2 labelAbbr texts):")
    print("  baseline:  ", label_texts(base, "labelAbbr")[1])
    print("  keep po=no:", label_texts(keep, "labelAbbr")[1])
    print("  clear po:  ", label_texts(clear, "labelAbbr")[1])
    print("Q2b blank P4 name (page-1 labels):",
          label_texts(blank, "label")[0])

    # -- Q3: id stability through the production adapter -----------------
    def prep_mutate(mut):
        def m(root):
            mut(root)
        return m

    ids_base = adapter_ids(lambda root: None)
    ids_rename = adapter_ids(rename_both)
    ids_abbr = adapter_ids(abbr_clear_po)
    print("\nQ3 id stability (production adapter):")
    print(f"  rename: identical id set: {ids_rename == ids_base}")
    only_base = sorted(ids_base - ids_abbr)
    only_abbr = sorted(ids_abbr - ids_base)
    print(f"  first-P1-abbr: -{len(only_base)} +{len(only_abbr)} ids")
    print(f"    gone: {only_base[:6]}")
    print(f"    new:  {only_abbr[:6]}")

    # -- Q4: score shifts to fit ------------------------------------------
    def long_name(root):
        sp = score_part(root, "P4")
        sp.find("part-name").text = "Trombones and Friends Ensemble"
        set_display(sp, "part-name-display",
                    "Trombones and Friends Ensemble")

    long_pages = render("long-name", long_name)
    print("\nQ4 staff min-x, page 1:")
    print(f"  baseline: {staff_min_x(base[0]):.1f}")
    print(f"  long name: {staff_min_x(long_pages[0]):.1f}")


if __name__ == "__main__":
    main()
