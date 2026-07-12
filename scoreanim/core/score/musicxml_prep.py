"""Canonical MusicXML preparation (plan D1).

One prep step produces the exact bytes fed to BOTH Verovio and music21,
plus facts extracted from the raw XML that neither library exposes:

- Octave-only <transpose> elements (chromatic==0, diatonic==0 — e.g.
  guitar, bass guitar) are removed, so concert-pitch rendering keeps
  those parts at their conventional written octave (CLAUDE.md rule 9)
  and pitch comparison between the two libraries holds by construction.
- Staff groups (Phase 8): user-defined groupings are injected as
  <part-group> elements into the <part-list>, so Verovio engraves the
  bracket/brace and joins barlines through the group (with its own
  collision avoidance — spikes/NOTES.md Phase 8). The document stores
  the groupings as intent; the injected XML and all geometry are
  re-derived here on every load (rule 5).
- Slash regions (<measure-style><slash/>) — music21 drops them entirely
  (verified, spikes/NOTES.md), so they are scanned here.
- Page geometry from <defaults> — Verovio does not read it itself.
- Credit texts (<credit>) — from Phase 2 on the engraved header is
  suppressed and title/composer/… become stage-level text elements
  (ARCHITECTURE.md §3 ruling 4); their defaults are seeded from these.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from scoreanim.core.score.identity import PartId

# <slash-type> note value → quarter-note units
_SLASH_UNIT_QUARTERS = {
    "whole": 4.0, "half": 2.0, "quarter": 1.0, "eighth": 0.5, "16th": 0.25,
}


@dataclass(frozen=True)
class PartGroupSpec:
    """Prep-seam input for one injected <part-group> (Phase 8).

    Neutral twin of the document's StaffGroup intent (core/project may
    import core/score, never the reverse); the UI converts at the seam.
    Parts must be contiguous in score order — validated here as defense
    in depth behind the Add/Edit/RemoveStaffGroup commands.
    """
    parts: tuple[PartId, ...]
    symbol: str = "bracket"      # MusicXML group-symbol vocabulary
    join_barlines: bool = True


@dataclass(frozen=True)
class PartInfo:
    index: int                   # 0-based document order (music21 parts order)
    part_id: PartId              # MusicXML id, e.g. "P1"
    name: str
    staff_count: int
    first_staff: int             # 1-based global staff number (Verovio/MEI @n)


@dataclass(frozen=True)
class SlashRegion:
    part: PartId
    start_measure: int           # inclusive
    stop_measure: int            # exclusive ([start, stop) — a measure
                                 # carrying <slash type="stop"> is NOT slash)
    slash_unit_quarters: float


@dataclass(frozen=True)
class CreditText:
    credit_type: str | None      # "title", "composer", …; None if untyped
    text: str
    page: int                    # 1-based
    font_size_pt: float | None   # MusicXML font-size is in points
    justify: str | None          # "left" | "center" | "right"
    color: str | None            # e.g. "#C0C0C0"
    default_x: float | None      # tenths, from the page's left edge
    default_y: float | None      # tenths, from the page's BOTTOM edge (y-up)


@dataclass(frozen=True)
class PreparedScore:
    canonical_xml: str
    parts: tuple[PartInfo, ...]
    slash_regions: tuple[SlashRegion, ...]
    credits: tuple[CreditText, ...]
    page_width: float            # page units (1/10 mm)
    page_height: float
    units_per_tenth: float       # tenths → page units (1/10 mm) factor

    def part_for_staff(self, staff_n: int) -> PartInfo:
        for p in self.parts:
            if p.first_staff <= staff_n < p.first_staff + p.staff_count:
                return p
        raise KeyError(f"no part owns staff {staff_n}")


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


def _page_size(root: ET.Element) -> tuple[float, float, float]:
    """(width, height, units_per_tenth) in 1/10 mm from <defaults>
    (as spikes/fidelity.py)."""
    scaling = root.find("./defaults/scaling")
    layout = root.find("./defaults/page-layout")
    if scaling is None or layout is None:
        raise ValueError("MusicXML <defaults> lacks scaling/page-layout; "
                         "cannot derive page geometry")
    mm = float(scaling.findtext("millimeters"))
    tenths = float(scaling.findtext("tenths"))
    units_per_tenth = mm / tenths * 10
    width = float(layout.findtext("page-width")) * units_per_tenth
    height = float(layout.findtext("page-height")) * units_per_tenth
    return width, height, units_per_tenth


def _credits(root: ET.Element) -> tuple[CreditText, ...]:
    """One CreditText per <credit-words>, carrying its credit's type.
    Untyped credits (Dorico's "other" fields, e.g. the lyricist line) keep
    credit_type None."""
    def fnum(el: ET.Element, name: str) -> float | None:
        v = el.get(name)
        return float(v) if v is not None else None

    out: list[CreditText] = []
    for credit in root.findall("credit"):
        ctype = credit.findtext("credit-type")
        page = int(credit.get("page", "1"))
        for words in credit.iter("credit-words"):
            text = (words.text or "").strip()
            if not text:
                continue
            out.append(CreditText(
                credit_type=ctype.strip() if ctype else None,
                text=text, page=page,
                font_size_pt=fnum(words, "font-size"),
                justify=words.get("justify") or words.get("halign"),
                color=words.get("color"),
                default_x=fnum(words, "default-x"),
                default_y=fnum(words, "default-y"),
            ))
    return tuple(out)


def _parts(root: ET.Element) -> tuple[PartInfo, ...]:
    staff_counts: dict[str, int] = {}
    for part in root.findall("part"):
        staves = [int(s.text) for s in part.iter("staves") if s.text]
        staff_counts[part.get("id", "")] = max(staves) if staves else 1

    infos: list[PartInfo] = []
    next_staff = 1
    for index, sp in enumerate(root.findall("./part-list/score-part")):
        pid = sp.get("id", "")
        name = (sp.findtext("part-name") or "").strip()
        count = staff_counts.get(pid, 1)
        infos.append(PartInfo(index=index, part_id=PartId(pid), name=name,
                              staff_count=count, first_staff=next_staff))
        next_staff += count
    return tuple(infos)


def _measure_number(measure: ET.Element, ordinal: int) -> int:
    try:
        return int(measure.get("number", ""))
    except ValueError:
        return ordinal


def _slash_regions(root: ET.Element) -> tuple[SlashRegion, ...]:
    regions: list[SlashRegion] = []
    for part in root.findall("part"):
        pid = PartId(part.get("id", ""))
        open_start: int | None = None
        open_unit = 1.0
        last_n = 0
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            n = _measure_number(measure, ordinal)
            last_n = n
            for slash in measure.iter("slash"):
                unit = _SLASH_UNIT_QUARTERS.get(
                    slash.findtext("slash-type", "quarter"), 1.0)
                # a measure may carry both stop (close old) and start (open
                # new) — process stop first so [start, stop) semantics hold
                if slash.get("type") == "stop" and open_start is not None:
                    regions.append(SlashRegion(pid, open_start, n, open_unit))
                    open_start = None
            for slash in measure.iter("slash"):
                if slash.get("type") == "start":
                    open_start = n
                    open_unit = _SLASH_UNIT_QUARTERS.get(
                        slash.findtext("slash-type", "quarter"), 1.0)
        if open_start is not None:            # region open to the end
            regions.append(SlashRegion(pid, open_start, last_n + 1, open_unit))
    return tuple(regions)


def prepare(score_path: Path,
            groups: tuple[PartGroupSpec, ...] = ()) -> PreparedScore:
    root = ET.fromstring(score_path.read_bytes())
    if root.tag != "score-partwise":
        raise ValueError(f"expected score-partwise MusicXML, got <{root.tag}>")

    parts = _parts(root)
    slash_regions = _slash_regions(root)
    credits = _credits(root)
    width, height, units_per_tenth = _page_size(root)
    _neutralize_octave_only_transposes(root)
    _inject_part_groups(root, groups)

    return PreparedScore(
        canonical_xml=ET.tostring(root, encoding="unicode"),
        parts=parts,
        slash_regions=slash_regions,
        credits=credits,
        page_width=width,
        page_height=height,
        units_per_tenth=units_per_tenth,
    )
