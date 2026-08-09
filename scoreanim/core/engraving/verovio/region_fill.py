"""Keep slash/repeat-region staves visible under optimize (2026-08-09).

Verovio's empty-staff hiding (scoreDef@optimize) judges a staff by its
notes, and a slash or bar-repeat region imports as empty <space> — so
the moment a system holds only region measures of a staff, optimize
hides it, the rule-10 guard fires, and the provider used to give up
hiding for the WHOLE score ("hide-unavailable"). A user system break
that isolated a region measure could flip a working score into that
state after the fact.

The fix, measured in spikes/region_fill.py: an INVISIBLE note keeps
the staff alive under optimize where an invisible rest does not
(optimize exists precisely to hide resting staves). Each whole-bar
<forward> in a region measure is replaced by a pitched note carrying
print-object="no" — Verovio turns that into MEI @visible="false" and
draws the group visibility="hidden", so no ink appears.

This transform feeds VEROVIO ONLY. It never touches
PreparedScore.canonical_xml: music21 reads those bytes too, and a fill
note there would join as a phantom onset. The fill notes carry minted
ids under FILL_ID_PREFIX (MusicXML @id survives to MEI xml:id and into
the SVG — measured), and the decomposer skips that prefix wholesale,
so no element, no note record and no stray ink ever reaches the
pipeline. The rule-10 guard stays behind this as a safety net.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

FILL_ID_PREFIX = "scoreanim-fill-"


def fill_region_measures(xml: str, regions) -> str:
    """The canonical bytes with every region measure's whole-bar
    <forward> replaced by an invisible note of the same duration (the
    measure sum is untouched). Returns the input unchanged when there
    is nothing to fill. Pure — deterministic ids, no state."""
    if not regions:
        return xml
    root = ET.fromstring(xml)
    parts = {p.get("id", ""): p for p in root.findall("part")}
    filled = 0
    for region in regions:
        part = parts.get(str(region.part))
        if part is None:
            continue
        measures = part.findall("measure")
        pitches = _middle_line_pitches(measures)
        for ordinal in range(region.start_measure,
                             min(region.stop_measure, len(measures) + 1)):
            measure = measures[ordinal - 1]
            for k, fwd in enumerate(measure.findall("forward")):
                duration = fwd.findtext("duration")
                if duration is None:
                    continue
                index = list(measure).index(fwd)
                measure.remove(fwd)
                measure.insert(index, _invisible_note(
                    f"{FILL_ID_PREFIX}{region.part}-m{ordinal}-{k}",
                    duration, pitches[ordinal - 1]))
                filled += 1
    return ET.tostring(root, encoding="unicode") if filled else xml


# Diatonic scale for clef arithmetic (index = step within an octave).
_STEPS = "CDEFGAB"
# Clef anchor: the (step, octave) sitting ON the clef's own line.
_CLEF_ANCHOR = {"G": ("G", 4), "F": ("F", 3), "C": ("C", 4)}
_CLEF_DEFAULT_LINE = {"G": 2, "F": 4, "C": 3}


def _middle_line_pitches(measures) -> list[tuple[str, str]]:
    """The staff's middle-line pitch, per measure, tracking the clef in
    force. The fill note must sit ON the staff or Verovio reserves
    vertical room for it — invisible ink still takes space in the
    engraver's justification (measured: a B4 over a bass clef pushed
    the whole system 30 units apart)."""
    step, octave = "B", "4"                 # treble/percussion default
    out: list[tuple[str, str]] = []
    for measure in measures:
        for clef in measure.iter("clef"):
            sign = (clef.findtext("sign") or "").strip()
            if sign in _CLEF_ANCHOR:
                anchor_step, anchor_oct = _CLEF_ANCHOR[sign]
                line = int(clef.findtext("line")
                           or _CLEF_DEFAULT_LINE[sign])
                shift = int(clef.findtext("clef-octave-change") or 0)
                # middle line = the anchor moved 2 diatonic steps per
                # line up to line 3, plus the clef's octave change
                index = (_STEPS.index(anchor_step)
                         + 2 * (3 - line))
                octave_n = anchor_oct + index // 7 + shift
                step, octave = _STEPS[index % 7], str(octave_n)
            elif sign == "percussion":
                step, octave = "B", "4"     # drawn with treble spacing
        out.append((step, octave))
    return out


def _invisible_note(note_id: str, duration: str,
                    pitch_so: tuple[str, str]) -> ET.Element:
    # middle line of the clef in force, so no ledger lines and no
    # vertical room reserved; print-object="no" → MEI @visible="false"
    # → SVG visibility="hidden" (spike-measured, all three hops)
    note = ET.Element("note", {"print-object": "no", "id": note_id})
    pitch = ET.SubElement(note, "pitch")
    ET.SubElement(pitch, "step").text = pitch_so[0]
    ET.SubElement(pitch, "octave").text = pitch_so[1]
    ET.SubElement(note, "duration").text = duration
    ET.SubElement(note, "voice").text = "1"
    return note
