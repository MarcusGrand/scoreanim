"""SVG decomposition: one engraved page → identity-bearing accumulators.

_PageDecomposer walks the page SVG tree, dereferencing <use> glyphs and
folding drawables into one _ElementAccumulator per emitted element
(kinds tables decide what emits, what nests, and what is transparent).
Reads _LoadState lookups (onsets, staff/layer ns, MEI index) and appends
load warnings; the accumulators feed every downstream post-pass.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from scoreanim.core.engraving.svg_geom import (ellipse_path, line_path,
                                               parse_transform, path_bbox,
                                               polygon_path, rect_path)
from scoreanim.core.engraving.types import (Affine, LoadWarning,
                                            PathPrimitive, Point, Rect,
                                            TextPrimitive, TextRun)
from scoreanim.core.engraving.verovio.kinds import (
    _BOLD_TEXT_CLASSES, _CONTAINER_CLASSES, _ITALIC_TEXT_CLASSES,
    _KIND_BY_CLASS, _SPANNER_CLASSES, _SVG_NS, _XLINK_HREF, _XML_ID)
from scoreanim.core.engraving.verovio.mei_index import _int_or
from scoreanim.core.engraving.verovio.records import _LoadState
from scoreanim.core.score.identity import Beats, ElementKind

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
