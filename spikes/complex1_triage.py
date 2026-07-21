"""Phase 11 planning — complex1/complex2 triage spike (kept).

Verifies the PHASE11_BRIEF diagnosis against the real files instead of
trusting it: reproduces each diagnosed failure in the brief's order,
confirms the shim results, and pins the facts the Phase 11 plan builds
on. After the 11.1-11.4 fixes land, the failure sections report "no
longer raises" and the anatomy sections remain durable library
documentation (the video_test_triage.py pattern).

Questions, against testdata/complex1.musicxml (14 single-staff parts,
3 pages) and testdata/complex2.musicxml (36 parts / 37 staves,
orchestral — Phase 12's file, but its decomposer/geometry failures are
scheduled into Phase 11):

A. `bTrem` unknown SVG class (complex1, brief item 1): reproduce the
   _walk raise; what is bTrem structurally — id-bearing? direct
   drawables (container shim would orphan them)? WHERE does the
   tremolo stroke ink live (informs ruling (a): does it animate with
   the owning note for free)? fTrem twin on complex2.
B. `beamSpan` unknown SVG class (complex2, brief item 1b): reproduce;
   anatomy — id-bearing, drawable, and which onset table could serve
   it (MEI beamSpan @startid/@endid vs the layer-beam table).
C. `rotate` transform crash (complex2, brief item 1c): reproduce the
   svg_geom.parse_transform raise; where do rotates occur and what do
   they carry; do a rotate-capable parse + corner-mapped
   Affine.apply_rect suffice for a full complex2 load (brief: 42,530
   elements, 20 pages, 20 system-overflow warnings)?
D. mRest ledger-dash failure (complex1, brief item 2): reproduce the
   _attribute_ledger_dashes raise at page 3 m13 staff 8; confirm the
   dash's owner is the displaced whole-bar rest (mRest, id m16om1hq)
   and that an mRest tier in the candidate pool fixes it.
E. The join gap (complex1, brief item 3): with A+D shimmed, complex1
   loads fully (brief: 3490 elements, 3 pages, 3 dropped-spanner
   warnings) but join_notes matches 899/921 with 22 unmatched per
   side pairing 1:1 on grace notes. join.py ALREADY has a grace tier
   that excludes onset — so WHY do these graces miss? Print both
   sides' keys and grace flags to pin the real mechanism (the fix
   itself is Phase 12.1; Phase 11 only pins the gap).

Run: .venv/bin/python spikes/complex1_triage.py
"""

import sys
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import verovio                                                # noqa: E402

from scoreanim.core.engraving import verovio_adapter          # noqa: E402
from scoreanim.core.engraving.svg_geom import parse_transform  # noqa: E402
from scoreanim.core.engraving.types import (                  # noqa: E402
    Affine, EngravingParams, Rect)
from scoreanim.core.engraving.verovio_adapter import (        # noqa: E402
    _CONTAINER_CLASSES, _KIND_BY_CLASS, VerovioEngravingProvider)
from scoreanim.core.score.identity import Beats, ElementKind  # noqa: E402
from scoreanim.core.score.join import (                       # noqa: E402
    _align_voices, _note_key, _pitch_key, join_notes)
from scoreanim.core.score.model import build_score_model      # noqa: E402
from scoreanim.core.score.musicxml_prep import prepare        # noqa: E402

COMPLEX1 = ROOT / "testdata" / "complex1.musicxml"
COMPLEX2 = ROOT / "testdata" / "complex2.musicxml"

_SVG_NS = "{http://www.w3.org/2000/svg}"
_MEI_NS = "{http://www.music-encoding.org/ns/mei}"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
_DRAWABLE = {"use", "path", "rect", "line", "polygon", "polyline",
             "ellipse", "circle", "text"}

DISCREPANCIES: list[str] = []


def check(fact: str, ok: bool) -> None:
    """Brief-verification: loud but non-fatal, collected for the plan."""
    print(f"  {'PASS ' if ok else 'DIFFERS FROM BRIEF '}- {fact}")
    if not ok:
        DISCREPANCIES.append(fact)


def tag_of(el: ET.Element) -> str:
    return el.tag.split("}")[-1]


