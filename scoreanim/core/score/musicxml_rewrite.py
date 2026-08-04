"""The canonical-MusicXML rewrite passes (M5.0 split).

`musicxml_prep` does two unrelated jobs: it READS facts out of the raw
XML that neither Verovio nor music21 exposes (parts, slash/repeat
regions, credits, page geometry), and it REWRITES the tree so the bytes
both libraries see carry the user's intent. This module holds the
rewriters; `musicxml_prep.prepare()` stays the orchestrator that names
the pass order, and the spec dataclasses keep their home there (so no
downstream import changes).

Every pass here is the same shape: a tree in, mutated in place, nothing
returned but incidental counts. They are the Phase 8 / 9 / 10R / 12
injection pattern — the document stores intent, the XML is re-derived on
every load (CLAUDE.md rule 5).

The break passes moved to `musicxml_breaks` on 2026-08-03, when this
module went past the size ceiling; the stem passes are in
`musicxml_stems`. `musicxml_prep` re-exports all three families.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

if TYPE_CHECKING:      # the specs live in musicxml_prep; importing them at
                       # runtime would be circular (prepare() calls us)
    from scoreanim.core.score.musicxml_prep import (PartCondenseSpec,
                                                    PartGroupSpec,
                                                    PartTextSpec)


def _drop_redundant_trailing_forwards(root: ET.Element) -> int:
    """Dorico positions <harmony> with a <backup>/<forward> pair. When the
    last chord symbol of a measure sits on that measure's last note, the
    closing <forward> is the measure's final timed element: musically a
    no-op (nothing follows it), but Verovio's MusicXML importer
    materializes it as a trailing <space>, which LENGTHENS the engraved
    measure and corrupts the timemap the whole app treats as the beat
    authority (rule 12).

    Only REDUNDANT trailing forwards are dropped — ones landing at or
    before the measure's already-filled length. A trailing forward that
    advances past it is real content (a bar-repeat measure is exactly one
    such forward, rule 10) and is left alone. <harmony> is untouched.
    Returns how many were removed.
    """
    removed = 0
    for measure in root.iter("measure"):
        while True:
            cursor = 0
            filled = 0
            last_forward = None
            for el in measure:
                if el.tag == "note":
                    if (el.find("chord") is not None
                            or el.find("grace") is not None):
                        continue
                    cursor += int(el.findtext("duration") or 0)
                    filled = max(filled, cursor)
                elif el.tag == "backup":
                    cursor -= int(el.findtext("duration") or 0)
                elif el.tag == "forward":
                    last_forward = (el, cursor + int(el.findtext("duration")
                                                     or 0))
                    cursor = last_forward[1]
            timed = [el for el in measure
                     if el.tag in ("note", "backup", "forward")]
            if (last_forward is not None and timed
                    and timed[-1] is last_forward[0]
                    and last_forward[1] <= filled):
                measure.remove(last_forward[0])
                removed += 1
            else:
                break
    return removed


def _voice_cursor(measure: ET.Element) -> int:
    """Net time-cursor advance of a measure's voice-1 flow, in divisions
    (chord members and graces carry no duration; backup rewinds)."""
    cur = 0
    for el in measure:
        if el.tag == "note":
            if el.find("chord") is not None or el.find("grace") is not None:
                continue
            cur += int(el.findtext("duration") or 0)
        elif el.tag == "forward":
            cur += int(el.findtext("duration") or 0)
        elif el.tag == "backup":
            cur -= int(el.findtext("duration") or 0)
    return cur


def _apply_condense(root: ET.Element,
                    specs: tuple[PartCondenseSpec, ...]) -> None:
    """Merge each spec's contiguous parts onto the first part's staff, one
    voice per source player (Phase 12.3). Runs FIRST in prepare so every
    downstream pass (labels, _parts, slash/repeat scans, groups) sees the
    condensed part-list. The rewrite mirrors spikes/condense_prep.py, which
    verified the naive two-voice merge renders cleanly."""
    if not specs:
        return
    part_list = root.find("part-list")
    if part_list is None:
        raise ValueError("MusicXML has no <part-list>")

    for spec in specs:
        if len(spec.parts) < 2:
            raise ValueError(f"condense group needs >= 2 parts, got {spec.parts}")
        parts_by_id = {p.get("id", ""): p for p in root.findall("part")}
        sp_by_id = {sp.get("id", ""): sp
                    for sp in part_list.findall("score-part")}
        score_part_ids = [sp.get("id", "")
                          for sp in part_list.findall("score-part")]
        for pid in spec.parts:
            if pid not in score_part_ids:
                raise ValueError(f"condense group names unknown part {pid!r}")
            staves = [int(s.text) for s in parts_by_id[pid].iter("staves")
                      if s.text]
            if staves and max(staves) > 1:
                raise ValueError(f"condense of multi-staff part {pid!r} is "
                                 "not supported in v1")
        indices = [score_part_ids.index(pid) for pid in spec.parts]
        if indices != list(range(min(indices), min(indices) + len(indices))):
            raise ValueError("condense group parts must be contiguous in "
                             f"score order, got {spec.parts}")

        keep = str(spec.parts[0])
        keep_part = parts_by_id[keep]
        keep_measures = keep_part.findall("measure")
        if spec.name:        # "" keeps the first part's own label
            _set_part_text(sp_by_id[keep], "part-name", "part-name-display",
                           spec.name)
        if spec.abbreviation:
            _set_part_text(sp_by_id[keep], "part-abbreviation",
                           "part-abbreviation-display", spec.abbreviation)

        for offset, absorb in enumerate(spec.parts[1:], start=1):
            absorb_part = parts_by_id[str(absorb)]
            for km, am in zip(keep_measures, absorb_part.findall("measure")):
                cursor = _voice_cursor(km)     # measure start (stays == dur:
                                               # each appended player nets 0)
                if cursor > 0:
                    bk = ET.SubElement(km, "backup")
                    ET.SubElement(bk, "duration").text = str(cursor)
                for el in am:
                    if el.tag not in ("note", "backup", "forward", "direction"):
                        continue          # skip attributes/print/barline
                    e = copy.deepcopy(el)
                    v = e.find("voice")
                    if v is not None and v.text and v.text.isdigit():
                        v.text = str(int(v.text) + offset)
                    st = e.find("staff")
                    if st is not None:
                        st.text = "1"     # shared staff
                    km.append(e)
            root.remove(absorb_part)
            part_list.remove(sp_by_id[str(absorb)])


def _apply_text_overrides(root: ET.Element,
                          texts: tuple[PartTextSpec, ...]) -> None:
    """Rewrite part labels in the <part-list> (Phase 9.3). Runs BEFORE
    _parts so PartInfo carries the effective names — part_id never
    changes, so ids, the join, and every keying are untouched."""
    if not texts:
        return
    part_list = root.find("part-list")
    if part_list is None:
        raise ValueError("MusicXML has no <part-list>")
    by_id = {sp.get("id", ""): sp for sp in part_list.findall("score-part")}
    for spec in texts:
        sp = by_id.get(str(spec.part))
        if sp is None:
            raise ValueError(f"part text override names unknown part "
                             f"{spec.part!r}")
        if spec.name is not None:
            _set_part_text(sp, "part-name", "part-name-display", spec.name)
        if spec.abbreviation is not None:
            _set_part_text(sp, "part-abbreviation",
                           "part-abbreviation-display", spec.abbreviation)


def _set_part_text(sp: ET.Element, plain_tag: str, display_tag: str,
                   value: str) -> None:
    """Write BOTH the plain element and its -display twin: Verovio reads
    the display when present and ignores the plain; _parts reads the
    plain (spike findings, spikes/NOTES.md "Phase 9"). Non-blank values
    clear print-object="no" from both — it suppresses even non-empty
    text. "" stays an explicit blank (Verovio drops the label)."""
    plain = sp.find(plain_tag)
    if plain is None:
        # childless Elements are falsy — `find(a) or find(b)` would skip
        # an existing empty display element, so test None explicitly
        anchor = sp.find("part-name-display")
        if anchor is None:
            anchor = sp.find("part-name")
        index = list(sp).index(anchor) + 1 if anchor is not None else 0
        plain = ET.Element(plain_tag)
        sp.insert(index, plain)
    plain.text = value
    display = sp.find(display_tag)
    if value:
        plain.attrib.pop("print-object", None)
        if display is not None:
            display.attrib.pop("print-object", None)
    if display is not None:
        for dt in list(display.findall("display-text")):
            display.remove(dt)
        ET.SubElement(display, "display-text").text = value


def _neutralize_octave_only_transposes(root: ET.Element) -> None:
    for attributes in root.iter("attributes"):
        for tr in list(attributes.findall("transpose")):
            chromatic = float(tr.findtext("chromatic", "0"))
            diatonic = float(tr.findtext("diatonic", "0"))
            if chromatic == 0 and diatonic == 0:
                attributes.remove(tr)


def _inject_part_groups(root: ET.Element,
                        groups: tuple[PartGroupSpec, ...]) -> None:
    """Insert <part-group> start/stop pairs into the <part-list>.

    Numbering continues past any groups already in the file (the fixture
    has none — Dorico exported without them, which is BACKLOG 1).
    """
    if not groups:
        return
    part_list = root.find("part-list")
    if part_list is None:
        raise ValueError("MusicXML has no <part-list>")
    existing = [int(pg.get("number", "0"))
                for pg in part_list.findall("part-group")]
    next_number = max(existing, default=0) + 1

    score_part_ids = [sp.get("id", "")
                      for sp in part_list.findall("score-part")]
    for i, group in enumerate(groups):
        indices = []
        for pid in group.parts:
            if pid not in score_part_ids:
                raise ValueError(f"staff group names unknown part {pid!r}")
            indices.append(score_part_ids.index(pid))
        if indices != list(range(min(indices), min(indices) + len(indices))):
            raise ValueError("staff group parts must be contiguous in "
                             f"score order, got {group.parts}")

        start = ET.Element("part-group",
                           {"type": "start", "number": str(next_number + i)})
        ET.SubElement(start, "group-symbol").text = group.symbol
        ET.SubElement(start, "group-barline").text = \
            "yes" if group.join_barlines else "no"
        stop = ET.Element("part-group",
                          {"type": "stop", "number": str(next_number + i)})

        # positions in the CURRENT child list (shifts as groups land)
        kids = list(part_list)
        first = next(k for k, el in enumerate(kids)
                     if el.tag == "score-part"
                     and el.get("id") == group.parts[0])
        last = next(k for k, el in enumerate(kids)
                    if el.tag == "score-part"
                    and el.get("id") == group.parts[-1])
        part_list.insert(last + 1, stop)     # stop first; `first` stays valid
        part_list.insert(first, start)
