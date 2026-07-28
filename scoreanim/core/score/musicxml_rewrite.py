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
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from enum import Enum
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:      # the specs live in musicxml_prep; importing them at
                       # runtime would be circular (prepare() calls us)
    from scoreanim.core.score.musicxml_prep import (PartCondenseSpec,
                                                    PartGroupSpec,
                                                    PartTextSpec)


class SystemBreak(str, Enum):
    """What the user asked of one measure's system break (M5).

    This is the `<print new-system>` vocabulary, so it lives with the pass
    that writes the attribute and is re-exported from `musicxml_prep` as
    the prep seam's public face. Unlike the `*Spec` dataclasses it has NO
    neutral twin in `core/project`: a two-valued vocabulary has no fields
    to twin, and the layering already permits `core/project` to import
    `core/score` (the `PartId` shape). One enum, no conversion at the
    seam.
    """
    FORCE = "force"          # start a system at this measure
    SUPPRESS = "suppress"    # do NOT start a system at this measure


class PageBreak(str, Enum):
    """What the user asked of one measure's page break (M6).

    `SystemBreak`'s twin, for the `<print new-page>` attribute, and the
    same reasoning applies: it lives with the pass that writes the
    attribute, is re-exported from `musicxml_prep`, and has no neutral
    twin in `core/project` because a two-valued vocabulary has no fields
    to twin.

    Kept a SEPARATE enum from `SystemBreak` rather than one shared
    Force/Suppress vocabulary: the two maps are different documents
    fields with different meanings at the seam, and a mis-keyed value
    should be a type error rather than a silently plausible one.
    """
    FORCE = "force"          # start a page at this measure
    SUPPRESS = "suppress"    # do NOT start a page at this measure


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


def _apply_system_breaks(root: ET.Element,
                         overrides: Mapping[int, SystemBreak]
                         ) -> tuple[int, ...]:
    """Apply the user's system-break intent to `<print new-system>` (M5).

    A deliberate twin of `_repaginate` — part 1 only (Verovio reads print
    layout from the first part, spike section D), keyed by 1-based
    document ordinal (never the printed number, adapter item 12),
    creating `<print>` when absent — with two differences that matter:

    - It is STORED intent, not a derived plan, so unlike `_repaginate` it
      never strips the encoded breaks first. It is a sparse DELTA: a
      measure with no override keeps whatever the file encodes.
    - SUPPRESS also clears a coincident `new-page` (D7, measured in
      spikes/system_breaks.py F2). A page break implies a system break,
      so leaving it would make the suppression a lie — the systems
      simply would not merge. The consequence, stated plainly:
      suppressing a SYSTEM break can move a PAGE break. That is
      acceptable because rule 7(a) already establishes that we own page
      breaks whenever the encoded ones cannot hold their systems, and
      pagination re-derives from here.

    SUPPRESS on a measure with no `<print>` at all writes NOTHING: there
    is no encoded break to suppress, so the override is inert rather than
    an assertion that the measure must not start a system (Verovio would
    honor it identically either way — spike section A3 — but not writing
    keeps the canonical XML a true delta).

    Returns the ordinals that wrote NOTHING, in score order — D10's
    "break-override-inert" warning. That is precisely the set of
    overrides that could not be applied AT THIS SEAM: an ordinal past the
    end of a score since shortened (the loop never reaches it), and a
    suppression whose encoded break has gone (writing "no" over "no").
    It deliberately does NOT mean "had no visible effect", which only a
    second no-override load could establish: forcing a break on a measure
    that already starts a system rewrites the attribute and so is not
    reported, even though the layout is unchanged.
    """
    if not overrides:
        return ()
    parts = root.findall("part")
    if not parts:
        return tuple(sorted(overrides))
    inert = set(overrides)
    for ordinal, measure in enumerate(parts[0].findall("measure"), start=1):
        mode = overrides.get(ordinal)
        if mode is None:
            continue
        pr = measure.find("print")
        if mode is SystemBreak.FORCE:
            if pr is None:
                pr = ET.Element("print")
                measure.insert(0, pr)
            if pr.get("new-system") != "yes":
                pr.set("new-system", "yes")
                inert.discard(ordinal)
        elif mode is SystemBreak.SUPPRESS:
            if pr is not None and (pr.get("new-system") == "yes"
                                   or pr.get("new-page") == "yes"):
                pr.set("new-system", "no")
                if pr.get("new-page") == "yes":
                    pr.set("new-page", "no")       # D7
                inert.discard(ordinal)
        else:
            raise ValueError(f"unknown system break mode {mode!r}")
    return tuple(sorted(inert))


def _promote_page_breaks_to_system(root: ET.Element) -> int:
    """Say out loud the system break every encoded page break implies
    (M6.0, BACKLOG 16 — measured in spikes/page_breaks.py section F).

    Dorico encodes a page break as `new-page="yes"` ALONE: the measure
    carries no `new-system`, because starting a page starts a system by
    definition. That makes the page attribute the measure's ONLY break
    marker, so anything that clears it silently takes the system break
    with it — and `_repaginate` clears every one of them before
    asserting its own plan. The consequence, on `main` before this pass:
    forcing a system break anywhere on a score with page-only markers
    repaginates, and the encoded system structure collapses (testscore
    m19 went from five systems to four, merging 1+2 and 3+4 — spike F2).

    That contradicts rule 7(a)'s own wording, which says repagination
    KEEPS the encoded system breaks. This pass makes the wording true:
    every `new-page="yes"` also gets `new-system="yes"` before anything
    can strip it, so a re-derived page plan can never change system
    content. Measured a total no-op at baseline on all four fixtures —
    systems, pages and element ids identical, goldens unmoved (spike F1)
    — because the two attributes already agree wherever both are read.

    Returns how many measures were promoted. All parts, not just part 1:
    Verovio reads print layout from the first part, but a promotion is
    harmless anywhere and leaving later parts inconsistent with part 1
    would be a trap for the next reader.
    """
    promoted = 0
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            pr = measure.find("print")
            if (pr is not None and pr.get("new-page") == "yes"
                    and pr.get("new-system") != "yes"):
                pr.set("new-system", "yes")
                promoted += 1
    return promoted


def _repaginate(root: ET.Element, break_measures: tuple[int, ...]) -> None:
    """Replace the encoded PAGE breaks with our own (Phase 10R, rule-7
    amendment): keep every encoded system break, strip all new-page
    attributes, and set new-page="yes" at the given system-start
    measures. Part 1 only — Verovio reads print layout from the first
    part (spike section D). Called only when the measured first pass
    overflowed; the plan is derived data, never stored (rule 5).

    "Keep every encoded system break" is only true because of the
    promotion below (M6.0): a page-only marker's system break has to be
    said out loud before the strip, or the strip takes it away."""
    parts = root.findall("part")
    if not parts:
        return
    _promote_page_breaks_to_system(root)
    for part in parts:
        for measure in part.findall("measure"):
            pr = measure.find("print")
            if pr is not None and pr.get("new-page"):
                del pr.attrib["new-page"]
    wanted = set(break_measures)
    # Measure identity is the 1-based document-order ordinal everywhere (see
    # verovio.mei_index._parse_mei): `break_measures` come from the adapter's
    # ordinal-keyed system_of_measure, so match by ordinal here — the printed
    # `number` is neither unique nor consistent (Dorico's "X0"/"X1" bars).
    for ordinal, measure in enumerate(parts[0].findall("measure"), start=1):
        if ordinal in wanted:
            pr = measure.find("print")
            if pr is None:
                pr = ET.Element("print")
                measure.insert(0, pr)
            pr.set("new-page", "yes")
