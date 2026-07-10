"""Verovio adapter: MusicXML → identity-tagged, paged Layout (plan D2/D3/D5).

Verovio types, ids, and SVG never leak past this module (CLAUDE.md rule 4).
ElementIds are minted here from musical identity (part/measure/staff/voice/
kind/index), so they are deterministic across loads and survive engraving
reflows. A fixed xmlIdSeed keeps Verovio's internal ids reproducible for
the timemap ↔ SVG ↔ MEI cross-referencing inside a load.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import verovio

from scoreanim.core.engraving.provider import EngravingProvider
from scoreanim.core.engraving.svg_geom import (ellipse_path, line_path,
                                               parse_transform, path_bbox,
                                               polygon_path, rect_path)
from scoreanim.core.engraving.types import (TRANSPOSE_TO_SOUNDING_PITCH,
                                            Affine, EngravingParams, Layout,
                                            PageGeometry, PathPrimitive,
                                            Point, Rect, RenderedElement,
                                            RenderPrimitive, TextPrimitive,
                                            TextRun)
from scoreanim.core.score.identity import (Beats, ElementId, ElementIdentity,
                                           ElementKind, PartId)
from scoreanim.core.score.musicxml_prep import (PartInfo, PreparedScore,
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
    "system": ElementKind.OTHER,        # owns only the systemic barline path
}

# Transparent grouping classes: never emitted, provide context only.
# keyAccid/fig fold their glyphs into the enclosing keySig / harm element;
# space and the milestone markers contain nothing drawable.
_CONTAINER_CLASSES = {
    "measure", "layer", "chord", "graceGrp", "notehead", "ledgerLines",
    "page-margin", "definition-scale", "section", "pb", "sb", "ending",
    "keyAccid", "fig", "mdiv", "score", "svg", "space",
    "pageMilestoneEnd", "systemMilestoneEnd", "pageElement",
}

# Short kind tag used inside minted ElementIds.
_ID_TAG = {k: k.name.lower() for k in ElementKind}

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
    spanners: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    measure_by_id: dict[str, int] = field(default_factory=dict)
    # measure-attached elements (dynam, dir, tempo, harm...) → their @staff
    staff_attr_by_id: dict[str, int] = field(default_factory=dict)


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
            elif sp.get("staff"):
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
                   measure=None, staff=None, layer=None, owner_onset=None)
        if self.drawables_claimed != self.drawables_seen:
            raise ValueError(
                f"page {self.page}: {self.drawables_seen - self.drawables_claimed} "
                f"drawable(s) not claimed by any element — decomposition is lossy")
        return self.done

    # -- tree walk ----------------------------------------------------------

    def _walk(self, node: ET.Element, ctm: Affine,
              owner: _ElementAccumulator | None,
              measure: int | None, staff: int | None, layer: int | None,
              owner_onset: Beats | None) -> None:
        st = self.st
        for child in node:
            tag = child.tag.removeprefix(_SVG_NS)
            child_ctm = ctm.compose(parse_transform(child.get("transform")))
            if tag == "g":
                cls = (child.get("class") or "").split()[0] if child.get("class") else ""
                cid = child.get(_XML_ID) or child.get("id")
                new_measure, new_staff, new_layer = measure, staff, layer
                new_owner, new_owner_onset = owner, owner_onset
                if cls == "measure" and cid in st.mei.measure_by_id:
                    new_measure = st.mei.measure_by_id[cid]
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
                if cid and cls in _KIND_BY_CLASS:
                    acc = _ElementAccumulator(
                        verovio_id=cid, svg_class=cls,
                        kind=_KIND_BY_CLASS[cls],
                        measure=new_measure, staff=new_staff, layer=new_layer,
                        owner_onset=new_owner_onset)
                    self._walk(child, child_ctm, acc, new_measure, new_staff,
                               new_layer, new_owner_onset)
                    if acc.paths or acc.texts:
                        self.done.append(acc)
                    continue
                if cls and cls not in _CONTAINER_CLASSES and cls not in _KIND_BY_CLASS \
                        and self._has_drawables(child):
                    raise ValueError(f"page {self.page}: unknown SVG class "
                                     f"{cls!r} with drawable content")
                self._walk(child, child_ctm, new_owner, new_measure, new_staff,
                           new_layer, new_owner_onset)
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

    def load(self, score_path: Path, params: EngravingParams) -> Layout:
        return self.load_detailed(score_path, params).layout

    def load_detailed(self, score_path: Path,
                      params: EngravingParams) -> EngravedScore:
        prep = prepare(score_path)
        tk = verovio.toolkit()
        tk.setOptions({
            "breaks": "encoded",
            "font": "Bravura",
            "pageWidth": round(prep.page_width),
            "pageHeight": round(prep.page_height),
            "scaleToPageSize": True,
            "header": "encoded",
            "footer": "encoded",
            "svgHtml5": False,
            "svgViewBox": True,
            "transposeToSoundingPitch": TRANSPOSE_TO_SOUNDING_PITCH,
            "xmlIdSeed": params.xml_id_seed,
        })
        if not tk.loadData(prep.canonical_xml):
            raise ValueError(f"Verovio failed to load {score_path}")

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
            layer_n_by_id={},
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

        elements, note_records, staff_geo = _build_elements(accumulators, state)
        elements.extend(_synthesize_slashes(state, staff_geo))
        layout = Layout(pages=pages, elements=tuple(elements))
        return EngravedScore(layout=layout,
                             note_records=tuple(note_records),
                             prepared=prep)


def _container_ns(mei_xml: str, tag: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for el in ET.fromstring(mei_xml).iter(f"{_MEI_NS}{tag}"):
        el_id = el.get(_XML_ID)
        if el_id and el.get("n"):
            result[el_id] = _int_or(el.get("n"), 0)
    return result


# ---------------------------------------------------------------------------
# Identity minting (plan D5) and element construction
# ---------------------------------------------------------------------------

def _build_elements(
    accumulators: list[tuple[int, _ElementAccumulator]],
    st: _LoadState,
) -> tuple[list[RenderedElement], list[AdapterNoteRecord],
           dict[tuple, tuple[int, Rect]]]:
    counters: dict[tuple, int] = defaultdict(int)
    elements: list[RenderedElement] = []
    note_records: list[AdapterNoteRecord] = []
    voice_order: dict[tuple, int] = defaultdict(int)
    seen_ids: set[str] = set()
    # (part_id, measure, staff_local) → (page, staff-lines bbox), for
    # slash synthesis
    staff_geo: dict[tuple, tuple[int, Rect]] = {}

    for page, acc in accumulators:
        identity = _identity_for(acc, page, st, counters)
        if str(identity.element_id) in seen_ids:
            raise ValueError(f"duplicate ElementId {identity.element_id}")
        seen_ids.add(str(identity.element_id))

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
        ))

        if (identity.kind is ElementKind.STAFF_LINES
                and identity.part is not None and acc.measure is not None):
            staff_geo[(identity.part, acc.measure, identity.staff)] = \
                (page, acc.bbox)

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
                        staff_geo: dict[tuple, tuple[int, Rect]]
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
            page, staff_bbox = staff_geo[(region.part, m, 1)]
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


def _identity_for(acc: _ElementAccumulator, page: int, st: _LoadState,
                  counters: dict[tuple, int]) -> ElementIdentity:
    prep = st.prep
    kind_tag = _ID_TAG[acc.kind] if acc.svg_class != "dots" else "dots"
    if acc.svg_class == "note":
        kind_tag = "note"

    # staff: from SVG nesting; measure-attached elements (dynam, dir…)
    # carry it as an MEI @staff attribute; spanners inherit their start
    # note's staff and voice.
    staff_n = acc.staff or st.mei.staff_attr_by_id.get(acc.verovio_id)
    layer_n = acc.layer
    if acc.verovio_id in st.mei.spanners:
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

    onset: Beats | None = None
    extent: tuple[Beats, Beats] | None = None
    vid = acc.verovio_id
    if vid in st.onset_by_id:
        onset = st.onset_by_id[vid]
    elif vid in st.mei.spanners:
        start_id, end_id = st.mei.spanners[vid]
        start = st.onset_by_id.get(start_id or "")
        end = st.onset_by_id.get(end_id or "")
        if start is not None:
            onset = start
            extent = (start, end if end is not None else start)
    elif vid in st.mei.beam_note_ids:
        onsets = [st.onset_by_id[n] for n in st.mei.beam_note_ids[vid]
                  if n in st.onset_by_id]
        if onsets:
            onset = min(onsets)
            extent = (min(onsets), max(onsets))
    elif acc.owner_onset is not None:
        onset = acc.owner_onset          # stems, flags, accid, artic, dots
    elif acc.kind in (ElementKind.DYNAMIC, ElementKind.TEXT,
                      ElementKind.CHORD_SYMBOL, ElementKind.MREST) \
            and acc.measure is not None:
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
