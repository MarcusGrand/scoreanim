"""Can invisible content keep a slash/repeat-region staff visible under
Verovio's scoreDef@optimize? (2026-08-09, BACKLOG 310-316.)

The hide-unavailable fallback disables empty-staff hiding for a WHOLE
score the moment optimize would hide a region staff — and a user
system break that isolates a region measure trips it after the fact.
The parked fix: fill region measures with invisible content so Verovio
never judges the staff empty. This spike measures which fill works,
through the REAL pipeline (prepare is wrapped, the provider runs
unmodified):

  A. explicit invisible rest   <note print-object="no"><rest/>…
  B. invisible pitched note    <note print-object="no"><pitch>…
  C. invisible measure rest    <note print-object="no"><rest measure="yes"/>…

For each: does the staff survive where a break isolates it, does the
warning go, do note_records / the timemap move against the flat load,
and how far does the geometry drift on systems that were already right.

Run: python spikes/region_fill.py
"""
from __future__ import annotations

import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import provider as provider_module
from scoreanim.core.engraving.verovio.provider import VerovioEngravingProvider
from scoreanim.core.score.musicxml_prep import SystemBreak, prepare

TESTSCORE = Path("testdata/testscore.musicxml")
VIDEO = Path("testdata/video_test.musicxml")
BAR_REPEAT = Path("testdata/bar_repeat_min.musicxml")


def _fill_note(variant: str, duration: int) -> ET.Element:
    note = ET.Element("note", {"print-object": "no"})
    if variant == "invisible_rest":
        ET.SubElement(note, "rest")
    elif variant == "invisible_measure_rest":
        ET.SubElement(note, "rest", {"measure": "yes"})
    elif variant == "invisible_note":
        pitch = ET.SubElement(note, "pitch")
        ET.SubElement(pitch, "step").text = "B"
        ET.SubElement(pitch, "octave").text = "4"
    else:
        raise ValueError(variant)
    ET.SubElement(note, "duration").text = str(duration)
    ET.SubElement(note, "voice").text = "1"
    return note


def _fill_regions(xml: str, regions, variant: str) -> str:
    """Replace each region measure's whole-bar <forward> with invisible
    content of the same duration (keeps the measure sum intact)."""
    root = ET.fromstring(xml)
    parts = {p.get("id", ""): p for p in root.findall("part")}
    for region in regions:
        part = parts.get(str(region.part))
        if part is None:
            continue
        measures = part.findall("measure")
        for ordinal in range(region.start_measure, region.stop_measure):
            measure = measures[ordinal - 1]
            for fwd in measure.findall("forward"):
                duration = int(fwd.findtext("duration", "0"))
                idx = list(measure).index(fwd)
                measure.remove(fwd)
                measure.insert(idx, _fill_note(variant, duration))
    return ET.tostring(root, encoding="unicode")


def _wrapped_prepare(variant: str):
    def wrapper(*args, **kwargs):
        prep = prepare(*args, **kwargs)
        if variant == "none":
            return prep
        from dataclasses import replace
        filled = _fill_regions(prep.canonical_xml,
                               (*prep.slash_regions, *prep.repeat_regions),
                               variant)
        return replace(prep, canonical_xml=filled)
    return wrapper


def _staves_per_system(engraved):
    out: dict[tuple[int, int], set] = {}
    for e in engraved.layout.elements:
        if e.system is None or e.identity.part is None:
            continue
        out.setdefault((e.page, e.system), set()).add(
            (str(e.identity.part), e.identity.staff))
    return {k: len(v) for k, v in sorted(out.items())}


def _note_key(engraved):
    return sorted((str(r.element_id) for r in engraved.note_records))


def run(path: Path, variant: str, breaks=None, hide=True):
    provider_module.prepare = _wrapped_prepare(variant)
    try:
        return VerovioEngravingProvider().load_detailed(
            path, EngravingParams(), hide_empty_staves=hide, strict=False,
            system_breaks=breaks)
    finally:
        provider_module.prepare = prepare


def report(name: str, engraved, baseline_flat=None):
    codes = sorted({w.code for w in engraved.warnings})
    rows = list(_staves_per_system(engraved).values())
    line = f"{name:34s} warns={codes} staves/system={rows}"
    if baseline_flat is not None:
        same_notes = _note_key(engraved) == _note_key(baseline_flat)
        end_a = max(m.start + m.duration for m in
                    engraved.timeline.measures) \
            if hasattr(engraved.timeline, "measures") else None
        line += f" note_records_identical={same_notes}"
    print(line)


def main() -> None:
    for fixture, breaks in ((TESTSCORE, None),
                            (VIDEO, {21: SystemBreak.FORCE}),
                            (BAR_REPEAT, None)):
        print(f"\n== {fixture.name}"
              + (f" break@{list(breaks)[0]}" if breaks else ""))
        flat = run(fixture, "none", breaks=breaks, hide=False)
        report("flat (no hiding)", flat)
        report("hidden, no fill", run(fixture, "none", breaks=breaks), flat)
        for variant in ("invisible_rest", "invisible_measure_rest",
                        "invisible_note"):
            try:
                report(f"hidden + {variant}",
                       run(fixture, variant, breaks=breaks), flat)
            except Exception as exc:
                print(f"hidden + {variant:24s} RAISED: {exc}")


if __name__ == "__main__":
    main()
