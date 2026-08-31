"""Invisible notes standing in for a slash or bar-repeat region.

Verovio draws nothing for either region kind — both import as empty
<space> (rule 10) — which used to cost us two different things.

First, empty-staff hiding. scoreDef@optimize judges a staff by its
notes, so the moment a system held only region measures of a staff,
optimize hid it, the rule-10 guard fired, and the provider gave up
hiding for the WHOLE score ("hide-unavailable"). Measured in
spikes/region_fill.py: an INVISIBLE note keeps the staff alive where an
invisible rest does not (optimize exists precisely to hide resting
staves).

Second, and why the fill now runs on every load rather than only under
hiding (2026-08-31): WHERE the slashes go. We used to compute that
ourselves, and our arithmetic put Nidelven's first slash between the
key signature and the time signature. A slash follows the same rules as
the quarter note it stands for, so we let Verovio place it: a slash
region is filled with one invisible note PER SLASH UNIT, and synthesis
reads each slash's x off the note Verovio laid out for it. A bar-repeat
region is still filled whole-bar — a % is centred in its bar and needs
the keep-alive only.

This transform feeds VEROVIO ONLY. It never touches
PreparedScore.canonical_xml: music21 reads those bytes too, and a fill
note there would join as a phantom onset. The fill notes carry minted
ids under FILL_ID_PREFIX (MusicXML @id survives to MEI xml:id and into
the SVG — measured); the decomposer emits no element, no note record
and no ink for them, and records their geometry alone. The rule-10
guard stays behind this as a safety net.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

FILL_ID_PREFIX = "scoreanim-fill-"


def slash_fill_id(part, measure: int, index: int) -> str:
    """The id of the note standing in for slash `index` of a measure.
    Synthesis looks the geometry up under this name, so the two sides
    have to spell it the same way — hence one function."""
    return f"{FILL_ID_PREFIX}{part}-m{measure}-slash{index}"


def fill_region_measures(xml: str, slash_regions=(),
                         repeat_regions=()) -> str:
    """The canonical bytes with every region measure's whole-bar
    <forward> replaced by invisible notes of the same total duration
    (the measure sum is untouched). A slash region gets one note per
    slash unit, named by `slash_fill_id`; a bar-repeat region gets one
    for the whole bar. Returns the input unchanged when there is
    nothing to fill. Pure — deterministic ids, no state."""
    if not slash_regions and not repeat_regions:
        return xml
    root = ET.fromstring(xml)
    parts = {p.get("id", ""): p for p in root.findall("part")}
    filled = 0
    for region in slash_regions:
        filled += _fill_region(parts, region, per_unit=True)
    for region in repeat_regions:
        filled += _fill_region(parts, region, per_unit=False)
    return ET.tostring(root, encoding="unicode") if filled else xml


def _fill_region(parts, region, per_unit: bool) -> int:
    part = parts.get(str(region.part))
    if part is None:
        return 0
    measures = part.findall("measure")
    pitches = _middle_line_pitches(measures)
    divisions = _divisions_per_measure(measures)
    filled = 0
    for ordinal in range(region.start_measure,
                         min(region.stop_measure, len(measures) + 1)):
        measure = measures[ordinal - 1]
        pitch = pitches[ordinal - 1]
        unit = _unit_duration(region, divisions[ordinal - 1]) if per_unit else 0
        slot = 0
        for k, fwd in enumerate(measure.findall("forward")):
            total = int(float(fwd.findtext("duration") or 0))
            if total <= 0:
                continue
            index = list(measure).index(fwd)
            measure.remove(fwd)
            # One note per slash unit where the bar divides evenly. It
            # does in every fixture; a bar that does not (an odd meter
            # against the slash unit) keeps one whole-bar note under the
            # plain name, which synthesis will not find — so that
            # measure falls back to spreading its slashes evenly.
            exact = bool(unit) and total % unit == 0
            count = total // unit if exact else 1
            duration = str(total // count)
            for j in range(count):
                name = (slash_fill_id(region.part, ordinal, slot + j)
                        if per_unit and exact
                        else f"{FILL_ID_PREFIX}{region.part}-m{ordinal}-{k}")
                measure.insert(index + j,
                               _invisible_note(name, duration, pitch))
            slot += count
            filled += 1
    return filled


def _unit_duration(region, divisions: int) -> int:
    """The slash unit in MusicXML duration units, or 0 when it does not
    land on a whole number of them."""
    exact = divisions * region.slash_unit_quarters
    return int(round(exact)) if abs(exact - round(exact)) < 1e-6 else 0


def _divisions_per_measure(measures) -> list[int]:
    """<divisions> in force in each measure. It is stated once and
    carries forward, so a region measure usually does not restate it."""
    divisions = 1
    out: list[int] = []
    for measure in measures:
        for d in measure.iter("divisions"):
            divisions = int(float(d.text or 1))
        out.append(divisions)
    return out


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
