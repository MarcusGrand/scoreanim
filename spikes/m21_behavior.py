"""Phase 1, task T0 — music21 behavior spike.

Confirms the assumptions behind ScoreModel and the identity join (plan
D1/D2):
1. Does music21 expose <measure-style><slash/>? (expected: dropped)
2. toSoundingPitch(): does it produce concert pitch matching Verovio's
   transposeToSoundingPitch, and does removing octave-only <transpose>
   elements keep guitar/bass at written octave?
3. Grace notes: offsets, flags, how they attach.
4. Voice numbering inside measures.
5. What <forward>-only (slash) measures parse into.
6. Do any parts split into multiple PartStaff objects?

Run: .venv/bin/python spikes/m21_behavior.py
"""

from pathlib import Path
import xml.etree.ElementTree as ET

import music21 as m21

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"


def neutralize_octave_only_transposes(xml_bytes: bytes) -> bytes:
    """Remove <transpose> elements with chromatic==0 and diatonic==0
    (octave-only) — the plan-D1 canonicalization."""
    root = ET.fromstring(xml_bytes)
    removed = 0
    for attributes in root.iter("attributes"):
        for tr in list(attributes.findall("transpose")):
            chromatic = float(tr.findtext("chromatic", "0"))
            diatonic = float(tr.findtext("diatonic", "0"))
            if chromatic == 0 and diatonic == 0:
                attributes.remove(tr)
                removed += 1
    print(f"neutralized {removed} octave-only <transpose> elements")
    return ET.tostring(root)


def first_notes(part: m21.stream.Part, n: int = 3) -> list[str]:
    return [p.nameWithOctave
            for p in part.flatten().notes[:n]
            for p in (p.pitches if hasattr(p, "pitches") else [p.pitch])][:n]


def main() -> None:
    raw = SCORE.read_bytes()
    canonical = neutralize_octave_only_transposes(raw)

    score = m21.converter.parse(canonical.decode(), format="musicxml")
    parts = list(score.parts)
    print(f"\nparts ({len(parts)}):")
    for p in parts:
        print(f"  id={p.id!r} name={p.partName!r} class={type(p).__name__}")

    # --- 6. multi-staff / PartStaff check ------------------------------------
    part_staffs = [p for p in parts if isinstance(p, m21.stream.PartStaff)]
    print(f"\nPartStaff objects: {len(part_staffs)}")

    # --- 2. toSoundingPitch --------------------------------------------------
    p1, p5, p6 = parts[0], parts[4], parts[5]
    print("\nbefore toSoundingPitch:")
    print(f"  P1 {p1.partName!r} first notes: {first_notes(p1)}  "
          f"key: {p1.flatten().getElementsByClass(m21.key.KeySignature).first()}")
    print(f"  P5 {p5.partName!r} first notes: {first_notes(p5)}")
    print(f"  P6 {p6.partName!r} first notes: {first_notes(p6)}")
    score.toSoundingPitch(inPlace=True)
    print("after toSoundingPitch:")
    print(f"  P1 first notes: {first_notes(p1)}  "
          f"key: {p1.flatten().getElementsByClass(m21.key.KeySignature).first()}")
    print(f"  P5 first notes: {first_notes(p5)}   (should be UNCHANGED)")
    print(f"  P6 first notes: {first_notes(p6)}   (should be UNCHANGED)")

    # --- 1 & 5. slash measures in the drum part ------------------------------
    drums = parts[6]
    print(f"\ndrum part {drums.partName!r}, measures 2-4 contents:")
    for m in drums.getElementsByClass(m21.stream.Measure):
        if m.number in (2, 3, 4):
            elems = [f"{type(e).__name__}(off={e.offset}, "
                     f"dur={getattr(e, 'quarterLength', '?')})"
                     for e in m]
            print(f"  m{m.number} (mdur={m.duration.quarterLength}): {elems}")
    # any trace of the slash measure-style anywhere?
    slashy = [e for e in score.recurse()
              if "slash" in type(e).__name__.lower()
              or "Slash" in str(getattr(e, "classes", ""))]
    print(f"objects with 'slash' in class name anywhere: {len(slashy)}")

    # --- 3. grace notes -------------------------------------------------------
    print("\ngrace notes:")
    for p in parts:
        for n in p.recurse().notes:
            if n.duration.isGrace:
                m = n.getContextByClass(m21.stream.Measure)
                print(f"  part={p.partName!r} m{m.number} offset={n.offset} "
                      f"pitches={[pp.nameWithOctave for pp in n.pitches]} "
                      f"ql={n.quarterLength}")

    # --- 4. voice numbering ---------------------------------------------------
    print("\nvoice ids seen per part (measure containers):")
    for p in parts:
        vids = {v.id for m in p.getElementsByClass(m21.stream.Measure)
                for v in m.voices}
        print(f"  {p.partName!r}: {sorted(vids, key=str) or 'no Voice containers'}")

    # --- onset sanity: global offsets in quarter notes -------------------------
    flat = parts[0].flatten()
    print("\nP1 first 5 note global offsets (quarterLength units):")
    for n in list(flat.notes)[:5]:
        print(f"  offset={float(n.offset)} pitch(es)="
              f"{[pp.nameWithOctave for pp in n.pitches]} ql={float(n.quarterLength)}")


if __name__ == "__main__":
    main()