def first_cls(el: ET.Element) -> str:
    tokens = (el.get("class") or "").split()
    return tokens[0] if tokens else ""


# ---------------------------------------------------------------------------
# Raw renders (Verovio toolkit with the production adapter options; no
# decomposer, so census/anatomy work even where the decomposer crashes).
# Cached: complex2 takes ~20 s per engrave.
# ---------------------------------------------------------------------------

_RENDER_CACHE: dict[Path, tuple] = {}


def render(score: Path):
    """Return (prep, page ET roots, parent maps, mei string)."""
    if score in _RENDER_CACHE:
        return _RENDER_CACHE[score]
    prep = prepare(score)
    tk = verovio.toolkit()
    tk.setOptions({
        "breaks": "encoded", "font": "Bravura",
        "pageWidth": round(prep.page_width),
        "pageHeight": round(prep.page_height),
        "scaleToPageSize": True,
        "header": "none", "footer": "encoded",
        "svgHtml5": False, "svgViewBox": True,
        "transposeToSoundingPitch": True,
        "xmlIdSeed": 42,
        "condense": "encoded", "systemDivider": "none",
    })
    if not tk.loadData(prep.canonical_xml):
        raise SystemExit(f"Verovio failed to load {score.name}")
    pages = [ET.fromstring(tk.renderToSVG(p))
             for p in range(1, tk.getPageCount() + 1)]
    parents = [{child: parent for parent in page.iter() for child in parent}
               for page in pages]
    _RENDER_CACHE[score] = (prep, pages, parents, tk.getMEI())
    return _RENDER_CACHE[score]


def ancestry(el: ET.Element, parent_map: dict) -> list[ET.Element]:
    chain = []
    node = el
    while node in parent_map:
        node = parent_map[node]
        chain.append(node)
    return chain


def class_chain(el: ET.Element, parent_map: dict) -> str:
    names = [first_cls(a) for a in ancestry(el, parent_map) if first_cls(a)]
    return " < ".join(names[:6])


def orphan_drawables_if_container(g: ET.Element) -> int:
    """If g's class were treated as a transparent container, how many of
    its descendant drawables would reach the walk with NO emitting owner
    (id-bearing known class, or ledgerLines) between them and g?"""
    parent_map = {child: parent for parent in g.iter() for child in parent}
    orphans = 0
    for el in g.iter():
        if el is g or tag_of(el) not in _DRAWABLE:
            continue
        node, owned = el, False
        while node in parent_map and node is not g:
            node = parent_map[node]
            cls = first_cls(node)
            if (node.get(_XML_ID) or node.get("id")) and cls in _KIND_BY_CLASS:
                owned = True
                break
            if cls == "ledgerLines":
                owned = True
                break
        if not owned:
            orphans += 1
    return orphans


def census(score: Path):
    """class → (count, with_id, with_drawable_descendants, sample)."""
    _, pages, _, _ = render(score)
    counts, with_id, drawable = Counter(), Counter(), Counter()
    samples: dict[str, ET.Element] = {}
    for page in pages:
        for g in page.iter():
            cls = first_cls(g)
            if not cls or tag_of(g) != "g":
                continue
            counts[cls] += 1
            if g.get(_XML_ID) or g.get("id"):
                with_id[cls] += 1
            if any(tag_of(e) in _DRAWABLE for e in g.iter() if e is not g):
                drawable[cls] += 1
            samples.setdefault(cls, g)
    return counts, with_id, drawable, samples


def known_classes() -> set[str]:
    # ledgerLines is handled by a dedicated _walk branch, not the maps
    return set(_KIND_BY_CLASS) | _CONTAINER_CLASSES | {"ledgerLines"}


# ---------------------------------------------------------------------------
# Shims (context managers over the production module — the brief's fixes,
# applied temporarily so each failure can be reproduced and then passed)
# ---------------------------------------------------------------------------

@contextmanager
def shim_trem():
    """Brief item 1: bTrem/fTrem as transparent containers (the id-bearing
    note children mint their own elements; section A verifies no direct
    drawables get orphaned)."""
    added = {"bTrem", "fTrem"} - _CONTAINER_CLASSES
    _CONTAINER_CLASSES.update(added)
    try:
        yield
    finally:
        _CONTAINER_CLASSES.difference_update(added)


