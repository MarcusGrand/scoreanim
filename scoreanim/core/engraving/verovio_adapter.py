"""Verovio adapter: MusicXML → identity-tagged, paged Layout (plan D2/D3/D5).

Verovio types, ids, and SVG never leak past this module (CLAUDE.md rule 4).
ElementIds are minted here from musical identity (part/measure/staff/voice/
kind/index), so they are deterministic across loads and survive engraving
reflows. A fixed xmlIdSeed keeps Verovio's internal ids reproducible for
the timemap ↔ SVG ↔ MEI cross-referencing inside a load.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

import verovio

from scoreanim.core.animation.schedule import REVEALED_KINDS, STATIC_KINDS
from scoreanim.core.engraving.provider import EngravingProvider
from scoreanim.core.engraving.systems import plan_page_breaks, system_bands
from scoreanim.core.engraving.svg_geom import (ellipse_path, line_path,
                                               parse_transform, path_bbox,
                                               polygon_path, rect_path)
from scoreanim.core.engraving.types import (TRANSPOSE_TO_SOUNDING_PITCH,
                                            Affine, EngravingParams, Layout,
                                            LoadWarning, PageGeometry,
                                            PathPrimitive, Point, Rect,
                                            RenderedElement, RenderPrimitive,
                                            TextPrimitive, TextRun)
from scoreanim.core.score.identity import (Beats, ElementId, ElementIdentity,
                                           ElementKind, PartId)
from scoreanim.core.score.musicxml_prep import (PartCondenseSpec,
                                                PartGroupSpec, PartInfo,
                                                PartTextSpec, PreparedScore,
                                                prepare)

_MEI_NS = "{http://www.music-encoding.org/ns/mei}"
_SVG_NS = "{http://www.w3.org/2000/svg}"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

# SVG class (first token) → ElementKind for emitted elements.
_KIND_BY_CLASS: dict[str, ElementKind] = {
    "note": ElementKind.NOTEHEAD,
    "rest": ElementKind.REST,
    "mRest": ElementKind.MREST,
    "multiRest": ElementKind.MREST,
    "stem": ElementKind.STEM,
    "flag": ElementKind.FLAG,
    "dots": ElementKind.OTHER,
    "beam": ElementKind.BEAM,
    "slur": ElementKind.SLUR,
    "tie": ElementKind.TIE,
    "lv": ElementKind.TIE,
    "hairpin": ElementKind.HAIRPIN,
    "accid": ElementKind.ACCIDENTAL,
    "artic": ElementKind.ARTICULATION,
    # tremolo stroke groups (Phase 11): id-bearing, the stroke <use>
    # (SMuFL E22x) is a DIRECT child, so bTrem/fTrem must EMIT their own
    # element or the stroke folds into the static staff scaffold (the
    # BACKLOG-6 shape). Carries its child note's onset, animates untinted
    # (ruling a). fTrem never occurs in either fixture — defensive.
    "bTrem": ElementKind.TREMOLO,
    "fTrem": ElementKind.TREMOLO,
    # cross-measure/cross-staff beam (Phase 11): id-bearing with direct
    # polygon children; onset/extent come from its MEI @startid/@endid,
    # NOT the layer-beam table (beamSpan is a measure-level spanner)
    "beamSpan": ElementKind.BEAM,
    "dynam": ElementKind.DYNAMIC,
    "clef": ElementKind.CLEF,
    "keySig": ElementKind.KEY_SIG,
    "meterSig": ElementKind.METER_SIG,
    "barLine": ElementKind.BARLINE,
    "staff": ElementKind.STAFF_LINES,
    "harm": ElementKind.CHORD_SYMBOL,
    "verse": ElementKind.LYRIC,
    "syl": ElementKind.LYRIC,
    "tempo": ElementKind.TEXT,
    "dir": ElementKind.TEXT,
    "reh": ElementKind.TEXT,
    "label": ElementKind.TEXT,
    "labelAbbr": ElementKind.TEXT,
    "pgHead": ElementKind.TEXT,
    "pgFoot": ElementKind.TEXT,
    "mNum": ElementKind.TEXT,
    "tuplet": ElementKind.OTHER,
    "tupletNum": ElementKind.OTHER,
    "tupletBracket": ElementKind.OTHER,
    "arpeg": ElementKind.OTHER,
    "fermata": ElementKind.ARTICULATION,
    "trill": ElementKind.OTHER,
    "mordent": ElementKind.OTHER,
    "turn": ElementKind.OTHER,
    "octave": ElementKind.OTHER,
    "breath": ElementKind.OTHER,
    # the system-left vertical line joining a system's staves IS a
    # barline — scaffold, static by the denylist (ruling 2026-07-20).
    # It owns only that path; measures/staves nest as their own elements.
    "system": ElementKind.BARLINE,
    "grpSym": ElementKind.GROUP_SYMBOL,  # staff-group bracket/brace (Phase 8);
                                         # joined-barline connector paths land
                                         # inside the ordinary barLine groups
                                         # (spikes/NOTES.md Phase 8), so no
                                         # further class is needed
    # id-less between-system divider glyph; drawn only under condensed
    # layout, which condense:"encoded" disables — defensive (Phase 10)
    "systemDivider": ElementKind.SYSTEM_DIVIDER,
    # bracket/line spanner group: id-bearing, empty on the Phase 10
    # fixture; if a future score inks it, it renders as static OTHER
    # instead of tripping the unknown-class guard
    "bracketSpan": ElementKind.OTHER,
}

# Transparent grouping classes: never emitted, provide context only.
# keyAccid/fig fold their glyphs into the enclosing keySig / harm element;
# space and the milestone markers contain nothing drawable. ledgerLines
# is NOT here: its dashes are emitted per-path as LEDGER_LINES elements
# and attributed to noteheads afterwards (BACKLOG 6).
_CONTAINER_CLASSES = {
    "measure", "layer", "chord", "graceGrp", "notehead",
    "page-margin", "definition-scale", "section", "pb", "sb", "ending",
    "keyAccid", "fig", "mdiv", "score", "svg", "space",
    "pageMilestoneEnd", "systemMilestoneEnd", "pageElement",
    "mSpace",           # invisible measure space (Phase 10 fixture) —
                        # nothing drawable, the `space` precedent
}

# Short kind tag used inside minted ElementIds.
_ID_TAG = {k: k.name.lower() for k in ElementKind}

# SVG classes that are drawn spanners. A system-broken spanner renders as
# one id-bearing <g> in its start measure plus one id-less <g> per
# continuation system (Phase 5 spike, spikes/spanner_split.py).
_SPANNER_CLASSES = {"slur", "tie", "hairpin", "lv"}

# Page furniture: TEXT sub-classes that stay STATIC under the Phase 10R
# animate-everything ruling (part labels, page header/footer, measure
# numbers are navigation furniture, not musical objects). They mint
# onset=None, which is what the schedule's onset gate excludes.
_STATIC_TEXT_CLASSES = {"label", "labelAbbr", "pgHead", "pgFoot", "mNum"}

# SVG classes whose Verovio id is genuinely a timemap key (notes and
# rests). Note-owned fragments (stems, flags, accidentals, beams, …)
# derive their onset from their owner, NOT their own id — and MUST NOT
# consult the id tables, because Verovio reuses SVG group ids across
# element types under condensed layout (hide-empty-staves): an m1 stem
# and an m44 note can share an id, so a naive id lookup would give the
# stem the note's late onset (Phase 10R bug, spikes/NOTES.md).
_TIMEMAP_CLASSES = {"note", "rest", "mRest", "multiRest"}

# Verovio styles its SVG through one small stylesheet instead of element
# attributes; its effective rules are baked into the primitives so the
# redraw needs no CSS: every shape strokes in currentColor, and text
# weight/style follow the owning class.
_BOLD_TEXT_CLASSES = {"ending", "fing", "reh", "tempo"}
_ITALIC_TEXT_CLASSES = {"dir", "dynam", "mNum"}

_ACCID_TO_ALTER = {
    None: 0.0, "": 0.0, "n": 0.0, "s": 1.0, "f": -1.0,
    "ss": 2.0, "x": 2.0, "ff": -2.0,
}


# ---------------------------------------------------------------------------
# MEI-side tables (plan D2): musical attributes per Verovio id, one load.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _MeiNote:
    measure: int
    staff: int
    layer: int
    pname: str | None            # 'a'..'g'; None for unpitched
    alter: float
    octave: int | None
    loc: int | None              # staff position for unpitched notes
    grace: bool
    chord_id: str | None


@dataclass
class _MeiIndex:
    notes: dict[str, _MeiNote] = field(default_factory=dict)
    chord_members: dict[str, tuple[str, ...]] = field(default_factory=dict)
    beam_note_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # tremolo group id → its contained note ids, for onset propagation
    # (chord-member style; Phase 11 ruling a)
    tremolo_note_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # tuplet group id → its contained note ids: the tuplet bracket/number
    # decorate those notes, so they light with the tuplet's first note,
    # NOT the measure start (bug fix 2026-07-20)
    tuplet_note_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # beamSpan id → (startid, endid) note ids, its onset/extent source
    # (Phase 11 — not in the layer-beam table)
    beamspan_ends: dict[str, tuple[str | None, str | None]] = \
        field(default_factory=dict)
    spanners: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    spanner_tags: dict[str, str] = field(default_factory=dict)
    measure_by_id: dict[str, int] = field(default_factory=dict)
    # measure-attached elements (dynam, dir, tempo, harm...) → their @staff.
    # Spanners are recorded here too (Phase 5): hairpins carry @staff but
    # no startid, so this is their only staff source.
    staff_attr_by_id: dict[str, int] = field(default_factory=dict)
    # timestamp-addressed elements (hairpins AND dynamics — Phase 5
    # re-plan R.1): id → (measure_n, tstamp, tstamp2 or None). tstamp is
    # in meter units, 1-based; tstamp2 grammar is "<n>m+<beat>"
    # (n measures ahead) or a bare beat (same measure).
    tstamps_by_id: dict[str, tuple[int, str, str | None]] = \
        field(default_factory=dict)
    # measure-attached elements addressed by @startid (fermatas, trills,
    # ornaments; dynamics from non-Dorico exporters) — their animation
    # attach point (Phase 10R widened this beyond dynam)
    attach_startid: dict[str, str] = field(default_factory=dict)
    # active meter denominator per measure (document-order tracking of
    # meterSig), for tstamp → quarter-note conversion
    meter_unit_by_measure: dict[int, int] = field(default_factory=dict)


def _int_or(value: str | None, fallback: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


def _parse_mei(mei_xml: str) -> _MeiIndex:
    root = ET.fromstring(mei_xml)
    index = _MeiIndex()

    def ref(value: str | None) -> str | None:
        return value.lstrip("#") if value else None

    # Document-order meter tracking: meterSig elements (initial scoreDef +
    # mid-score changes) precede the measures they govern. Needed to
    # convert spanner tstamps (meter units) to quarters (Phase 5 spike).
    unit = 4
    meter_ordinal = 0
    for el in root.iter():
        tag = el.tag.removeprefix(_MEI_NS)
        if tag == "meterSig" and el.get("unit"):
            unit = _int_or(el.get("unit"), unit)
        elif tag == "measure":
            meter_ordinal += 1
            index.meter_unit_by_measure[
                _int_or(el.get("n"), meter_ordinal)] = unit

    measure_ordinal = 0
    for measure in root.iter(f"{_MEI_NS}measure"):
        measure_ordinal += 1
        m_n = _int_or(measure.get("n"), measure_ordinal)
        m_id = measure.get(_XML_ID)
        if m_id:
            index.measure_by_id[m_id] = m_n
        for staff in measure.findall(f"{_MEI_NS}staff"):
            s_n = _int_or(staff.get("n"), 0)
            for layer in staff.findall(f"{_MEI_NS}layer"):
                l_n = _int_or(layer.get("n"), 1)
                _walk_layer(layer, index, m_n, s_n, l_n)
        for sp in measure:
            sp_id = sp.get(_XML_ID)
            if not sp_id:
                continue
            tag = sp.tag.removeprefix(_MEI_NS)
            if tag in ("slur", "tie", "hairpin", "octave", "lv"):
                index.spanners[sp_id] = (ref(sp.get("startid")),
                                         ref(sp.get("endid")))
                index.spanner_tags[sp_id] = tag
                if sp.get("tstamp"):
                    index.tstamps_by_id[sp_id] = (
                        m_n, sp.get("tstamp", "1"), sp.get("tstamp2"))
            elif tag in ("dynam", "fermata", "trill", "mordent", "turn",
                         "dir", "tempo", "reh", "harm"):
                # measure-attached objects animate at their attach point
                # (dynamics: ruling 2026-07-12; the rest: Phase 10R
                # animate-everything ruling). Dorico addresses texts and
                # dynamics by @tstamp+@staff, ornaments/fermatas by
                # @startid; both are honored.
                startid = ref(sp.get("startid"))
                if startid:
                    index.attach_startid[sp_id] = startid
                if sp.get("tstamp"):
                    index.tstamps_by_id[sp_id] = (
                        m_n, sp.get("tstamp", "1"), sp.get("tstamp2"))
            elif tag == "beamSpan":
                index.beamspan_ends[sp_id] = (ref(sp.get("startid")),
                                              ref(sp.get("endid")))
            if sp.get("staff"):
                index.staff_attr_by_id[sp_id] = _int_or(
                    sp.get("staff", "").split()[0], 0)
    return index


def _walk_layer(layer: ET.Element, index: _MeiIndex,
                m_n: int, s_n: int, l_n: int) -> None:
    def note_alter(note: ET.Element) -> float:
        accid = note.find(f"{_MEI_NS}accid")
        value = None
        if accid is not None:
            value = accid.get("accid.ges") or accid.get("accid")
        value = value or note.get("accid.ges") or note.get("accid")
        return _ACCID_TO_ALTER.get(value, 0.0)

    def visit(node: ET.Element, chord_id: str | None, grace_ctx: bool) -> list[str]:
        """Returns note ids in document order beneath node."""
        collected: list[str] = []
        tag = node.tag.removeprefix(_MEI_NS)
        node_id = node.get(_XML_ID)
        if tag == "note" and node_id:
            oct_str = node.get("oct")
            index.notes[node_id] = _MeiNote(
                measure=m_n, staff=s_n, layer=l_n,
                pname=node.get("pname"),
                alter=note_alter(node),
                octave=int(oct_str) if oct_str is not None else None,
                loc=_int_or(node.get("loc"), 0) if node.get("loc") else None,
                grace=grace_ctx or node.get("grace") is not None,
                chord_id=chord_id,
            )
            collected.append(node_id)
            return collected
        child_chord = node_id if tag == "chord" else chord_id
        child_grace = grace_ctx or tag == "graceGrp" or node.get("grace") is not None
        for child in node:
            collected.extend(visit(child, child_chord, child_grace))
        if tag == "chord" and node_id:
            index.chord_members[node_id] = tuple(collected)
        if tag == "beam" and node_id:
            index.beam_note_ids[node_id] = tuple(collected)
        if tag in ("bTrem", "fTrem") and node_id:
            index.tremolo_note_ids[node_id] = tuple(collected)
        if tag == "tuplet" and node_id:
            index.tuplet_note_ids[node_id] = tuple(collected)
        return collected

    for child in layer:
        visit(child, None, False)


# ---------------------------------------------------------------------------
# Note records exposed for the ScoreModel join (plan D2). Plain data — no
# Verovio ids or types.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AdapterNoteRecord:
    element_id: ElementId
    part: PartId
    measure: int
    staff: int                   # part-local, 1-based
    voice: int
    onset: Beats
    grace: bool
    pitch_step: str | None       # 'A'..'G'; None for unpitched
    pitch_alter: float
    octave: int | None
    staff_loc: int | None        # vertical staff position for unpitched
    chord_group: str | None      # shared token for members of one chord
    order_in_voice: int          # document order within (measure, staff, voice)


@dataclass(frozen=True)
class EngravedScore:
    layout: Layout
    note_records: tuple[AdapterNoteRecord, ...]
    prepared: PreparedScore
    # Non-fatal load anomalies (Phase 10 ruling b): dropped spanners,
    # continuation-attribution gaps. Empty on clean loads.
    warnings: tuple[LoadWarning, ...] = ()


# ---------------------------------------------------------------------------
# SVG decomposition
# ---------------------------------------------------------------------------

@dataclass
class _ElementAccumulator:
    verovio_id: str
    svg_class: str
    kind: ElementKind
    measure: int | None
    staff: int | None
    layer: int | None
    owner_onset: Beats | None    # onset of enclosing note/chord (for stems etc.)
    system: int | None = None            # score-wide system index (1-based)
    ledger_dir: str | None = None        # "above" | "below" for ledger dashes
    # Continuation segment of a system-broken spanner (Phase 5 spike):
    # an id-less <g class="slur|tie|hairpin"> child of the continuation
    # system. Attributed to its source spanner post-decomposition.
    continuation: bool = False
    source_vid: str | None = None        # set by _attribute_spanner_segments
    seg_index: int = 0                   # 1-based continuation order
    paths: list[PathPrimitive] = field(default_factory=list)
    texts: list[TextPrimitive] = field(default_factory=list)
    use_origins: list[Point] = field(default_factory=list)
    bbox: Rect | None = None

    def add_bbox(self, rect: Rect) -> None:
        self.bbox = rect if self.bbox is None else self.bbox.union(rect)


class _PageDecomposer:
    def __init__(self, svg_text: str, page: int, adapter: "_LoadState") -> None:
        self.page = page
        self.st = adapter
        self.root = ET.fromstring(svg_text)
        self.glyphs: dict[str, tuple[str, Affine]] = {}   # def id → (d, inner tf)
        self.done: list[_ElementAccumulator] = []
        self.drawables_seen = 0
        self.drawables_claimed = 0

    def run(self) -> list[_ElementAccumulator]:
        inner = self.root.find(f"{_SVG_NS}svg")
        if inner is None:
            raise ValueError(f"page {self.page}: no definition-scale <svg>")
        for defs in self.root.findall(f"{_SVG_NS}defs"):
            for g in defs:
                gid = g.get("id")
                path = g.find(f"{_SVG_NS}path")
                if gid and path is not None:
                    self.glyphs[gid] = (path.get("d", ""),
                                        parse_transform(path.get("transform")))
        outer_vb = [float(v) for v in (self.root.get("viewBox") or "").split()]
        inner_vb = [float(v) for v in (inner.get("viewBox") or "").split()]
        if len(outer_vb) != 4 or len(inner_vb) != 4:
            raise ValueError(f"page {self.page}: missing viewBox")
        root_ctm = Affine(a=outer_vb[2] / inner_vb[2],
                          d=outer_vb[3] / inner_vb[3])
        self._walk(inner, root_ctm, owner=None,
                   measure=None, staff=None, layer=None, owner_onset=None,
                   system=None)
        if self.drawables_claimed != self.drawables_seen:
            raise ValueError(
                f"page {self.page}: {self.drawables_seen - self.drawables_claimed} "
                f"drawable(s) not claimed by any element — decomposition is lossy")
        return self.done

    # -- tree walk ----------------------------------------------------------

    def _walk(self, node: ET.Element, ctm: Affine,
              owner: _ElementAccumulator | None,
              measure: int | None, staff: int | None, layer: int | None,
              owner_onset: Beats | None, system: int | None) -> None:
        st = self.st
        for child in node:
            tag = child.tag.removeprefix(_SVG_NS)
            child_ctm = ctm.compose(parse_transform(child.get("transform")))
            if tag == "g":
                cls = (child.get("class") or "").split()[0] if child.get("class") else ""
                cid = child.get(_XML_ID) or child.get("id")
                new_measure, new_staff, new_layer = measure, staff, layer
                new_owner, new_owner_onset = owner, owner_onset
                new_system = system
                if cls == "system":
                    st.system_count += 1
                    new_system = st.system_count
                elif cls == "measure" and cid in st.mei.measure_by_id:
                    new_measure = st.mei.measure_by_id[cid]
                    if new_system is not None:
                        st.system_of_measure.setdefault(new_measure,
                                                        new_system)
                elif cls == "staff":
                    new_staff = _int_or(child.get("data-n"), 0) or \
                        st.staff_n_by_id.get(cid or "", 0) or staff or 0
                elif cls == "layer":
                    new_layer = st.layer_n_by_id.get(cid or "", layer or 1)
                if cls in ("note", "chord") and cid:
                    onset = st.onset_by_id.get(cid)
                    if onset is None and cls == "chord":
                        member = next(iter(st.mei.chord_members.get(cid, ())), None)
                        onset = st.onset_by_id.get(member) if member else None
                    if onset is not None:
                        new_owner_onset = onset
                if cls in ("bTrem", "fTrem") and cid:
                    # the tremolo element inherits its child note's onset
                    # (ruling a) — the stroke ink lights with the note it
                    # decorates; the nested note keeps its own timemap onset
                    onsets = [st.onset_by_id[n]
                              for n in st.mei.tremolo_note_ids.get(cid, ())
                              if n in st.onset_by_id]
                    if onsets:
                        new_owner_onset = min(onsets)
                if cls == "tuplet" and cid:
                    # the tuplet bracket/number decorate the notes under
                    # them, so they light with the tuplet's FIRST note, not
                    # the measure start (the measure-start fallback would
                    # fire them at the downbeat — bug fix 2026-07-20). The
                    # nested notes keep their own timemap onsets.
                    onsets = [st.onset_by_id[n]
                              for n in st.mei.tuplet_note_ids.get(cid, ())
                              if n in st.onset_by_id]
                    if onsets:
                        new_owner_onset = min(onsets)
                if cls == "ledgerLines":
                    self._add_ledger_dashes(child, child_ctm,
                                            new_measure, new_staff,
                                            new_system)
                    continue
                if cls == "systemDivider" and not cid:
                    # Between-system divider: id-less <g> hosted directly
                    # in the system (Phase 10 triage). Static ink with a
                    # system-scoped identity; drawn only under condensed
                    # layout, which condense:"encoded" disables.
                    acc = _ElementAccumulator(
                        verovio_id="", svg_class=cls,
                        kind=ElementKind.SYSTEM_DIVIDER,
                        measure=None, staff=None, layer=None,
                        owner_onset=None, system=new_system)
                    self._walk(child, child_ctm, acc, new_measure, new_staff,
                               new_layer, new_owner_onset, new_system)
                    if acc.paths or acc.texts:
                        self.done.append(acc)
                    continue
                if cls in _SPANNER_CLASSES and not cid:
                    # Continuation segment of a system-broken spanner:
                    # id-less, hosted directly in the continuation system
                    # (Phase 5 spike). Emitted as its own element;
                    # attributed to its source spanner in a post-pass.
                    acc = _ElementAccumulator(
                        verovio_id="", svg_class=cls,
                        kind=_KIND_BY_CLASS[cls],
                        measure=None, staff=None, layer=None,
                        owner_onset=None, system=new_system,
                        continuation=True)
                    self._walk(child, child_ctm, acc, new_measure, new_staff,
                               new_layer, new_owner_onset, new_system)
                    if acc.paths or acc.texts:
                        self.done.append(acc)
                    continue
                if cid and cls in _KIND_BY_CLASS:
                    acc = _ElementAccumulator(
                        verovio_id=cid, svg_class=cls,
                        kind=_KIND_BY_CLASS[cls],
                        measure=new_measure, staff=new_staff, layer=new_layer,
                        owner_onset=new_owner_onset, system=new_system)
                    self._walk(child, child_ctm, acc, new_measure, new_staff,
                               new_layer, new_owner_onset, new_system)
                    if acc.paths or acc.texts:
                        self.done.append(acc)
                    continue
                if cls and cls not in _CONTAINER_CLASSES and cls not in _KIND_BY_CLASS \
                        and self._has_drawables(child):
                    if st.strict:
                        raise ValueError(f"page {self.page}: unknown SVG "
                                         f"class {cls!r} with drawable content")
                    # Graceful degradation (Phase 11.4, app path): an
                    # unknown drawable class no longer fails the load — it
                    # mints an OTHER element that claims its drawables
                    # (nothing is lost or orphaned) and warns loudly. It
                    # animates like any OTHER ink when it resolves an onset
                    # (owner note, else measure start — animate-everything
                    # ruling 2026-07-20). Strict loads (pytest / doctor
                    # --strict) still raise, so coverage gaps stay visible
                    # in development.
                    print(f"scoreanim: unknown SVG class {cls!r} on page "
                          f"{self.page} — rendered as a degraded element",
                          file=sys.stderr)
                    st.warnings.append(LoadWarning(
                        "unknown-class",
                        f"unknown SVG class {cls!r} with drawable content "
                        f"(page {self.page}) — rendered as a degraded element"))
                    acc = _ElementAccumulator(
                        verovio_id=cid or "", svg_class=cls,
                        kind=ElementKind.OTHER,
                        measure=new_measure, staff=new_staff, layer=new_layer,
                        owner_onset=new_owner_onset, system=new_system)
                    self._walk(child, child_ctm, acc, new_measure, new_staff,
                               new_layer, new_owner_onset, new_system)
                    if acc.paths or acc.texts:
                        self.done.append(acc)
                    continue
                self._walk(child, child_ctm, new_owner, new_measure, new_staff,
                           new_layer, new_owner_onset, new_system)
            elif tag in ("use", "path", "rect", "line", "polygon", "polyline",
                         "ellipse", "circle", "text"):
                self.drawables_seen += 1
                if owner is None:
                    raise ValueError(
                        f"page {self.page}: orphan <{tag}> outside any "
                        f"emitted element (parent class "
                        f"{node.get('class')!r})")
                self._add_drawable(owner, tag, child, child_ctm)
                self.drawables_claimed += 1
            # desc, style, title, defs handled elsewhere / ignored

    def _add_ledger_dashes(self, group: ET.Element, ctm: Affine,
                           measure: int | None, staff: int | None,
                           system: int | None) -> None:
        """Each ledger dash becomes its own LEDGER_LINES element so it can
        dim with the note that owns it (BACKLOG 6). The group carries no
        id; onset/voice are attributed geometrically afterwards
        (_attribute_ledger_dashes)."""
        tokens = (group.get("class") or "").split()
        direction = ("above" if "above" in tokens
                     else "below" if "below" in tokens else None)
        for dash in group:
            tag = dash.tag.removeprefix(_SVG_NS)
            if tag != "path":
                raise ValueError(f"page {self.page}: unexpected <{tag}> "
                                 f"inside ledgerLines")
            self.drawables_seen += 1
            acc = _ElementAccumulator(
                verovio_id="", svg_class="ledgerLines",
                kind=ElementKind.LEDGER_LINES,
                measure=measure, staff=staff, layer=None,
                owner_onset=None, system=system, ledger_dir=direction)
            self._add_drawable(
                acc, "path", dash,
                ctm.compose(parse_transform(dash.get("transform"))))
            self.drawables_claimed += 1
            self.done.append(acc)

    def _has_drawables(self, node: ET.Element) -> bool:
        drawable = {"use", "path", "rect", "line", "polygon", "polyline",
                    "ellipse", "circle", "text"}
        return any(e.tag.removeprefix(_SVG_NS) in drawable for e in node.iter()
                   if e is not node)

    # -- drawables ----------------------------------------------------------

    def _add_drawable(self, acc: _ElementAccumulator, tag: str,
                      el: ET.Element, ctm: Affine) -> None:
        def fnum(name: str, default: float = 0.0) -> float:
            v = el.get(name)
            return float(v) if v is not None else default

        if tag == "use":
            href = (el.get(_XLINK_HREF) or el.get("href") or "").lstrip("#")
            if href not in self.glyphs:
                raise ValueError(f"page {self.page}: <use> references unknown "
                                 f"def {href!r}")
            d, inner_tf = self.glyphs[href]
            full = ctm.compose(inner_tf)
            acc.paths.append(PathPrimitive(d=d, transform=full,
                                           fill=el.get("fill"),
                                           stroke=el.get("stroke")
                                           or "currentColor"))
            acc.add_bbox(full.apply_rect(self.st.glyph_bbox(href, d)))
            acc.use_origins.append(Point(*ctm.apply(0.0, 0.0)))
            return
        if tag == "text":
            self._add_text(acc, el, ctm)
            return

        if tag == "path":
            d = el.get("d", "")
        elif tag == "rect":
            d = rect_path(fnum("x"), fnum("y"), fnum("width"), fnum("height"))
        elif tag == "line":
            d = line_path(fnum("x1"), fnum("y1"), fnum("x2"), fnum("y2"))
        elif tag in ("polygon", "polyline"):
            d = polygon_path(el.get("points", ""), close=tag == "polygon")
        elif tag in ("ellipse", "circle"):
            r = fnum("r")
            d = ellipse_path(fnum("cx"), fnum("cy"),
                             fnum("rx", r), fnum("ry", r))
        else:  # pragma: no cover — guarded by caller
            raise AssertionError(tag)
        sw = el.get("stroke-width")
        fill = el.get("fill")
        if el.get("fill-opacity") == "0":       # e.g. rehearsal-mark boxes
            fill = "none"
        acc.paths.append(PathPrimitive(
            d=d, transform=ctm, fill=fill,
            stroke=el.get("stroke") or "currentColor",
            stroke_width=float(sw) if sw else None))
        acc.add_bbox(ctm.apply_rect(path_bbox(d)))

    def _add_text(self, acc: _ElementAccumulator, el: ET.Element,
                  ctm: Affine) -> None:
        """One <text> → one TextPrimitive of styled runs. Verovio puts the
        anchor point and text-anchor either on <text> itself (labels,
        tempo) or on a positioned rend tspan inside it (pgHead lines);
        styling (size/family/style/weight/fill) sits on nested tspans and
        inherits downward."""
        # position + anchor: <text> first, else the single positioned tspan
        positioned = [t for t in el.iter(f"{_SVG_NS}tspan") if t.get("x")]
        if el.get("x") is not None or not positioned:
            pos_el = el
        elif len(positioned) == 1:
            pos_el = positioned[0]
        else:
            raise ValueError(f"page {self.page}: <text> with "
                             f"{len(positioned)} positioned tspans — "
                             f"needs splitting support")
        x = float(pos_el.get("x", "0"))
        y = float(pos_el.get("y", "0"))
        anchor = pos_el.get("text-anchor") or el.get("text-anchor") or "start"

        cls_weight = "bold" if acc.svg_class in _BOLD_TEXT_CLASSES else None
        cls_style = "italic" if acc.svg_class in _ITALIC_TEXT_CLASSES else None
        runs = self._text_runs(el, _RunAttrs(font_size=0.0, font_family=None,
                                             font_style=cls_style,
                                             font_weight=cls_weight,
                                             fill=None))
        runs = [r for r in runs if r.content.strip() and r.font_size > 0]
        if not runs:
            return
        acc.texts.append(TextPrimitive(runs=tuple(runs), x=x, y=y,
                                       anchor=anchor, transform=ctm))
        # crude metric estimate: 0.5 em average advance, 0.8/0.2 em
        # ascent/descent — a placeholder until real font metrics (Phase 2)
        width = sum(0.5 * r.font_size * len(r.content) for r in runs)
        height = max(r.font_size for r in runs)
        x0 = {"start": x, "middle": x - width / 2, "end": x - width}[anchor]
        local = Rect(x0, y - 0.8 * height, width, height)
        acc.add_bbox(ctm.apply_rect(local))

    def _text_runs(self, node: ET.Element, inherited: "_RunAttrs"
                   ) -> list[TextRun]:
        """Depth-first over tspans, tracking inherited styling; leaf text
        segments become runs. Inter-tspan whitespace (XML pretty-printing
        tails) is not content and is skipped."""
        attrs = inherited.updated(node)
        runs: list[TextRun] = []
        if node.text and node.text.strip():
            runs.append(TextRun(content=node.text,
                                font_size=attrs.font_size,
                                font_family=attrs.font_family,
                                font_style=attrs.font_style,
                                font_weight=attrs.font_weight,
                                fill=attrs.fill))
        for child in node:
            if child.tag == f"{_SVG_NS}tspan":
                runs.extend(self._text_runs(child, attrs))
        return runs


@dataclass(frozen=True)
class _RunAttrs:
    """Styling inherited down the tspan tree."""
    font_size: float
    font_family: str | None
    font_style: str | None
    font_weight: str | None
    fill: str | None

    def updated(self, node: ET.Element) -> "_RunAttrs":
        size = self.font_size
        v = node.get("font-size")
        if v is not None and float(v.removesuffix("px")) > 0:
            size = float(v.removesuffix("px"))
        return _RunAttrs(
            font_size=size,
            font_family=node.get("font-family") or self.font_family,
            font_style=node.get("font-style") or self.font_style,
            font_weight=node.get("font-weight") or self.font_weight,
            fill=node.get("fill") or self.fill,
        )


# ---------------------------------------------------------------------------
# Load orchestration
# ---------------------------------------------------------------------------

@dataclass
class _LoadState:
    prep: PreparedScore
    mei: _MeiIndex
    onset_by_id: dict[str, Beats]           # notes and rests → qstamp
    measure_start: dict[int, Beats]          # measure number → qstamp
    measure_duration: dict[int, Beats]       # from timemap start deltas
    staff_n_by_id: dict[str, int]
    layer_n_by_id: dict[str, int]
    # system → {global staff n → staff-lines y center}, built after
    # decomposition; grpSym identity reads which staves a symbol spans
    # (geometric — Phase 10; slot bookkeeping broke on native braces,
    # which Verovio SUPPRESSES when an injected group overlaps them)
    staff_centers_by_system: dict[int, dict[int, float]] = \
        field(default_factory=dict)
    system_count: int = 0                    # score-wide, across pages
    system_of_measure: dict[int, int] = field(default_factory=dict)
    warnings: list[LoadWarning] = field(default_factory=list)
    # Strict loads raise on an unknown drawable SVG class; app loads
    # degrade it to a static OTHER element with a warning (Phase 11.4).
    strict: bool = True
    # ties suppressed as engraving artifacts (Phase 10R): neither the
    # source element nor its continuation segments are emitted
    suppressed_spanners: set[str] = field(default_factory=set)
    _glyph_bbox_cache: dict[str, Rect] = field(default_factory=dict)

    def glyph_bbox(self, def_id: str, d: str) -> Rect:
        # def ids are "<codepoint>-<pageid>"; path data is identical across
        # pages, so cache by codepoint
        key = def_id.split("-")[0]
        if key not in self._glyph_bbox_cache:
            self._glyph_bbox_cache[key] = path_bbox(d)
        return self._glyph_bbox_cache[key]


class VerovioEngravingProvider(EngravingProvider):
    """MusicXML → Layout via Verovio, honoring encoded breaks and rendering
    at concert pitch (octave-only transpositions neutralized in prep)."""

    def load(self, score_path: Path, params: EngravingParams,
             groups: tuple[PartGroupSpec, ...] = (),
             texts: tuple[PartTextSpec, ...] = (),
             hide_empty_staves: bool = False,
             condense: tuple[PartCondenseSpec, ...] = (),
             strict: bool = True) -> Layout:
        return self.load_detailed(score_path, params, groups, texts,
                                  hide_empty_staves, condense, strict).layout

    def load_detailed(self, score_path: Path, params: EngravingParams,
                      groups: tuple[PartGroupSpec, ...] = (),
                      texts: tuple[PartTextSpec, ...] = (),
                      hide_empty_staves: bool = False,
                      condense: tuple[PartCondenseSpec, ...] = (),
                      strict: bool = True) -> EngravedScore:
        # strict (Phase 11.4): when False (the app path) an unknown
        # drawable SVG class degrades to a static OTHER element plus a
        # "unknown-class" warning instead of raising; True (the default,
        # and pytest / the doctor's --strict) keeps coverage gaps loud.
        prep = prepare(score_path, groups, texts, condense)
        extra: list[LoadWarning] = []
        effective_hide = hide_empty_staves
        engraved, first_measure = self._engrave_prepared(
            score_path, prep, params, effective_hide, strict)
        if engraved is None:
            # Hiding made a slash- or bar-repeat-region staff vanish
            # (Verovio judges both empty — MEI <space>). Both are
            # first-class (rule 10 family), so they win over the option:
            # engrave flat, flagged (spikes/NOTES.md Phase 10R / 12).
            effective_hide = False
            extra.append(LoadWarning(
                "hide-unavailable",
                "a slash- or bar-repeat-region staff would be hidden; "
                "empty-staff hiding skipped for this score"))
            engraved, first_measure = self._engrave_prepared(
                score_path, prep, params, effective_hide, strict)
            assert engraved is not None

        # Never-clip guard (Phase 10R, rule-7 amendment): when the
        # encoded page breaks cannot hold their systems (e.g. Dorico
        # breaks computed assuming hidden staves), keep the encoded
        # SYSTEM breaks and repaginate ourselves at the prep seam.
        # Page-scoped ids (score:p{n}:…) shift — accepted; musical ids
        # are pagination-independent.
        page_h = engraved.layout.pages[0].height
        bands = system_bands(engraved.layout)
        if any(b.rect.y + b.rect.h > page_h for b in bands):
            breaks = plan_page_breaks(bands, page_h, first_measure)
            if breaks:
                prep = prepare(score_path, groups, texts, condense,
                               page_break_measures=breaks)
                engraved, _ = self._engrave_prepared(
                    score_path, prep, params, effective_hide, strict)
                assert engraved is not None    # same flag that succeeded
                extra.append(LoadWarning(
                    "repaginated",
                    f"systems overflowed the encoded page height; "
                    f"{len(breaks)} page break(s) re-derived "
                    f"(before measures "
                    f"{', '.join(str(m) for m in breaks)})"))
                for b in system_bands(engraved.layout):
                    if b.rect.y + b.rect.h > page_h:
                        extra.append(LoadWarning(
                            "system-overflow",
                            f"system {b.system} still overflows page "
                            f"{b.page} after repagination"))
        if extra:
            engraved = replace(engraved,
                               warnings=engraved.warnings + tuple(extra))
        return engraved

    @staticmethod
    def _make_toolkit(prep: PreparedScore,
                      params: EngravingParams) -> "verovio.toolkit":
        tk = verovio.toolkit()
        tk.setOptions({
            "breaks": "encoded",
            "font": "Bravura",
            "pageWidth": round(prep.page_width),
            "pageHeight": round(prep.page_height),
            "scaleToPageSize": True,
            "header": "none" if params.suppress_header else "encoded",
            "footer": "encoded",
            "svgHtml5": False,
            "svgViewBox": True,
            "transposeToSoundingPitch": TRANSPOSE_TO_SOUNDING_PITCH,
            "xmlIdSeed": params.xml_id_seed,
            # Verovio's default condense:"auto" silently switches to
            # condensed layout once a score has 2+ staff groups — hiding
            # empty staves per system and drawing systemDividers. That is
            # engraver-derived reflow, which rule 7 forbids; "encoded"
            # honors only what the file encodes. Verified byte-identical
            # for 0- and 1-group renders (Phase 10 triage spike). A fixed
            # rule like transposeToSoundingPitch, not a params field.
            # Hide-empty-staves (Phase 10R) opts IN per score by setting
            # scoreDef@optimize on the MEI round-trip — condense stays
            # "encoded" either way.
            "condense": "encoded",
            # Condensed layouts draw between-system dividers by default;
            # Dorico's default look has none (Phase 10R spike). The
            # SYSTEM_DIVIDER decomposer support stays as defense.
            "systemDivider": "none",
        })
        return tk

    def _engrave_prepared(self, score_path: Path, prep: PreparedScore,
                          params: EngravingParams,
                          hide_empty_staves: bool,
                          strict: bool = True
                          ) -> tuple[EngravedScore | None, dict[int, int]]:
        """One full engrave+decompose; also returns the first measure
        of every system (for the repagination planner). The score is
        None only when hide_empty_staves hid a slash-region staff (the
        caller retries flat)."""
        tk = self._make_toolkit(prep, params)
        if not tk.loadData(prep.canonical_xml):
            raise ValueError(f"Verovio failed to load {score_path}")
        if hide_empty_staves:
            # Two-pass load: Verovio honors hidden empty staves only via
            # MEI scoreDef@optimize (staff-details print-object and
            # staffDef@visible are ignored). The round-trip is id- and
            # timemap-transparent (Phase 10R spike, section A).
            mei_text = _set_scoredef_optimize(tk.getMEI())
            tk = self._make_toolkit(prep, params)
            if not tk.loadData(mei_text):
                raise ValueError(
                    f"Verovio failed to reload optimized MEI for "
                    f"{score_path}")

        mei = _parse_mei(tk.getMEI())
        timemap = tk.renderToTimemap({"includeMeasures": True,
                                      "includeRests": True})
        onset_by_id: dict[str, Beats] = {}
        measure_start: dict[int, Beats] = {}
        for entry in timemap:
            q = float(entry["qstamp"])
            for vid in entry.get("on", []):
                onset_by_id[vid] = q
            for vid in entry.get("restsOn", []):
                onset_by_id[vid] = q
            m_id = entry.get("measureOn")
            if m_id and m_id in mei.measure_by_id:
                measure_start.setdefault(mei.measure_by_id[m_id], q)

        score_end = max(float(e["qstamp"]) for e in timemap)
        starts = sorted(measure_start.items(), key=lambda kv: kv[1])
        measure_duration = {
            n: (starts[i + 1][1] if i + 1 < len(starts) else score_end) - q
            for i, (n, q) in enumerate(starts)
        }

        state = _LoadState(
            prep=prep, mei=mei, onset_by_id=onset_by_id,
            measure_start=measure_start, measure_duration=measure_duration,
            staff_n_by_id={vid: n.staff for vid, n in mei.notes.items()},
            layer_n_by_id={}, strict=strict,
        )
        # staff/layer container ids appear in both MEI and SVG; index them
        state.staff_n_by_id.update(_container_ns(tk.getMEI(), "staff"))
        state.layer_n_by_id.update(_container_ns(tk.getMEI(), "layer"))

        page_count = tk.getPageCount()
        pages = tuple(PageGeometry(number=p, width=prep.page_width,
                                   height=prep.page_height)
                      for p in range(1, page_count + 1))

        accumulators: list[tuple[int, _ElementAccumulator]] = []
        for page in range(1, page_count + 1):
            for acc in _PageDecomposer(tk.renderToSVG(page), page, state).run():
                accumulators.append((page, acc))

        # staff y-centers per system, for geometric grpSym identity
        for _, acc in accumulators:
            if (acc.svg_class == "staff" and acc.bbox is not None
                    and acc.staff and acc.system is not None):
                state.staff_centers_by_system.setdefault(
                    acc.system, {}).setdefault(
                    acc.staff, acc.bbox.y + acc.bbox.h / 2)

        _attribute_ledger_dashes(accumulators, state)
        _attribute_spanner_segments(accumulators, state)
        _flag_implausible_ties(state)
        elements, note_records, staff_geo = _build_elements(accumulators, state)
        first_measure: dict[int, int] = {}
        for measure_n, system_n in state.system_of_measure.items():
            if measure_n < first_measure.get(system_n, 1 << 30):
                first_measure[system_n] = measure_n
        if hide_empty_staves and any(
                (region.part, m, 1) not in staff_geo
                for region in (*prep.slash_regions, *prep.repeat_regions)
                for m in range(region.start_measure, region.stop_measure)):
            return None, first_measure   # caller retries flat (rule 10)
        elements.extend(_synthesize_slashes(state, staff_geo))
        elements.extend(_synthesize_repeats(state, staff_geo))
        layout = Layout(pages=pages, elements=tuple(elements))
        return EngravedScore(layout=layout,
                             note_records=tuple(note_records),
                             prepared=prep,
                             warnings=tuple(state.warnings)), first_measure


def _set_scoredef_optimize(mei_xml: str) -> str:
    """Mark the score's first scoreDef optimize='true' — the encoding
    Verovio's condense honors for hiding empty staves per system."""
    ET.register_namespace("", _MEI_NS.strip("{}"))
    root = ET.fromstring(mei_xml)
    score_def = next(root.iter(f"{_MEI_NS}scoreDef"), None)
    if score_def is None:
        raise ValueError("MEI has no scoreDef to optimize")
    score_def.set("optimize", "true")
    return ET.tostring(root, encoding="unicode")


