"""D5 (L0, adapter): kind/ink purity — the FINDING-5 oracle.

(a) Straight-ink kinds (stem, ledger, beam) must hold no bézier paths,
and compact kinds must fit sane per-kind bbox bounds — a stem 30
staff-spaces wide is somebody else's ink. (b) Every MEI slur/tie that
the engraver actually inked must yield exactly ONE SLUR/TIE element
attributed to its own staff's part — audited against the raw page SVG
and MEI captured DURING the load (Verovio reuses xml:ids across element
types under hide-empty-staves and can nest a spanner's curve inside a
foreign stem/flag group; the reused id also masks the dropped-spanner
warning, so the absorption is silent everywhere else).
"""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import median
from xml.etree import ElementTree

# Adapter-stage internals: D5 audits Verovio ids against our elements,
# which is inherently adapter-internal work. Diagnosis only — nothing
# here feeds animation (rule 4 intact).
from scoreanim.core.engraving.verovio import identity as _identity_mod
from scoreanim.core.engraving.verovio.kinds import _SVG_NS, _XML_ID
from scoreanim.core.score.identity import ElementKind
from scoreanim.tools.live_oracle.bundle import Finding, OracleBundle

# Kinds whose own ink is straight by construction: stems are rects,
# ledger dashes are lines, beams are polygons. A C/S/Q bézier inside one
# of these is foreign ink (a spanner curve swallowed by id reuse).
_STRAIGHT_INK_KINDS = {ElementKind.STEM, ElementKind.LEDGER_LINES,
                       ElementKind.BEAM}

# Sane per-kind bbox bounds, in staff spaces (max_w, max_h). Generous —
# a cross-staff piano stem spans two staves and the gap (~16sp tall);
# the corrupted hosts measure 15-35sp WIDE, an order of magnitude out.
_KIND_BBOX_SP: dict[ElementKind, tuple[float, float]] = {
    ElementKind.STEM: (4.0, 24.0),
    ElementKind.FLAG: (6.0, 12.0),
    ElementKind.NOTEHEAD: (8.0, 8.0),
    ElementKind.ACCIDENTAL: (6.0, 12.0),
    ElementKind.ARTICULATION: (8.0, 8.0),
    ElementKind.LEDGER_LINES: (12.0, 3.0),
}

_CURVE_CMD_RE = re.compile(r"[CcSsQqTt]")
_SPANNER_SVG_CLASSES = ("slur", "tie", "lv")
_SPANNER_KIND_BY_TAG = {"slur": ElementKind.SLUR, "tie": ElementKind.TIE,
                        "lv": ElementKind.TIE}
_DRAWABLE_TAGS = {"use", "path", "rect", "line", "polygon", "polyline",
                  "ellipse", "circle", "text"}


def _staff_space(bundle: OracleBundle) -> float | None:
    """One staff space in layout units: median STAFF_LINES bbox height is
    4 spaces. Scale-to-fit shrinks both, so bounds track the engraving."""
    heights = [el.bbox.h for el in bundle.engraved.layout.elements
               if el.identity.kind is ElementKind.STAFF_LINES
               and el.bbox.h > 0]
    return median(heights) / 4.0 if heights else None


def audit_kind_purity(bundle: OracleBundle,
                      log: list[str] | None = None) -> list[Finding]:
    """(a) Straight-ink kinds must hold no bézier paths; compact kinds
    must fit sane per-kind bbox bounds. Either violation means the
    element carries somebody else's ink and will fire it at ITS onset —
    the early-slur mechanism."""
    findings: list[Finding] = []
    sp = _staff_space(bundle)
    if sp is None or sp <= 0:
        if log is not None:
            log.append("D5: no staff-lines geometry — purity bounds skipped")
        return findings
    for el in bundle.engraved.layout.elements:
        kind = el.identity.kind
        eid = str(el.identity.element_id)
        if kind in _STRAIGHT_INK_KINDS:
            curved = sum(1 for p in el.glyph.paths
                         if _CURVE_CMD_RE.search(p.d))
            if curved:
                findings.append(Finding(
                    "D5", "kind-curve-ink", eid,
                    f"kind={kind.name} carries {curved} bézier path(s) of "
                    f"{len(el.glyph.paths)} — foreign curve ink folded in "
                    f"(bbox {el.bbox.w:.0f}x{el.bbox.h:.0f} = "
                    f"{el.bbox.w / sp:.1f}x{el.bbox.h / sp:.1f} sp)"))
                continue                 # one finding per element suffices
        bound = _KIND_BBOX_SP.get(kind)
        if bound is not None:
            max_w, max_h = bound
            if el.bbox.w > max_w * sp or el.bbox.h > max_h * sp:
                findings.append(Finding(
                    "D5", "kind-bbox-oversize", eid,
                    f"kind={kind.name} bbox {el.bbox.w:.0f}x{el.bbox.h:.0f} "
                    f"= {el.bbox.w / sp:.1f}x{el.bbox.h / sp:.1f} sp exceeds "
                    f"the sane bound {max_w:g}x{max_h:g} sp — foreign ink "
                    f"folded in"))
    return findings