@contextmanager
def shim_beamspan():
    """Brief item 1b: beamSpan mapped to the beam kind."""
    _KIND_BY_CLASS["beamSpan"] = ElementKind.BEAM
    try:
        yield
    finally:
        _KIND_BY_CLASS.pop("beamSpan", None)


def _parse_transform_with_rotate(value: str | None) -> Affine:
    """Copy of svg_geom.parse_transform plus rotate(a[, cx, cy]) — the
    brief's 1c fix direction: rotate goes INTO the matrix (Affine already
    stores the full 2x3), and rotating matrices are no longer an error."""
    import math
    import re
    tf_re = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")
    num_re = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
    result = Affine()
    if not value:
        return result
    matches = list(tf_re.finditer(value))
    if not matches and value.strip():
        raise ValueError(f"unparseable transform: {value!r}")
    for m in matches:
        name = m.group(1)
        args = [float(x) for x in num_re.findall(m.group(2))]
        if name == "translate":
            step = Affine(e=args[0], f=args[1] if len(args) > 1 else 0.0)
        elif name == "scale":
            sx = args[0]
            step = Affine(a=sx, d=args[1] if len(args) > 1 else sx)
        elif name == "matrix" and len(args) == 6:
            step = Affine(*args)
        elif name == "rotate" and args:
            rad = math.radians(args[0])
            cos, sin = math.cos(rad), math.sin(rad)
            step = Affine(a=cos, b=sin, c=-sin, d=cos)
            if len(args) >= 3:
                cx, cy = args[1], args[2]
                step = Affine(e=cx, f=cy).compose(step).compose(
                    Affine(e=-cx, f=-cy))
        else:
            raise ValueError(f"unsupported transform {name!r} in {value!r}")
        result = result.compose(step)
    return result


