"""Reclaim decoration ink stolen under Verovio id reuse.

Under hide-empty-staves the optimize round-trip re-mints xml:ids, and
Verovio can draw a decoration's ink inside a foreign group elsewhere on
the page that carries the same id, leaving the decoration's own <g>
empty (2026-08-10, testdata/triplet_error.musicxml m28: a tuplet "3"
drawn inside another part's note, a tuplet bracket inside another
part's staff). The spanner reclaim cannot help — a bracket is a
straight polyline and a numeral a glyph, not a bézier curve — so this
pass reclaims BY SIGNATURE: for an empty id-bearing group whose class
is in kinds._DECORATION_INK and whose id appears on other groups in
the same page, the direct drawable children of those groups matching
the class's own ink signature are the stolen ink.

`scan` runs on the raw page tree before the walk and marks the stolen
nodes; the walk buffers them instead of handing them to their host;
`finish` folds the buffered ink onto the empty accumulators and warns.
An empty decoration group whose id collides but whose ink is nowhere
to be found is dropped loudly (raised under strict). An empty
decoration group with NO collision stays silent — empty groups are
routine; only a collision is evidence of theft.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from scoreanim.core.engraving.types import LoadWarning
from scoreanim.core.engraving.verovio.kinds import (_DECORATION_INK,
                                                    _SVG_NS, _XLINK_HREF,
                                                    _XML_ID)

_DRAWABLE_TAGS = {"use", "path", "rect", "line", "polygon", "polyline",
                  "ellipse", "circle", "text"}


@dataclass
class _Expectation:
    """One empty decoration group whose id is reused elsewhere."""
    vid: str
    svg_class: str
    measure_id: str | None                    # its own enclosing measure
    # (host class, host measure id, matching direct drawables found)
    hosts: list[tuple[str, str | None, int]] = field(default_factory=list)


@dataclass
class ReclaimPlan:
    stolen: dict[int, str]                    # id(ET node) → victim vid
    expected: dict[str, _Expectation]         # victim vid → expectation

    def is_expected(self, cid: str | None, svg_class: str) -> bool:
        """True when this id-bearing group is a registered victim, so
        the walk keeps its empty accumulator alive for the fold."""
        exp = self.expected.get(cid or "")
        return exp is not None and exp.svg_class == svg_class


def _matches(node: ET.Element, tag_needed: str,
             code_range: tuple[int, int] | None) -> bool:
    """Does this direct child carry the decoration's ink signature?"""
    if node.tag.removeprefix(_SVG_NS) != tag_needed:
        return False
    if code_range is None:
        return True
    href = (node.get(_XLINK_HREF) or node.get("href") or "").lstrip("#")
    try:
        code = int(href.split("-", 1)[0], 16)
    except ValueError:
        return False
    return code_range[0] <= code <= code_range[1]


def _has_drawables(g: ET.Element) -> bool:
    return any(e.tag.removeprefix(_SVG_NS) in _DRAWABLE_TAGS
               for e in g.iter() if e is not g)


def scan(inner: ET.Element) -> ReclaimPlan:
    """Pre-scan one page tree: which drawable nodes are stolen
    decoration ink, and which empty groups expect it back."""
    # gid → [(group node, class, enclosing measure id)], document order
    groups: dict[str, list[tuple[ET.Element, str, str | None]]] = {}

    def walk(node: ET.Element, measure_id: str | None) -> None:
        for child in node:
            if child.tag != f"{_SVG_NS}g":
                continue
            cls = (child.get("class") or "").split()[0] \
                if child.get("class") else ""
            gid = child.get(_XML_ID) or child.get("id")
            m = gid if cls == "measure" and gid else measure_id
            if gid:
                groups.setdefault(gid, []).append((child, cls, m))
            walk(child, m)

    walk(inner, None)

    plan = ReclaimPlan(stolen={}, expected={})
    for gid, entries in groups.items():
        if len(entries) < 2:
            continue
        for victim, cls, measure_id in entries:
            signature = _DECORATION_INK.get(cls)
            if signature is None or _has_drawables(victim):
                continue
            exp = _Expectation(vid=gid, svg_class=cls,
                               measure_id=measure_id)
            for host, host_cls, host_measure in entries:
                if host is victim:
                    continue
                found = 0
                for node in host:
                    if _matches(node, *signature):
                        plan.stolen[id(node)] = gid
                        found += 1
                exp.hosts.append((host_cls, host_measure, found))
            plan.expected[gid] = exp
    return plan


def finish(plan: ReclaimPlan, buffered, done: list, add_drawable,
           measure_by_id: dict[str, int], warnings: list[LoadWarning],
           strict: bool, page: int) -> None:
    """Fold the buffered stolen ink onto its own (kept-empty)
    accumulators, then warn per group — or drop and warn/raise where
    the ink never turned up. `buffered` is [(vid, tag, node, ctm)] in
    document order; `add_drawable` is the decomposer's own, so the
    fold builds paths and bboxes exactly as a normal claim would."""

    def m_name(mid: str | None) -> str:
        n = measure_by_id.get(mid or "")
        return f"m{n}" if n is not None else "m?"

    by_victim: dict[str, list] = {}
    for vid, tag, node, ctm in buffered:
        by_victim.setdefault(vid, []).append((tag, node, ctm))

    acc_by_key = {}
    for acc in done:
        acc_by_key.setdefault((acc.verovio_id, acc.svg_class), acc)

    failed = []
    for vid, exp in plan.expected.items():
        acc = acc_by_key.get((vid, exp.svg_class))
        ink = by_victim.get(vid, [])
        where = f"{exp.svg_class} {m_name(exp.measure_id)}"
        if acc is not None and ink:
            for tag, node, ctm in ink:
                add_drawable(acc, tag, node, ctm)
            hosts = ", ".join(f"{cls} {m_name(mid)}"
                              for cls, mid, found in exp.hosts if found)
            warnings.append(LoadWarning(
                "reclaimed-decoration-ink",
                f"{where}: {len(ink)} drawable(s) drawn inside foreign "
                f"group(s) sharing its reused id ({hosts}) — reclaimed "
                f"onto its own element (Verovio id-reuse artifact under "
                f"hide-empty-staves)"))
            continue
        hosts = ", ".join(f"{cls} {m_name(mid)}"
                          for cls, mid, _ in exp.hosts)
        msg = (f"{where}: its group is empty and its id is reused by "
               f"{len(exp.hosts)} other group(s) ({hosts}), but no "
               f"matching ink was found — the decoration is missing")
        if strict:
            raise ValueError(f"page {page}: {msg}")
        warnings.append(LoadWarning("empty-decoration", msg))
        if acc is not None:
            failed.append(acc)
    if failed:
        done[:] = [a for a in done if all(a is not f for f in failed)]