def audit_spanner_coverage(bundle: OracleBundle,
                           log: list[str] | None = None) -> list[Finding]:
    """(b) Every MEI slur/tie the engraver inked must yield exactly one
    SLUR/TIE element attributed to its own staff's part. Two truth
    sources from the load capture: the raw page SVGs (which spanner
    groups actually carry ink) and the accumulator list (where each id's
    ink ended up). Identity minting is re-run over the captured
    accumulators — the same pure loop _build_elements runs — so the
    reported ElementIds match the layout exactly."""
    cap = bundle.capture
    if cap is None or cap.state is None:
        if log is not None:
            log.append("D5: prebuilt engraving, no load capture — "
                       "spanner-coverage sub-check skipped")
        return []
    st = cap.state
    findings: list[Finding] = []
    layout_ids = {str(el.identity.element_id)
                  for el in bundle.engraved.layout.elements}

    # Independent SVG truth: id-bearing slur/tie groups that carry ink.
    svg_inked: dict[str, int] = {}
    for page in sorted(cap.svg_pages):
        root = ElementTree.fromstring(cap.svg_pages[page])
        for g in root.iter(f"{_SVG_NS}g"):
            cls = (g.get("class") or "").split()[0] if g.get("class") else ""
            if cls not in _SPANNER_SVG_CLASSES:
                continue
            cid = g.get(_XML_ID) or g.get("id")
            if not cid:
                continue         # id-less continuation segment (own pipeline)
            if any(e.tag.removeprefix(_SVG_NS) in _DRAWABLE_TAGS
                   for e in g.iter() if e is not g):
                svg_inked.setdefault(cid, page)

    # Where each verovio id's ink ended up, with the identity it minted —
    # the exact _build_elements first-pass loop (same skips, same
    # counters), so eids match the layout byte for byte.
    counters: dict[tuple, int] = defaultdict(int)
    minted: dict[str, list] = defaultdict(list)
    for page, acc in cap.accumulators:
        if acc.continuation:
            continue
        if acc.verovio_id in st.suppressed_spanners:
            continue
        ident = _identity_mod._identity_for(acc, page, st, counters)
        if acc.verovio_id:
            minted[acc.verovio_id].append((acc, ident))

    for vid, tag in sorted(st.mei.spanner_tags.items()):
        want = _SPANNER_KIND_BY_TAG.get(tag)
        if want is None:
            continue             # hairpin/octave: out of D5's slur/tie scope
        if vid in st.suppressed_spanners:
            continue             # implausible tie: intentionally absent
        entries = minted.get(vid, [])
        spanner_entries = [(a, i) for a, i in entries
                           if a.svg_class in _SPANNER_SVG_CLASSES]
        host_entries = [(a, i) for a, i in entries
                        if a.svg_class not in _SPANNER_SVG_CLASSES]
        start_id, _ = st.mei.spanners.get(vid, (None, None))
        start_note = st.mei.notes.get(start_id or "")
        staff_n = (start_note.staff if start_note is not None
                   else st.mei.staff_attr_by_id.get(vid, 0))
        expected_part = (st.prep.part_for_staff(staff_n).part_id
                         if staff_n else None)
        where = (f"starts {expected_part} m{start_note.measure}"
                 if start_note is not None else f"staff {staff_n or '?'}")

        if not spanner_entries:
            if host_entries:
                hosts = ", ".join(
                    f"{i.element_id}"
                    + ("(+curve ink)" if any(_CURVE_CMD_RE.search(p.d)
                                             for p in a.paths) else "")
                    for a, i in host_entries)
                findings.append(Finding(
                    "D5", "spanner-absorbed", vid,
                    f"{tag} ({where}): no {want.name} element minted — its "
                    f"reused id is claimed by non-spanner group(s) {hosts}; "
                    f"the reused id also masks the dropped-spanner warning"))
            elif vid in svg_inked:
                findings.append(Finding(
                    "D5", "spanner-ink-lost", vid,
                    f"{tag} ({where}): inked <g> on page {svg_inked[vid]} "
                    f"but no element and no accumulator — decompose lost it"))
            # else: engraver drew nothing — the dropped-spanner warning path
            continue
        if len(spanner_entries) > 1:
            findings.append(Finding(
                "D5", "spanner-duplicate", vid,
                f"{tag} ({where}): {len(spanner_entries)} spanner elements "
                f"minted for one id: "
                f"{', '.join(str(i.element_id) for _, i in spanner_entries)}"))
        acc, ident = spanner_entries[0]
        if ident.kind is not want:
            findings.append(Finding(
                "D5", "spanner-wrong-kind", vid,
                f"{tag} ({where}): minted {ident.element_id} "
                f"kind={ident.kind.name}, expected {want.name}"))
        if expected_part is not None and ident.part != expected_part:
            findings.append(Finding(
                "D5", "spanner-wrong-part", vid,
                f"{tag} ({where}): minted {ident.element_id} on part "
                f"{ident.part}, expected {expected_part}"))
        if str(ident.element_id) not in layout_ids:
            findings.append(Finding(
                "D5", "spanner-element-missing", vid,
                f"{tag} ({where}): identity {ident.element_id} minted but "
                f"absent from the layout (ink-less accumulator)"))

    # SVG cross-check: an inked spanner group whose id minted no spanner
    # element and isn't an MEI spanner at all (should never happen).
    for cid, page in sorted(svg_inked.items()):
        if cid not in st.mei.spanner_tags:
            findings.append(Finding(
                "D5", "spanner-unknown-id", cid,
                f"inked spanner <g> on page {page} with an id the MEI has "
                f"no slur/tie/hairpin for"))
    return findings


def check_d5(bundle: OracleBundle,
             log: list[str] | None = None) -> list[Finding]:
    return audit_kind_purity(bundle, log) + audit_spanner_coverage(bundle, log)
