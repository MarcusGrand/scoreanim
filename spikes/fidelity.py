"""Phase 0, task 0.2 — Dorico → Verovio fidelity spike.

Loads testdata/testscore.musicxml with encoded breaks honored, page size
derived from the score's own <defaults>, renders every page to
spikes/out/page-<n>.svg, and prints the page/system/measure structure so
it can be compared against the Dorico PDF (testdata/testscore.pdf).

Run: .venv/bin/python spikes/fidelity.py
"""

from pathlib import Path
import xml.etree.ElementTree as ET

import verovio

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"
OUT = ROOT / "spikes" / "out"


def page_size_from_musicxml(path: Path) -> tuple[float, float]:
    """Return (width, height) in tenths-of-mm, from <defaults>."""
    tree = ET.parse(path)
    scaling = tree.find("./defaults/scaling")
    mm_per_40_tenths = float(scaling.find("millimeters").text)
    tenths = float(scaling.find("tenths").text)
    mm_per_tenth = mm_per_40_tenths / tenths
    layout = tree.find("./defaults/page-layout")
    height_tenths = float(layout.find("page-height").text)
    width_tenths = float(layout.find("page-width").text)
    # Verovio pageWidth/pageHeight are in 1/10 mm (A4 default = 2100 x 2970)
    return (width_tenths * mm_per_tenth * 10, height_tenths * mm_per_tenth * 10)


def render(sounding: bool) -> None:
    """Render all pages; sounding=True transposes to concert pitch
    (the PDF is a concert-pitch score; the MusicXML encodes written pitch)."""
    width, height = page_size_from_musicxml(SCORE)

    tk = verovio.toolkit()
    options = {
        "breaks": "encoded",          # honor new-system / new-page from the file
        "font": "Bravura",            # match Dorico's engraving font
        "pageWidth": round(width),
        "pageHeight": round(height),
        "scaleToPageSize": True,      # fit Verovio's layout scale to that page
        "header": "encoded",          # only render header/footer if encoded
        "footer": "encoded",
        "svgHtml5": False,
        "svgViewBox": True,           # scalable SVG with viewBox
        "transposeToSoundingPitch": sounding,
    }
    tk.setOptions(options)
    print(f"\n=== {'sounding (concert) pitch' if sounding else 'written pitch'} ===")
    print(f"verovio {tk.getVersion()}  options: {options}")

    if not tk.loadFile(str(SCORE)):
        raise SystemExit("FAILED to load the MusicXML file")

    page_count = tk.getPageCount()
    print(f"page count: {page_count}")

    suffix = "-concert" if sounding else ""
    OUT.mkdir(exist_ok=True)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    for page in range(1, page_count + 1):
        svg = tk.renderToSVG(page)
        out_path = OUT / f"page-{page}{suffix}.svg"
        out_path.write_text(svg)

        root = ET.fromstring(svg)
        systems = root.findall(".//svg:g[@class='system']", ns)
        print(f"page {page}  ->  {out_path.relative_to(ROOT)}")
        for i, system in enumerate(systems, 1):
            measures = system.findall(".//svg:g[@class='measure']", ns)
            print(f"  system {i}: {len(measures)} measures")


def main() -> None:
    width, height = page_size_from_musicxml(SCORE)
    print(f"score page size from <defaults>: {width:.0f} x {height:.0f} (1/10 mm)")
    render(sounding=False)
    render(sounding=True)


if __name__ == "__main__":
    main()
