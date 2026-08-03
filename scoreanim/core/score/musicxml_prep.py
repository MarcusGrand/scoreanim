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

This module holds the spec dataclasses, those scanners, and `prepare()`
as the orchestrator that names the pass order. The passes that REWRITE
the tree live in `musicxml_rewrite` (M5.0 split) and are re-exported
below.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from scoreanim.core.score.identity import PartId
# The tree-rewriting passes live in their own modules (M5.0, split again
# 2026-08-03); they are re-exported here so `prepare`'s callers and the
# tests that reach for a single pass keep importing from one place.
from scoreanim.core.score.musicxml_breaks import (  # noqa: F401
    PageBreak, SystemBreak, _apply_breaks, _promote_page_breaks_to_system,
    _repaginate, _system_only, _wanted_break_attrs)
from scoreanim.core.score.musicxml_rewrite import (  # noqa: F401
    _apply_condense, _apply_text_overrides,
    _drop_redundant_trailing_forwards, _inject_part_groups,
    _neutralize_octave_only_transposes, _set_part_text, _voice_cursor)
from scoreanim.core.score.musicxml_stems import (  # noqa: F401
    StemDirection, _apply_stem_directions, _normalize_stem_directions)

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
class PartTextSpec:
    """Prep-seam input for one part's label override (Phase 9.3).

    Neutral twin of the document's PartTextOverride intent (core/project
    may import core/score, never the reverse — the PartGroupSpec
    precedent); the UI converts at the seam. None fields keep the
    score's own text; "" is an explicit blank (Verovio suppresses the
    label — spike finding, spikes/NOTES.md "Phase 9")."""
    part: PartId
    name: str | None = None
    abbreviation: str | None = None


@dataclass(frozen=True)
class PartCondenseSpec:
    """Prep-seam input to merge contiguous like parts onto ONE staff as one
    voice per source player (Phase 12.3). Neutral twin of the document's
    CondenseGroup intent (core/project may import core/score, never the
    reverse — the PartGroupSpec precedent); the UI converts at the seam.

    Verovio cannot condense from MusicXML, so condensing is a canonical
    rewrite BEFORE engraving: the first part is kept, each later part's
    voice flow is appended behind a <backup> and relabelled to its own
    voice, and the label becomes the combined name. v1 is deliberately
    naive (ruling d): shared staff, one voice per player, NO a2 unison
    collapse and NO divisi logic (BACKLOG). Parts must be contiguous in
    score order and single-staff — validated here as defense behind the
    Add/Edit/RemoveCondenseGroup commands."""
    parts: tuple[PartId, ...]    # >= 2, contiguous; parts[0] is kept
    name: str                    # combined part-name, e.g. "Flute 1.2"
    abbreviation: str = ""       # combined abbreviation, e.g. "Fl. 1.2"


@dataclass(frozen=True)
class PartInfo:
    index: int                   # 0-based document order (music21 parts order)
    part_id: PartId              # MusicXML id, e.g. "P1"
    name: str
    staff_count: int
    first_staff: int             # 1-based global staff number (Verovio/MEI @n)
    abbreviation: str = ""       # <part-abbreviation> (Phase 9.3)


@dataclass(frozen=True)
class SlashRegion:
    part: PartId
    start_measure: int           # inclusive
    stop_measure: int            # exclusive ([start, stop) — a measure
                                 # carrying <slash type="stop"> is NOT slash)
    slash_unit_quarters: float


@dataclass(frozen=True)
class RepeatRegion:
    """A <measure-repeat> span. Verovio's MusicXML importer has no
    measure-repeat support — the repeat bars import as empty <space>
    (verified, spikes/NOTES.md Phase 12) — so like slash regions they are
    scanned here and the % symbol is synthesized in the adapter. [start,
    stop): a measure carrying <measure-repeat type="stop"> is a real fill,
    NOT a repeat. v1 handles single-bar repeats (Dorico's `<measure-repeat
    type="start">1`); `bar_span` records the pattern width for defense."""
    part: PartId
    start_measure: int           # inclusive
    stop_measure: int            # exclusive
    bar_span: int = 1            # measures per repeat pattern (1 = single-bar)


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
    repeat_regions: tuple[RepeatRegion, ...]
    credits: tuple[CreditText, ...]
    page_width: float            # page units (1/10 mm)
    page_height: float
    units_per_tenth: float       # tenths → page units (1/10 mm) factor
    # Break overrides this prep could not apply (M5 D10 / M6 D8): an
    # ordinal past the end of the score, a suppression whose encoded break
    # has gone, or an assertion the file already made. Derived here,
    # warned by the provider — never stored (rule 5). The page half is
    # only PROVISIONALLY inert: never-clip's planner sees the same
    # overrides and can honor a page ordinal this seam could not, so the
    # provider subtracts what the planner acted on before warning (M6.3).
    inert_system_breaks: tuple[int, ...] = ()
    inert_page_breaks: tuple[int, ...] = ()
    # Stem flips this prep could not place (2026-08-03): a minted id
    # whose note is no longer there, because the score changed or
    # condensing renumbered the voice under it. Same contract as the two
    # above — derived here, warned by the provider, never stored.
    inert_stem_directions: tuple[str, ...] = ()

    def part_for_staff(self, staff_n: int) -> PartInfo:
        for p in self.parts:
            if p.first_staff <= staff_n < p.first_staff + p.staff_count:
                return p
        raise KeyError(f"no part owns staff {staff_n}")




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
        abbreviation = (sp.findtext("part-abbreviation") or "").strip()
        count = staff_counts.get(pid, 1)
        infos.append(PartInfo(index=index, part_id=PartId(pid), name=name,
                              staff_count=count, first_staff=next_staff,
                              abbreviation=abbreviation))
        next_staff += count
    return tuple(infos)