def _container_ns(mei_xml: str, tag: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for el in ET.fromstring(mei_xml).iter(f"{_MEI_NS}{tag}"):
        el_id = el.get(_XML_ID)
        if el_id and el.get("n"):
            result[el_id] = _int_or(el.get("n"), 0)
    return result


# ---------------------------------------------------------------------------
# Ledger-dash attribution (BACKLOG 6): a dash carries no id and no onset;
# it dims with the ink it serves. Owner = the notehead in the same
# (page, measure, staff) whose bbox overlaps the dash horizontally, on the
# correct side of the staff; a dash serving several heads (chords,
# multi-ledger stacks) takes the earliest onset so it never lights late.
# Verovio also draws ledger dashes through RESTS displaced off the staff
# (two-voice measures — Phase 10 triage, spikes/video_test_triage.py);
# a dash no notehead claims falls through to a rest tier with the same
# geometry rule. Tie resolution then happens for free: the dash inherits
# the owner's (onset, voice), which is exactly the schedule's
# attachment-group key — REST and LEDGER_LINES both animate.
# ---------------------------------------------------------------------------

def _attribute_ledger_dashes(
        accumulators: list[tuple[int, _ElementAccumulator]],
        st: _LoadState) -> None:
    notes_by_scope: dict[tuple, list[tuple[Rect, Beats, int]]] = \
        defaultdict(list)
    rests_by_scope: dict[tuple, list[tuple[Rect, Beats, int]]] = \
        defaultdict(list)
    for page, acc in accumulators:
        if acc.bbox is None:
            continue
        if acc.svg_class == "note":
            onset = st.onset_by_id.get(acc.verovio_id)
            mei_note = st.mei.notes.get(acc.verovio_id)
            if onset is None or mei_note is None:
                continue                 # _build_elements raises for these
            notes_by_scope[(page, acc.measure, acc.staff)].append(
                (acc.bbox, onset, mei_note.layer))
        elif acc.svg_class in ("rest", "mRest"):
            # whole-bar rests join the rest tier (Phase 11): a two-voice
            # measure displaces an mRest off the staff onto a ledger dash
            # exactly like an ordinary rest (complex1 p3 m13 staff 8)
            onset = st.onset_by_id.get(acc.verovio_id)
            if onset is None:
                continue                 # not in the timemap: no trigger
            rests_by_scope[(page, acc.measure, acc.staff)].append(
                (acc.bbox, onset, acc.layer if acc.layer is not None else 0))

    def matching(pool: list[tuple[Rect, Beats, int]],
                 dash: _ElementAccumulator) -> list[tuple[Beats, int]]:
        dash_cy = dash.bbox.y + dash.bbox.h / 2      # type: ignore[union-attr]
        out: list[tuple[Beats, int]] = []
        for bbox, onset, layer in pool:
            if (bbox.x + bbox.w <= dash.bbox.x
                    or dash.bbox.x + dash.bbox.w <= bbox.x):
                continue                 # no horizontal overlap
            owner_cy = bbox.y + bbox.h / 2
            # a dash above the staff is owned by ink at or above it
            # (y-down coordinates); intermediate dashes under a high note
            # pass this too. Mirror rule below the staff.
            if dash.ledger_dir == "above" and owner_cy > dash_cy + bbox.h / 2:
                continue
            if dash.ledger_dir == "below" and owner_cy < dash_cy - bbox.h / 2:
                continue
            out.append((onset, layer))
        return out

    for page, acc in accumulators:
        if acc.kind is not ElementKind.LEDGER_LINES or acc.bbox is None:
            continue
        scope = (page, acc.measure, acc.staff)
        candidates = (matching(notes_by_scope.get(scope, []), acc)
                      or matching(rests_by_scope.get(scope, []), acc))
        if not candidates:
            raise ValueError(
                f"page {page} m{acc.measure} staff {acc.staff}: ledger dash "
                f"at x={acc.bbox.x:.0f} matches no notehead or rest — "
                f"attribution failed")
        acc.owner_onset, acc.layer = min(candidates)


# ---------------------------------------------------------------------------
# Spanner continuation segments (Phase 5, spikes/spanner_split.py): a
# system-broken spanner renders as its id-bearing <g> (start system) plus
# id-less continuation <g>s. Each id-less segment is matched to the
# source spanner it continues — same SVG class, crossing-system
# predicate per class: slurs/hairpins draw a segment in EVERY crossed
# system (start < n <= end); ties draw continuation ink ONLY in their
# END system (Phase 10 triage — the Phase 5 fixture had only 2-system
# spanners, where the two rules coincide). Stacked same-kind candidates
# (several broken ties at once) are disambiguated by vertical order —
# segments and candidate end anchors are paired in y order, which is
# stable because a tie continuation hugs the pitch height of its end
# note. A count mismatch is tolerated: pairs are matched up to the
# shorter list and the mismatch surfaces as a LoadWarning (ruling b),
# never a silent absorption. Spanners the engraver dropped entirely
# (id-bearing <g> with no ink — e.g. Verovio's "ties left open") are
# detected structurally against the MEI and flagged the same way.
# ---------------------------------------------------------------------------

def _attribute_spanner_segments(
        accumulators: list[tuple[int, _ElementAccumulator]],
        st: _LoadState) -> None:
    note_accs: dict[str, _ElementAccumulator] = {
        acc.verovio_id: acc for _, acc in accumulators
        if acc.svg_class == "note"}

    # (svg_class, start_sys, end_sys, sort_key, vid)
    sources: list[tuple[str, int, int, tuple, str]] = []
    for _, acc in accumulators:
        if acc.continuation or acc.svg_class not in _SPANNER_CLASSES:
            continue
        vid = acc.verovio_id
        start_id, end_id = st.mei.spanners.get(vid, (None, None))
        end_sys: int | None = None
        end_y: float | None = None
        staff_n = 0
        end_note = note_accs.get(end_id or "")
        if end_note is not None:
            end_sys = end_note.system
            end_y = end_note.bbox.center.y if end_note.bbox else None
            staff_n = end_note.staff or 0
        elif vid in st.mei.tstamps_by_id:
            m, _, tstamp2 = st.mei.tstamps_by_id[vid]
            end_sys = st.system_of_measure.get(_tstamp2_end_measure(m, tstamp2))
            staff_n = st.mei.staff_attr_by_id.get(vid, 0)
        if acc.system is None or end_sys is None or end_sys <= acc.system:
            continue
        sources.append((acc.svg_class, acc.system, end_sys,
                        (staff_n, end_y if end_y is not None else 0.0), vid))

    segments: dict[tuple[str, int], list[_ElementAccumulator]] = \
        defaultdict(list)
    for _, acc in accumulators:
        if acc.continuation:
            if acc.system is None or acc.bbox is None:
                raise ValueError(
                    f"continuation {acc.svg_class} segment without "
                    f"system/bbox — cannot attribute")
            segments[(acc.svg_class, acc.system)].append(acc)

    for (cls, sys_n), segs in segments.items():
        if cls in ("tie", "lv"):
            crossing = (s for s in sources
                        if s[0] == cls and s[1] < sys_n and s[2] == sys_n)
        else:
            crossing = (s for s in sources
                        if s[0] == cls and s[1] < sys_n <= s[2])
        candidates = sorted(crossing, key=lambda s: s[3])
        if len(candidates) != len(segs):
            st.warnings.append(LoadWarning(
                "segment-count-mismatch",
                f"system {sys_n}: {len(segs)} {cls} continuation "
                f"segment(s), {len(candidates)} crossing source "
                f"spanner(s) — pairing up to the shorter list"))
        segs.sort(key=lambda a: a.bbox.center.y)       # type: ignore[union-attr]
        for seg, (_, _, _, _, vid) in zip(segs, candidates):
            seg.source_vid = vid

    # Segment index per source, in system order (a spanner across 3+
    # systems has several continuation segments: seg1, seg2, ...).
    # Unmatched segments (source_vid None) are skipped by
    # _build_elements with an unattributed-continuation warning.
    by_source: dict[str, list[_ElementAccumulator]] = defaultdict(list)
    for _, acc in accumulators:
        if acc.continuation and acc.source_vid:
            by_source[acc.source_vid].append(acc)
    for segs in by_source.values():
        segs.sort(key=lambda a: a.system or 0)
        for k, seg in enumerate(segs, start=1):
            seg.seg_index = k

    # Spanners the engraver dropped: the MEI records them but their
    # id-bearing <g> carries no ink, so no accumulator exists (Verovio's
    # "N ties left open" / "tie ignored" warnings, and testscore's 5
    # open ties). Flag-and-continue (ruling b); timing is unaffected —
    # tie chains come from the music21 ScoreModel, not drawn ties.
    drawn = {acc.verovio_id for _, acc in accumulators if acc.verovio_id}
    for vid, tag in sorted(st.mei.spanner_tags.items()):
        if vid in drawn:
            continue
        start_id, _ = st.mei.spanners[vid]
        start = st.mei.notes.get(start_id or "")
        if start is not None:
            info = st.prep.part_for_staff(start.staff)
            where = (f"from {info.part_id} m{start.measure} "
                     f"s{start.staff - info.first_staff + 1}")
        else:
            where = "with unresolved start"
        st.warnings.append(LoadWarning(
            "dropped-spanner",
            f"{tag} {where} was not drawn by the engraver"))


def _flag_implausible_ties(st: _LoadState) -> None:
    """Verovio force-matches some ties it cannot close to DISTANT
    same-pitch notes (video_test: e.g. a "tie" from m5 to m44, 148.5
    quarters — the stacked curves drew as ovals around the destination
    bar). A real tie connects adjacent notes: anything spanning more
    than two of its start measure's durations is an engraving artifact.
    Runs AFTER segment matching (the bogus sources must stay in the
    candidate pool so the y-order pairing of the remaining segments is
    right) and before element construction, which skips the suppressed
    vids and their continuation segments. Flag-and-continue (ruling b):
    one warning per suppressed tie, musical coordinates only."""
    for vid, tag in sorted(st.mei.spanner_tags.items()):
        if tag != "tie":         # lv has no end; slurs/hairpins can be long
            continue
        start_id, end_id = st.mei.spanners[vid]
        start = st.onset_by_id.get(start_id or "")
        end = st.onset_by_id.get(end_id or "")
        note = st.mei.notes.get(start_id or "")
        if start is None or end is None or note is None:
            continue             # ink-less opens hit the dropped path
        limit = 2.0 * st.measure_duration.get(note.measure, 4.0)
        if end - start > limit:
            st.suppressed_spanners.add(vid)
            info = st.prep.part_for_staff(note.staff)
            st.warnings.append(LoadWarning(
                "implausible-tie",
                f"tie from {info.part_id} m{note.measure} "
                f"s{note.staff - info.first_staff + 1} spans "
                f"{end - start:g} quarters (> 2 bars) — suppressed as "
                f"an engraving artifact"))


def _tstamp2_end_measure(start_measure: int, tstamp2: str | None) -> int:
    if tstamp2 and "m+" in tstamp2:
        return start_measure + int(tstamp2.split("m+", 1)[0])
    return start_measure


def _tstamp_extent(entry: tuple[int, str, str | None], st: _LoadState
                   ) -> tuple[Beats, tuple[Beats, Beats]]:
    """Onset/extent in quarters for a timestamp-addressed spanner
    (hairpins: @tstamp/@tstamp2 in meter units, 1-based; tstamp2 grammar
    "<n>m+<beat>" or a bare beat)."""
    m, tstamp, tstamp2 = entry

    def q_at(measure: int, beat: str) -> Beats:
        unit = st.mei.meter_unit_by_measure.get(measure, 4)
        return st.measure_start[measure] + (float(beat) - 1.0) * (4.0 / unit)

    start = q_at(m, tstamp)
    if not tstamp2:
        return start, (start, start)
    if "m+" in tstamp2:
        ahead, beat = tstamp2.split("m+", 1)
        end = q_at(m + int(ahead), beat)
    else:
        end = q_at(m, tstamp2)
    return start, (start, end)


# ---------------------------------------------------------------------------
# Identity minting (plan D5) and element construction
# ---------------------------------------------------------------------------

def _build_elements(
    accumulators: list[tuple[int, _ElementAccumulator]],
    st: _LoadState,
) -> tuple[list[RenderedElement], list[AdapterNoteRecord],
           dict[tuple, tuple[int, int | None, Rect]]]:
    counters: dict[tuple, int] = defaultdict(int)
    elements: list[RenderedElement] = []
    note_records: list[AdapterNoteRecord] = []
    voice_order: dict[tuple, int] = defaultdict(int)
    seen_ids: set[str] = set()
    identity_by_vid: dict[str, ElementIdentity] = {}
    # (part_id, measure, staff_local) → (page, system, staff-lines bbox),
    # for slash synthesis
    staff_geo: dict[tuple, tuple[int, int | None, Rect]] = {}

    for page, acc in accumulators:
        if acc.continuation:
            continue                     # second pass, after sources exist
        if acc.verovio_id in st.suppressed_spanners:
            continue                     # implausible tie: no element
        identity = _identity_for(acc, page, st, counters)
        if str(identity.element_id) in seen_ids:
            raise ValueError(f"duplicate ElementId {identity.element_id}")
        seen_ids.add(str(identity.element_id))
        if acc.verovio_id:
            identity_by_vid[acc.verovio_id] = identity

        if acc.bbox is None:
            continue
        anchor = acc.bbox.center
        if len(acc.use_origins) == 1 and not acc.texts:
            x, y = acc.use_origins[0].x, acc.use_origins[0].y
        else:
            x, y = anchor.x, anchor.y
        elements.append(RenderedElement(
            identity=identity, page=page, x=x, y=y, bbox=acc.bbox,
            anchor=anchor,
            glyph=RenderPrimitive(paths=tuple(acc.paths),
                                  texts=tuple(acc.texts)),
            system=acc.system,
            text_class=(acc.svg_class
                        if acc.kind is ElementKind.TEXT else None),
        ))

        if (identity.kind is ElementKind.STAFF_LINES
                and identity.part is not None and acc.measure is not None):
            staff_geo[(identity.part, acc.measure, identity.staff)] = \
                (page, acc.system, acc.bbox)

        if acc.svg_class == "note":
            mei_note = st.mei.notes.get(acc.verovio_id)
            onset = st.onset_by_id.get(acc.verovio_id)
            if mei_note is None or onset is None:
                raise ValueError(f"note {acc.verovio_id} missing from "
                                 f"MEI/timemap — join bridge broken")
            part = st.prep.part_for_staff(mei_note.staff)
            vkey = (part.part_id, mei_note.measure, mei_note.staff,
                    mei_note.layer)
            order = voice_order[vkey]
            voice_order[vkey] += 1
            note_records.append(AdapterNoteRecord(
                element_id=identity.element_id,
                part=part.part_id,
                measure=mei_note.measure,
                staff=mei_note.staff - part.first_staff + 1,
                voice=mei_note.layer,
                onset=onset,
                grace=mei_note.grace,
                pitch_step=mei_note.pname.upper() if mei_note.pname else None,
                pitch_alter=mei_note.alter,
                octave=mei_note.octave,
                staff_loc=mei_note.loc,
                chord_group=_chord_group(mei_note, st, part),
                order_in_voice=order,
            ))

    # Second pass: continuation segments inherit the source spanner's
    # identity under a ":seg<k>" id — deterministic because segment
    # matching and system order are (per-element overrides on a broken
    # spanner therefore target one segment, documented in the plan).
    for page, acc in accumulators:
        if not acc.continuation:
            continue
        if acc.source_vid in st.suppressed_spanners:
            continue    # its source tie is suppressed: drop the ink too
        source = identity_by_vid.get(acc.source_vid or "")
        if source is None or acc.bbox is None:
            # unmatched continuation ink: skip, flagged (ruling b) —
            # never silently absorbed into another element
            st.warnings.append(LoadWarning(
                "unattributed-continuation",
                f"{acc.svg_class} continuation segment in system "
                f"{acc.system} matched no source spanner — skipped"))
            continue
        eid = f"{source.element_id}:seg{acc.seg_index}"
        if eid in seen_ids:
            raise ValueError(f"duplicate ElementId {eid}")
        seen_ids.add(eid)
        identity = replace(source, element_id=ElementId(eid))
        elements.append(RenderedElement(
            identity=identity, page=page,
            x=acc.bbox.center.x, y=acc.bbox.center.y,
            bbox=acc.bbox, anchor=acc.bbox.center,
            glyph=RenderPrimitive(paths=tuple(acc.paths),
                                  texts=tuple(acc.texts)),
            system=acc.system,
        ))
    return elements, note_records, staff_geo


# ---------------------------------------------------------------------------
# Slash synthesis (CLAUDE.md rule 10, plan D4): Dorico exports slash
# regions as <measure-style><slash/> with no notes; Verovio renders those
# measures empty (MEI <space>). One slash per slash-unit, onsets on the
# beats, positioned on the staff so they render and animate like notes.
# ---------------------------------------------------------------------------

# Slash notehead as a parallelogram with horizontal end caps (approximates
# SMuFL noteheadSlashHorizontalEnds), in staff-space units, y-down, origin
# at the glyph's horizontal center on the middle staff line.
_SLASH_D = "M0.475 -1 L0.675 -1 L-0.475 1 L-0.675 1 Z"


def _synthesize_slashes(st: _LoadState,
                        staff_geo: dict[tuple, tuple[int, int | None, Rect]]
                        ) -> list[RenderedElement]:
    out: list[RenderedElement] = []
    glyph_bbox = path_bbox(_SLASH_D)
    for region in st.prep.slash_regions:
        info = next(p for p in st.prep.parts if p.part_id == region.part)
        for m in range(region.start_measure, region.stop_measure):
            start = st.measure_start[m]
            count = round(st.measure_duration[m] / region.slash_unit_quarters)
            if count <= 0:
                raise ValueError(f"slash region {region.part} m{m}: "
                                 f"non-positive slash count")
            # v1 limitation: slash regions on the part's first staff
            page, system, staff_bbox = staff_geo[(region.part, m, 1)]
            staff_space = staff_bbox.h / 4
            mid_y = staff_bbox.y + staff_bbox.h / 2
            slot_w = staff_bbox.w / count
            for k in range(count):
                cx = staff_bbox.x + (k + 0.5) * slot_w
                onset = start + k * region.slash_unit_quarters
                tf = Affine(a=staff_space, d=staff_space, e=cx, f=mid_y)
                bbox = tf.apply_rect(glyph_bbox)
                identity = ElementIdentity(
                    element_id=ElementId(f"{region.part}:m{m}:slash:{k}"),
                    kind=ElementKind.SLASH,
                    part=region.part, part_name=info.name,
                    staff=1, voice=None, onset=onset,
                )
                out.append(RenderedElement(
                    identity=identity, page=page, x=cx, y=mid_y,
                    bbox=bbox, anchor=bbox.center,
                    glyph=RenderPrimitive(paths=(
                        PathPrimitive(d=_SLASH_D, transform=tf),)),
                    system=system,
                ))
    return out


# Measure-repeat symbol (approximates SMuFL repeat1Bar): a bold oblique
# stroke with a dot in the upper-left and lower-right quadrants, in
# staff-space units, y-down, origin at the glyph's center on the middle
# staff line.
_REPEAT_D = ("M0.25 -1.1 L0.95 -1.1 L-0.25 1.1 L-0.95 1.1 Z "
             "M-0.62 -0.88 L-0.36 -0.62 L-0.62 -0.36 L-0.88 -0.62 Z "
             "M0.62 0.36 L0.88 0.62 L0.62 0.88 L0.36 0.62 Z")


def _synthesize_repeats(st: _LoadState,
                        staff_geo: dict[tuple, tuple[int, int | None, Rect]]
                        ) -> list[RenderedElement]:
    """One % symbol per repeated bar (ruling b — per measure), centered on
    the middle staff line, onset on the bar's downbeat. Verovio draws
    nothing for <measure-repeat> (empty <space>), so this is full
    synthesis in the slash shape (spikes/NOTES.md Phase 12)."""
    out: list[RenderedElement] = []
    glyph_bbox = path_bbox(_REPEAT_D)
    for region in st.prep.repeat_regions:
        info = next(p for p in st.prep.parts if p.part_id == region.part)
        for m in range(region.start_measure, region.stop_measure):
            # v1 limitation: repeat regions on the part's first staff
            page, system, staff_bbox = staff_geo[(region.part, m, 1)]
            staff_space = staff_bbox.h / 4
            cx = staff_bbox.x + staff_bbox.w / 2
            mid_y = staff_bbox.y + staff_bbox.h / 2
            tf = Affine(a=staff_space, d=staff_space, e=cx, f=mid_y)
            bbox = tf.apply_rect(glyph_bbox)
            identity = ElementIdentity(
                element_id=ElementId(f"{region.part}:m{m}:barrepeat"),
                kind=ElementKind.BAR_REPEAT,
                part=region.part, part_name=info.name,
                staff=1, voice=None, onset=st.measure_start[m],
            )
            out.append(RenderedElement(
                identity=identity, page=page, x=cx, y=mid_y,
                bbox=bbox, anchor=bbox.center,
                glyph=RenderPrimitive(paths=(
                    PathPrimitive(d=_REPEAT_D, transform=tf),)),
                system=system,
            ))
    return out


def _chord_group(mei_note: _MeiNote, st: _LoadState,
                 part: "PartInfo") -> str | None:
    """Neutral per-chord token: (part, measure, voice, onset-of-chord)."""
    if mei_note.chord_id is None:
        return None
    first = next(iter(st.mei.chord_members.get(mei_note.chord_id, ())), None)
    onset = st.onset_by_id.get(first) if first else None
    return f"{part.part_id}:m{mei_note.measure}:v{mei_note.layer}:q{onset}"


def _attach_onset(st: _LoadState, vid: str) -> Beats | None:
    """Attach point of a measure-attached object: @startid's note onset
    (a chord reference resolves through its first member), else @tstamp
    arithmetic. None when the element carries neither."""
    ref = st.mei.attach_startid.get(vid)
    if ref:
        if ref in st.onset_by_id:
            return st.onset_by_id[ref]
        member = next(iter(st.mei.chord_members.get(ref, ())), None)
        if member and member in st.onset_by_id:
            return st.onset_by_id[member]
    if vid in st.mei.tstamps_by_id:
        return _tstamp_extent(st.mei.tstamps_by_id[vid], st)[0]
    return None


def _identity_for(acc: _ElementAccumulator, page: int, st: _LoadState,
                  counters: dict[tuple, int]) -> ElementIdentity:
    prep = st.prep
    kind_tag = _ID_TAG[acc.kind] if acc.svg_class != "dots" else "dots"
    if acc.svg_class == "note":
        kind_tag = "note"

    if acc.kind is ElementKind.GROUP_SYMBOL:
        # Geometric identity (Phase 10, replacing the injected-slot
        # ordinal): the symbol's bbox says which staves it spans, and
        # part_for_staff turns that into a part span — self-identifying
        # for injected groups AND native ones (a multi-staff part's
        # brace, foreign part-groups). Slot bookkeeping cannot work:
        # Verovio SUPPRESSES a native brace when an injected group
        # overlaps its part (triage spike, section E). Injected groups
        # keep their exact Phase 8 ids (score:sys{n}:grpsym:P1-P2); a
        # multi-staff part's own brace mints its part id alone
        # (score:sys{n}:grpsym:P5).
        if acc.system is None or acc.bbox is None:
            raise ValueError("group symbol without system/bbox")
        centers = st.staff_centers_by_system.get(acc.system, {})
        covered = sorted(n for n, cy in centers.items()
                         if acc.bbox.y <= cy <= acc.bbox.y + acc.bbox.h)
        if not covered or covered != list(range(covered[0],
                                                covered[-1] + 1)):
            raise ValueError(
                f"group symbol in system {acc.system} spans staves "
                f"{covered} — expected a contiguous non-empty range")
        first = prep.part_for_staff(covered[0])
        last = prep.part_for_staff(covered[-1])
        if first is last and first.staff_count > 1:
            span = first.part_id             # native grand-staff brace
        else:
            span = f"{first.part_id}-{last.part_id}"
        return ElementIdentity(
            element_id=ElementId(f"score:sys{acc.system}:grpsym:{span}"),
            kind=acc.kind, part=None, part_name=None, staff=None,
            voice=None, onset=None, extent=None,
        )

    if acc.kind is ElementKind.SYSTEM_DIVIDER:
        scope = ("systemdivider", acc.system)
        seq = counters[scope]
        counters[scope] += 1
        return ElementIdentity(
            element_id=ElementId(
                f"score:sys{acc.system}:systemdivider:{seq}"),
            kind=acc.kind, part=None, part_name=None, staff=None,
            voice=None, onset=None, extent=None,
        )

    # staff: from SVG nesting; measure-attached elements (dynam, dir…)
    # carry it as an MEI @staff attribute; spanners inherit their start
    # note's staff and voice.
    staff_n = acc.staff or st.mei.staff_attr_by_id.get(acc.verovio_id)
    layer_n = acc.layer
    is_spanner = acc.svg_class in _SPANNER_CLASSES
    if is_spanner and acc.verovio_id in st.mei.spanners:
        start_id, _ = st.mei.spanners[acc.verovio_id]
        start_note = st.mei.notes.get(start_id or "")
        if start_note is not None:
            staff_n = staff_n or start_note.staff
            layer_n = layer_n if layer_n is not None else start_note.layer

    part = part_name = None
    staff_local = None
    if staff_n:
        info = prep.part_for_staff(staff_n)
        part, part_name = info.part_id, info.name
        staff_local = staff_n - info.first_staff + 1

    # Onset resolution is GATED BY svg_class so a note-owned fragment
    # never picks up a spurious onset from its own id: under condensed
    # layout Verovio reuses SVG group ids across element types, so a
    # stem's id can collide with a distant note/spanner id. Only the
    # element type the table is FOR may consult it (Phase 10R fix).
    onset: Beats | None = None
    extent: tuple[Beats, Beats] | None = None
    vid = acc.verovio_id
    if acc.svg_class in _TIMEMAP_CLASSES and vid in st.onset_by_id:
        onset = st.onset_by_id[vid]
    elif is_spanner and vid in st.mei.spanners:
        start_id, end_id = st.mei.spanners[vid]
        start = st.onset_by_id.get(start_id or "")
        end = st.onset_by_id.get(end_id or "")
        if start is not None:
            onset = start
            extent = (start, end if end is not None else start)
        elif vid in st.mei.tstamps_by_id:
            # timestamp-addressed spanner (hairpins carry @tstamp/@tstamp2
            # and @staff, no startid/endid — Phase 5 spike)
            onset, extent = _tstamp_extent(st.mei.tstamps_by_id[vid], st)
    elif acc.svg_class == "beam" and vid in st.mei.beam_note_ids:
        onsets = [st.onset_by_id[n] for n in st.mei.beam_note_ids[vid]
                  if n in st.onset_by_id]
        if onsets:
            onset = min(onsets)
            extent = (min(onsets), max(onsets))
    elif acc.svg_class == "beamSpan" and vid in st.mei.beamspan_ends:
        # a beamSpan is a measure-level beam: its onset/extent come from
        # its @startid/@endid note onsets, not the layer-beam table
        start_id, end_id = st.mei.beamspan_ends[vid]
        ends = [st.onset_by_id[n] for n in (start_id, end_id)
                if n and n in st.onset_by_id]
        if ends:
            onset = min(ends)
            extent = (min(ends), max(ends))
    elif acc.owner_onset is not None:
        onset = acc.owner_onset          # stems, flags, accid, artic, dots
    elif (attach := _attach_onset(st, vid)) is not None:
        # a measure-attached object's onset is its attach point
        # (dynamics: ruling 2026-07-12; fermatas, trills/ornaments,
        # dirs, tempo, harm: Phase 10R)
        onset = attach
    elif acc.measure is not None \
            and acc.kind not in STATIC_KINDS \
            and acc.kind not in REVEALED_KINDS \
            and acc.svg_class not in _STATIC_TEXT_CLASSES:
        # Measure-start fallback for an attach-less, non-scaffold object
        # (animate-everything ruling 2026-07-20): clefs, key signatures,
        # meter changes, and measure-attached texts/dynamics light when
        # their measure begins. NOTE-REGION decorations do NOT reach here
        # — tuplets/tremolos inherit their notes' onset via owner_onset
        # (else this fallback would fire them at the downbeat, before
        # their first note — the 2026-07-20 tuplet bug). Spanners
        # (REVEALED_KINDS) are excluded too: a slur/tie/hairpin's timing
        # is its start note or nothing, never a spurious downbeat — if
        # its start is unresolved it stays onset-less (its reveal is
        # edge-driven regardless). Scaffold (STATIC_KINDS) and page
        # furniture (_STATIC_TEXT_CLASSES) stay onset-less = static.
        onset = st.measure_start.get(acc.measure)

    # spanners for notes were handled; note extent stays None in v1

    if acc.measure is not None and part is not None:
        scope = (part, acc.measure, staff_local, layer_n, kind_tag)
        seq = counters[scope]
        counters[scope] += 1
        eid = (f"{part}:m{acc.measure}:s{staff_local}:"
               f"v{layer_n if layer_n is not None else 0}:{kind_tag}:{seq}")
    elif acc.measure is not None:
        scope = ("score", acc.measure, kind_tag)
        seq = counters[scope]
        counters[scope] += 1
        eid = f"score:m{acc.measure}:{kind_tag}:{seq}"
    else:
        scope = ("page", page, kind_tag)
        seq = counters[scope]
        counters[scope] += 1
        eid = f"score:p{page}:{kind_tag}:{seq}"

    return ElementIdentity(
        element_id=ElementId(eid), kind=acc.kind,
        part=part, part_name=part_name, staff=staff_local,
        voice=layer_n, onset=onset, extent=extent,
    )