def _apply_rect_corners(self: Affine, r: Rect) -> Rect:
    """Corner-mapped bbox: exact for 90-degree multiples, conservative
    otherwise (the brief's proposed apply_rect rewrite)."""
    pts = [self.apply(r.x, r.y), self.apply(r.x2, r.y),
           self.apply(r.x, r.y2), self.apply(r.x2, r.y2)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


@contextmanager
def shim_rotate():
    """Brief item 1c: rotate-capable transform parse + corner-mapped
    apply_rect, patched where the decomposer looks them up (the decompose
    stage module since the Phase R package split)."""
    from scoreanim.core.engraving.verovio import decompose
    orig_parse = decompose.parse_transform
    orig_apply = Affine.apply_rect
    decompose.parse_transform = _parse_transform_with_rotate
    Affine.apply_rect = _apply_rect_corners
    try:
        yield
    finally:
        decompose.parse_transform = orig_parse
        Affine.apply_rect = orig_apply


def _attribute_ledger_dashes_with_mrest(accumulators, st):
    """Copy of the production pass with mRest added to the rest tier —
    the brief's item-2 fix (same geometry rule; whole-bar rests displaced
    by a second voice sit on ledger dashes exactly like ordinary rests)."""
    notes_by_scope = defaultdict(list)
    rests_by_scope = defaultdict(list)
    for page, acc in accumulators:
        if acc.bbox is None:
            continue
        if acc.svg_class == "note":
            onset = st.onset_by_id.get(acc.verovio_id)
            mei_note = st.mei.notes.get(acc.verovio_id)
            if onset is None or mei_note is None:
                continue
            notes_by_scope[(page, acc.measure, acc.staff)].append(
                (acc.bbox, onset, mei_note.layer))
        elif acc.svg_class in ("rest", "mRest"):          # <-- mRest tier
            onset = st.onset_by_id.get(acc.verovio_id)
            if onset is None:
                continue
            rests_by_scope[(page, acc.measure, acc.staff)].append(
                (acc.bbox, onset, acc.layer if acc.layer is not None else 0))

    def matching(pool, dash):
        dash_cy = dash.bbox.y + dash.bbox.h / 2
        out = []
        for bbox, onset, layer in pool:
            if (bbox.x + bbox.w <= dash.bbox.x
                    or dash.bbox.x + dash.bbox.w <= bbox.x):
                continue
            owner_cy = bbox.y + bbox.h / 2
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


@contextmanager
def shim_mrest_ledger():
    # patched where the pipeline looks the pass up (the attribution stage
    # module since the Phase R package split)
    from scoreanim.core.engraving.verovio import attribution
    orig = attribution._attribute_ledger_dashes
    attribution._attribute_ledger_dashes = \
        _attribute_ledger_dashes_with_mrest
    try:
        yield
    finally:
        attribution._attribute_ledger_dashes = orig


def try_load(score: Path, *shims):
    """One load_detailed attempt under the given shim factories; returns
    (EngravedScore | None, exception | None)."""
    provider = VerovioEngravingProvider()
    from contextlib import ExitStack
    with ExitStack() as stack:
        for s in shims:
            stack.enter_context(s())
        try:
            return provider.load_detailed(score, EngravingParams()), None
        except Exception as e:                       # noqa: BLE001 — spike
            return None, e


# ---------------------------------------------------------------------------
# A. bTrem (complex1)
# ---------------------------------------------------------------------------

def section_a():
    print("== A. bTrem unknown class (complex1) ==")
    fixed = "bTrem" in _KIND_BY_CLASS or "bTrem" in _CONTAINER_CLASSES
    _, err = try_load(COMPLEX1)
    if fixed or err is None or "bTrem" not in str(err):
        print(f"  plain load: no longer raises on bTrem (fixed); "
              f"remaining: {err}")
    else:
        print(f"  plain load: {type(err).__name__}: {err}")
        check("complex1 plain load raises on unknown class 'bTrem'", True)
        check("the bTrem raise is on page 2", "page 2" in str(err))

    counts, with_id, drawable, samples = census(COMPLEX1)
    novel = sorted(c for c in counts if c not in known_classes())
    print(f"  complex1 novel classes: {novel}")
    if not fixed:
        check("bTrem is complex1's ONLY novel SVG class", novel == ["bTrem"])
    check("complex1 has no fTrem", "fTrem" not in counts)

    if "bTrem" in samples:
        g = samples["bTrem"]
        kids = Counter(f"{tag_of(e)}.{first_cls(e)}" for e in g)
        orphans = orphan_drawables_if_container(g)
        print(f"  bTrem x{counts['bTrem']}, with_id={with_id['bTrem']}, "
              f"direct children={dict(kids)}")
        for child in g:
            if tag_of(child) == "use":
                href = (child.get("{http://www.w3.org/1999/xlink}href")
                        or child.get("href") or "")
                print(f"    direct <use> glyph: {href} "
                      f"(SMuFL E22x = tremolo slashes)")
        print(f"  drawables NOT owned by an id-bearing known class inside "
              f"bTrem: {orphans}")
        # The brief said "container was sufficient". Structurally it is
        # NOT clean: the stroke <use> is a DIRECT child of bTrem, so a
        # container treatment hands it to the enclosing accumulator — the
        # id-bearing staff group — i.e. the stroke silently folds into
        # the static STAFF_LINES scaffold (the BACKLOG-6 ledger bug
        # shape). It loads, but 11.1 must make bTrem an EMITTING kind.
        check("brief's container story is structurally clean "
              "(no direct stroke ink)", orphans == 0)
        # Ruling (a) input: where does the stroke ink live?
        strokes = []
        pm = {c: p for p in g.iter() for c in p}
        for el in g.iter():
            if tag_of(el) in _DRAWABLE:
                strokes.append(class_chain(el, pm) or "(direct)")
        print("  ruling (a) input — tremolo subtree drawables live under: "
              f"{dict(Counter(strokes))}")

    # With the container shim, the load gets PAST bTrem (next stop is
    # the item-2 ledger failure) — reproducing the brief's shim result.
    eng, err = try_load(COMPLEX1, shim_trem)
    print(f"  with trem shim: {type(err).__name__ if err else 'loads'}"
          f"{': ' + str(err) if err else ''}")
    check("container shim clears bTrem (no class-guard raise)",
          err is None or "unknown SVG class" not in str(err))

    # Demonstrate the misattribution under the container shim: some
    # STAFF_LINES element gains a 6th primitive (5 staff lines + stroke).
    probe, _ = try_load(COMPLEX1, shim_trem, shim_mrest_ledger)
    if probe is not None:
        fat = [e for e in probe.layout.elements
               if e.identity.kind is ElementKind.STAFF_LINES
               and len(e.glyph.paths) > 5]
        for e in fat:
            print(f"  container-shim misattribution: {e.identity.element_id} "
                  f"has {len(e.glyph.paths)} primitives (stroke folded into "
                  f"the static staff scaffold)")
        check("container shim folds the tremolo stroke into STAFF_LINES "
              "(so the REAL fix must emit bTrem)", len(fat) == 1)
    print()
    return err                 # handed to section D (the ledger failure)


# ---------------------------------------------------------------------------
# B. beamSpan (complex2)
# ---------------------------------------------------------------------------

def section_b():
    print("== B. beamSpan unknown class (complex2) ==")
    counts, with_id, drawable, samples = census(COMPLEX2)
    novel = sorted(c for c in counts if c not in known_classes())
    print(f"  complex2 novel classes: {novel}")
    for c in novel:
        print(f"    {c}: x{counts[c]}, with_id={with_id[c]}, "
              f"with-drawables={drawable[c]}, orphans-if-container="
              f"{orphan_drawables_if_container(samples[c])}")
    if "beamSpan" not in _KIND_BY_CLASS:
        check("complex2's novel classes are exactly {bTrem, beamSpan}",
              novel == ["bTrem", "beamSpan"])
    # The brief promised an fTrem twin ("complex2 has 85 tremolos") —
    # in fact ALL 85 tremolos render as bTrem; fTrem never occurs in
    # either file, so fTrem coverage is defensive-only (synthetic test).
    check("brief's fTrem twin actually occurs in complex2",
          "fTrem" in counts)
    check("complex2's 85 tremolos are all bTrem", counts["bTrem"] == 85)

    if "beamSpan" in samples:
        g = samples["beamSpan"]
        kids = Counter(f"{tag_of(e)}.{first_cls(e)}" for e in g)
        print(f"  beamSpan sample: id={bool(g.get(_XML_ID) or g.get('id'))}, "
              f"direct children={dict(kids)}")
    # Which onset table could serve a BEAM-kind beamSpan? The layer-beam
    # table is built from MEI <beam> inside layers; beamSpan is a
    # measure-level spanner with @startid/@endid/@plist.
    _, _, _, mei = render(COMPLEX2)
    root = ET.fromstring(mei)
    spans = list(root.iter(f"{_MEI_NS}beamSpan"))
    attrs = Counter(a for sp in spans for a in sp.keys()
                    if a in ("startid", "endid", "plist", "staff"))
    print(f"  MEI beamSpan count={len(spans)}, attrs={dict(attrs)}")
    check("MEI beamSpan carries startid/endid (an extent source exists, "
          "but NOT via the layer-beam table)",
          bool(spans) and attrs.get("startid", 0) == len(spans)
          and attrs.get("endid", 0) == len(spans))

    _, err = try_load(COMPLEX2, shim_trem, shim_mrest_ledger)
    first_failure = str(err) if err else ""
    if err is None or ("beamSpan" not in first_failure
                       and "rotate" not in first_failure):
        print(f"  load with trem+mrest shims: beamSpan/rotate no longer "
              f"raise (fixed); remaining: {err}")
    else:
        print(f"  load with trem+mrest shims: {type(err).__name__}: {err}")
        check("with tremolos shimmed, complex2 fails on beamSpan or "
              "rotate (the 1b/1c pair)", True)
        if "beamSpan" not in first_failure:
            # rotate came first in walk order — reproduce beamSpan behind it
            _, err2 = try_load(COMPLEX2, shim_trem, shim_mrest_ledger,
                               shim_rotate)
            print(f"  ... and with rotate also shimmed: "
                  f"{type(err2).__name__ if err2 else 'no raise'}: {err2}")
            check("beamSpan raise reproduced once rotate is shimmed",
                  err2 is not None and "beamSpan" in str(err2))
    print()


# ---------------------------------------------------------------------------
# C. rotate transforms (complex2)
# ---------------------------------------------------------------------------

def section_c():
    print("== C. rotate transform crash (complex2) ==")
    _, pages, parents, _ = render(COMPLEX2)
    hits = []
    for page_n, (page, pm) in enumerate(zip(pages, parents), start=1):
        for el in page.iter():
            tf = el.get("transform") or ""
            if "rotate" in tf:
                hits.append((page_n, tag_of(el), class_chain(el, pm), tf))
    print(f"  rotate transforms in the SVG: {len(hits)}")
    for page_n, tag, chain, tf in hits[:6]:
        print(f"    page {page_n}: <{tag}> {tf!r} under [{chain}]")
    check("rotate transforms exist (the 'Verovio never rotates' docstring "
          "assumption is disproved)", bool(hits))
    # Brief located the rotate on "page 5"; in the raw encoded-breaks
    # render they sit on pages 8 and 16 (the brief likely quoted a page
    # under a different pagination). The load-order fact that matters:
    # beamSpan (page 5) raises BEFORE the first rotate.
    check("rotates are all -90 (exact corner mapping applies)",
          bool(hits) and all("-90" in tf for _, _, _, tf in hits))

    print("  parse_transform on the real value:")
    sample = hits[0][3] if hits else "rotate(-90) "
    try:
        parse_transform(sample)
        print("    no longer raises (fixed)")
    except ValueError as e:
        print(f"    reproduced: ValueError: {e}")
        check("parse_transform raises on rotate", True)

    # 90-degree sanity of the shim math before trusting a full load
    a = _parse_transform_with_rotate("rotate(-90)")
    r = _apply_rect_corners(a, Rect(0, 0, 10, 2))
    check("corner-mapped apply_rect maps a 10x2 rect under rotate(-90) "
          "to 2x10", (round(r.w, 6), round(r.h, 6)) == (2.0, 10.0))

    print("  full complex2 load under all four shims (brief: 42,530 "
          "elements, 20 pages, 20x system-overflow, 6x dropped-spanner, "
          "1x repaginated; ~20 s+)...")
    eng, err = try_load(COMPLEX2, shim_trem, shim_beamspan, shim_rotate,
                        shim_mrest_ledger)
    if err is not None:
        print(f"  FULL LOAD STILL FAILS: {type(err).__name__}: {err}")
        check("complex2 loads end-to-end under the four shims", False)
    else:
        wc = Counter(w.code for w in eng.warnings)
        print(f"  loaded: {len(eng.layout.elements)} elements, "
              f"{len(eng.layout.pages)} pages, warnings={dict(wc)}")
        check("complex2 loads end-to-end under the four shims", True)
        check("complex2: 20 pages", len(eng.layout.pages) == 20)
        check("complex2: ~42,530 elements",
              abs(len(eng.layout.elements) - 42530) < 200)
        check("complex2: every system overflows (20x system-overflow)",
              wc.get("system-overflow", 0) == 20)
        check("complex2: 6x dropped-spanner, 1x repaginated",
              wc.get("dropped-spanner") == 6 and wc.get("repaginated") == 1)
        spans = [e for e in eng.layout.elements
                 if e.identity.kind is ElementKind.BEAM]
        span_onsets = sum(1 for e in spans if e.identity.onset is not None)
        print(f"  BEAM-kind elements: {len(spans)}, with onset: "
              f"{span_onsets} (beamSpan ids are NOT in the layer-beam "
              f"table — 11.1 must decide their onset path)")
    print()


# ---------------------------------------------------------------------------
# D. mRest ledger dash (complex1)
# ---------------------------------------------------------------------------

def section_d(ledger_err):
    print("== D. mRest ledger-dash failure (complex1 p3 m13 staff 8) ==")
    msg = str(ledger_err or "")
    if ledger_err is None:
        print("  no longer raises (fixed)")
    else:
        print(f"  failure behind the trem shim (from section A): "
              f"{ledger_err}")
        check("it is the ledger-attribution raise",
              "ledger dash" in msg and "matches no notehead or rest" in msg)
        check("at page 3 m13 staff 8", "page 3 m13 staff 8" in msg)
        check("at x=1277 (the brief's dash)", "x=1277" in msg)

    # Whose ink is at that x? The brief says mRest m16om1hq — a whole-bar
    # rest displaced above the staff by a second voice.
    _, pages, parents, mei = render(COMPLEX1)
    root = ET.fromstring(mei)
    m13 = next((m for m in root.iter(f"{_MEI_NS}measure")
                if m.get("n") == "13"), None)
    mrest_ids = []
    if m13 is not None:
        for staff in m13.findall(f"{_MEI_NS}staff"):
            if staff.get("n") == "8":
                layers = staff.findall(f"{_MEI_NS}layer")
                print(f"  MEI m13 staff 8: {len(layers)} layers")
                for ly in layers:
                    for mr in ly.iter(f"{_MEI_NS}mRest"):
                        mrest_ids.append(mr.get(_XML_ID))
                        print(f"    layer n={ly.get('n')}: mRest "
                              f"id={mr.get(_XML_ID)}")
    check("m13 staff 8 is two-voice with an mRest (brief: id m16om1hq)",
          "m16om1hq" in mrest_ids)

    eng, err = try_load(COMPLEX1, shim_trem, shim_mrest_ledger)
    print(f"  with mRest tier: {type(err).__name__ if err else 'loads'}"
          f"{': ' + str(err) if err else ''}")
    check("the mRest tier clears the ledger failure (complex1 loads)",
          err is None)
    if eng is not None:
        dash = [e for e in eng.layout.elements
                if e.identity.kind is ElementKind.LEDGER_LINES
                and e.page == 3 and abs(e.bbox.x - 1277) < 3]
        for d in dash:
            print(f"  the dash as loaded: onset={d.identity.onset} "
                  f"voice={d.identity.voice} (inherited from the mRest)")
        check("the p3 dash now carries the mRest's onset",
              bool(dash) and all(d.identity.onset is not None for d in dash))
    print()
    return eng


# ---------------------------------------------------------------------------
# E. Full complex1 census + the join gap
# ---------------------------------------------------------------------------

def section_e(eng):
    print("== E. complex1 census + join gap (899/921) ==")
    if eng is None:
        print("  SKIPPED: complex1 did not load under the shims")
        DISCREPANCIES.append("section E skipped — no loaded complex1")
        return
    wc = Counter(w.code for w in eng.warnings)
    print(f"  loaded: {len(eng.layout.elements)} elements, "
          f"{len(eng.layout.pages)} pages, warnings={dict(wc)}")
    check("complex1: 3490 elements", len(eng.layout.elements) == 3490)
    check("complex1: 3 pages", len(eng.layout.pages) == 3)
    check("complex1: exactly 3 dropped-spanner warnings, nothing else",
          dict(wc) == {"dropped-spanner": 3})

    src = ET.parse(COMPLEX1).getroot()
    n_grace_src = sum(1 for _ in src.iter("grace"))
    print(f"  source <grace> notes: {n_grace_src}")
    check("source has 26 <grace> notes", n_grace_src == 26)

    model = build_score_model(COMPLEX1)
    report = join_notes(model, eng.note_records)
    n_s, n_l = len(model.notes), len(eng.note_records)
    print(f"  join: {len(report.matched)} matched of score={n_s} / "
          f"layout={n_l}; unmatched score={len(report.unmatched_score)} "
          f"layout={len(report.unmatched_layout)}")
    check("join is 899/921", len(report.matched) == 899 and n_s == 921)
    check("22 unmatched on each side",
          len(report.unmatched_score) == 22
          and len(report.unmatched_layout) == 22)

    # Pin the mechanism. join.py ALREADY keys graces as
    # ("grace", pitch) with onset excluded — if the brief's onset story
    # were the whole truth, these would match. Print both sides' actual
    # keys and grace flags.
    print("  unmatched pairs (sorted by part/measure):")
    s_un = sorted(report.unmatched_score,
                  key=lambda n: (str(n.part), n.measure, n.order))
    l_un = sorted(report.unmatched_layout,
                  key=lambda r: (str(r.part), r.measure, r.order_in_voice))
    graces_s = sum(1 for n in s_un if n.grace)
    graces_l = sum(1 for r in l_un if r.grace)
    pair_keys = Counter()
    for n in s_un:
        pair_keys[(str(n.part), n.measure,
                   n.pitch_step, n.octave)] += 1
    for r in l_un:
        pair_keys[(str(r.part), r.measure,
                   r.pitch_step, r.octave)] -= 1
    paired_1to1 = all(v == 0 for v in pair_keys.values())
    for n, r in zip(s_un, l_un):
        sk = _note_key(n.grace, n.onset,
                       _pitch_key(n.pitch_step, n.octave, n.staff_loc))
        lk = _note_key(r.grace, r.onset,
                       _pitch_key(r.pitch_step, r.octave, r.staff_loc))
        print(f"    score  {str(n.part):4s} m{n.measure:<3d} "
              f"v={n.voice_label!s:4s} onset={n.onset:<9.4f} "
              f"grace={n.grace!s:5s} {n.pitch_step}{n.octave} key={sk}")
        print(f"    layout {str(r.part):4s} m{r.measure:<3d} "
              f"v={r.voice:<4d} onset={r.onset:<9.4f} "
              f"grace={r.grace!s:5s} {r.pitch_step}{r.octave} key={lk} "
              f"[{r.element_id}]")
    print(f"  grace flags: score-side {graces_s}/22, layout-side "
          f"{graces_l}/22")
    check("unmatched pair 1:1 by (part, measure, pitch)",
          paired_1to1 and len(s_un) == len(l_un))
    # The brief said the unmatched ARE grace notes (fractional grace
    # qstamp vs integer beat). Mechanism as found: the unmatched are the
    # PRINCIPAL notes carrying the graces — Verovio's timemap DELAYS the
    # principal by the grace duration (+0.0957 q ≈ 98/1024) while
    # music21 keeps the notated beat; both sides flag grace=False, so
    # the exact-onset key misses. The graces themselves all match via
    # join.py's existing grace tier (onset-excluded). Same appoggiatura
    # semantics as complex2's 1882/9546 collapse, at acciaccatura scale
    # — one order-based rewrite (Phase 12.1) covers both.
    check("brief's mechanism (unmatched = the grace notes themselves)",
          graces_s == 22)
    deltas = {round(r.onset - n.onset, 4) for n, r in zip(s_un, l_un)}
    print(f"  onset deltas (layout - score) across pairs: {deltas}")
    check("all unmatched principals delayed by one grace step (+0.0957)",
          deltas == {0.0957})
    n_grace_model = sum(1 for n in model.notes if n.grace)
    matched_graces = sum(1 for _, n in report.matched if n.grace)
    print(f"  model grace notes: {n_grace_model}, matched: "
          f"{matched_graces}")
    check("every grace note itself matches (the grace tier works)",
          n_grace_model == matched_graces)

    # Was any unmatched group dumped by voice-alignment failure instead?
    scopes = {(str(n.part), n.measure, n.staff) for n in s_un}
    align_failures = []
    s_groups, l_groups = defaultdict(list), defaultdict(list)
    for n in model.notes:
        s_groups[(str(n.part), n.measure, n.staff)].append(n)
    for r in eng.note_records:
        l_groups[(str(r.part), r.measure, r.staff)].append(r)
    for scope in sorted(scopes):
        s_labels = list(dict.fromkeys(
            n.voice_label for n in s_groups[scope]))
        l_voices = sorted({r.voice for r in l_groups[scope]})
        vm = _align_voices(
            sorted(s_labels, key=lambda x: (x is None, x)), l_voices)
        if vm is None:
            align_failures.append(scope)
    print(f"  scopes with unmatched notes: {len(scopes)}; "
          f"voice-alignment failures among them: {align_failures or 'none'}")
    print()


def main() -> None:
    for f in (COMPLEX1, COMPLEX2):
        if not f.exists():
            raise SystemExit(f"missing fixture: {f}")
    ledger_err = section_a()
    section_b()
    section_c()
    eng = section_d(ledger_err)
    section_e(eng)
    print("== Summary ==")
    if DISCREPANCIES:
        print(f"  {len(DISCREPANCIES)} finding(s) DIFFER from the brief:")
        for d in DISCREPANCIES:
            print(f"    - {d}")
    else:
        print("  brief fully confirmed — no discrepancies")
    print("triage complete")


if __name__ == "__main__":
    main()