def _slash_regions(root: ET.Element) -> tuple[SlashRegion, ...]:
    # Region bounds are 1-based document-order ordinals — the same measure
    # identity the adapter keys staff_geo/measure_start by (never the printed
    # `number`, which collides for Dorico's "X0"/"X1" bars).
    regions: list[SlashRegion] = []
    for part in root.findall("part"):
        pid = PartId(part.get("id", ""))
        open_start: int | None = None
        open_unit = 1.0
        last_n = 0
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            n = ordinal
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


def _repeat_regions(root: ET.Element) -> tuple[RepeatRegion, ...]:
    """Scan <measure-repeat> spans (twin of _slash_regions). [start, stop)
    with stop-before-start within a measure, so a bar carrying both closes
    the old region and opens a new one."""
    regions: list[RepeatRegion] = []
    for part in root.findall("part"):
        pid = PartId(part.get("id", ""))
        open_start: int | None = None
        open_span = 1
        last_n = 0
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            n = ordinal
            last_n = n
            for mr in measure.iter("measure-repeat"):
                if mr.get("type") == "stop" and open_start is not None:
                    regions.append(RepeatRegion(pid, open_start, n, open_span))
                    open_start = None
            for mr in measure.iter("measure-repeat"):
                if mr.get("type") == "start":
                    open_start = n
                    try:
                        open_span = max(1, int((mr.text or "1").strip()))
                    except ValueError:
                        open_span = 1
        if open_start is not None:
            regions.append(RepeatRegion(pid, open_start, last_n + 1, open_span))
    return tuple(regions)





def prepare(score_path: Path,
            groups: tuple[PartGroupSpec, ...] = (),
            texts: tuple[PartTextSpec, ...] = (),
            condense: tuple[PartCondenseSpec, ...] = (),
            page_break_measures: tuple[int, ...] = (),
            system_breaks: Mapping[int, SystemBreak] | None = None,
            page_breaks: Mapping[int, PageBreak] | None = None,
            stem_directions: Mapping[str, StemDirection] | None = None
            ) -> PreparedScore:
    root = ET.fromstring(score_path.read_bytes())
    if root.tag != "score-partwise":
        raise ValueError(f"expected score-partwise MusicXML, got <{root.tag}>")

    _drop_redundant_trailing_forwards(root)  # BEFORE condense:
                                             # _voice_cursor counts forwards
    # BEFORE condense too, and for a sharper reason: each source player
    # is single-voice, so stripping here lets Verovio apply its own
    # voice-1-up / voice-2-down to the merged staff. After condense it
    # would see two voices and leave every condensed staff alone.
    _normalize_stem_directions(root)
    _apply_condense(root, condense)      # FIRST: rewrite the part-list so
                                         # every downstream pass sees the
                                         # condensed structure (Phase 12.3)
    # AFTER condense: the flips are keyed by engraved ids, and condensing
    # renumbers voices. Writes an explicit <stem> over what the strip
    # above left, which is the stated precedence — a flip is the last
    # word on the note it names.
    inert_stems = _apply_stem_directions(root, stem_directions or {})
    _apply_text_overrides(root, texts)   # before _parts: PartInfo carries
                                         # the EFFECTIVE names (Phase 9.3)
    parts = _parts(root)
    slash_regions = _slash_regions(root)
    repeat_regions = _repeat_regions(root)
    credits = _credits(root)
    width, height, units_per_tenth = _page_size(root)
    _neutralize_octave_only_transposes(root)
    _inject_part_groups(root, groups)
    # User break intent first — BOTH maps, in one pass (M6, D3) — and our
    # never-clip repagination on top: the page-break plan the caller
    # passes was measured from an engrave that ALREADY saw these breaks,
    # so repaginating over them is correct (rule 7(a) owning the page
    # count, D7). This ordering is why authored PAGE intent cannot stop
    # here: `_repaginate` strips what this pass just wrote, so the same
    # intent is also an INPUT to the planner (D1, provider side).
    inert_breaks: tuple[int, ...] = ()
    inert_pages: tuple[int, ...] = ()
    if system_breaks or page_breaks:
        inert_breaks, inert_pages = _apply_breaks(root, system_breaks or {},
                                                  page_breaks or {})
    if page_break_measures:
        _repaginate(root, page_break_measures)

    return PreparedScore(
        canonical_xml=ET.tostring(root, encoding="unicode"),
        parts=parts,
        slash_regions=slash_regions,
        repeat_regions=repeat_regions,
        credits=credits,
        page_width=width,
        page_height=height,
        units_per_tenth=units_per_tenth,
        inert_system_breaks=inert_breaks,
        inert_page_breaks=inert_pages,
        inert_stem_directions=inert_stems,
    )
