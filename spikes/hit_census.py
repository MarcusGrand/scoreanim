"""M2.0 hit census — what does scene.items(pos) actually return?

The M2 brief's §1 audit predicts two things this spike must confirm
before any selection code is written:

A. SHAPE POLLUTION. Qt's default QGraphicsItem.shape() returns
   boundingRect() as a path, and GroupItem.boundingRect() is
   childrenBoundingRect() — so every ElementItem PARENT answers a hit
   anywhere in its children's united bbox. A STAFF_LINES element spans
   its whole system, so without an override it should appear in the
   candidate list of every click on the page. With shape() returning an
   empty QPainterPath, parents go hit-transparent and hits come only
   from real ink children (QGraphicsPathItem.shape() includes the pen
   stroke, so thin stems/staff lines stay clickable via their child).

B. BBOX vs INK. ElementItem.bbox (the engraving-authored rect) is dead
   storage today — written in scene.py, read nowhere. M2 is its first
   consumer, for both hit-priority area and the highlight overlay, so
   this spike measures it against childrenBoundingRect() (the actual
   Qt path bounds) to see whether the authored rect can be trusted.

It also calibrates the click tolerance: a bare point-hit on a thin
glyph is fragile, so we probe with a small rect (~3 view px mapped to
scene units) and compare.

Run: .venv/bin/python spikes/hit_census.py
"""

import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF  # noqa: E402
from PySide6.QtGui import QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.engraving.types import EngravingParams  # noqa: E402
from scoreanim.core.engraving.verovio import \
    VerovioEngravingProvider  # noqa: E402
from scoreanim.core.project.document import StageConfig  # noqa: E402
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.render.items import ElementItem, GroupItem  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402

TESTSCORE = ROOT / "testdata" / "testscore.musicxml"
COMPLEX3 = ROOT / "testdata" / "complex3.musicxml"

# The kinds the M2 exit criteria name, plus the scaffold that pollutes.
PROBE_KINDS = (ElementKind.NOTEHEAD, ElementKind.SLUR, ElementKind.HAIRPIN,
               ElementKind.BARLINE, ElementKind.STAFF_LINES,
               ElementKind.TEXT)

# ~3 view px at fit zoom, in page units (1/10 mm). Page ~2000 units wide
# shown in ~1000 px => ~2 units/px, so 3 px ~ 6 units.
TOL = 6.0


class ShapedElementItem(ElementItem):
    """The M2.3 candidate fix, as a real subclass.

    NOTE (spike finding): monkeypatching ``GroupItem.shape`` after the
    class exists does NOTHING — PySide6 decides which C++ virtuals to
    route into Python when the type is created, so a post-hoc attribute
    assignment is never called. The override has to be declared in the
    class body, which is how M2.3 will ship it."""

    def shape(self):  # noqa: N802 (Qt naming)
        return QPainterPath()


def candidates(scene, pos: QPointF, tol: float):
    """What the SelectionController would see: every hit item walked up
    to its ElementItem ancestor, deduped by element id."""
    area = QRectF(pos.x() - tol, pos.y() - tol, 2 * tol, 2 * tol) \
        if tol else None
    hits = scene.items(area) if area is not None else scene.items(pos)
    out = []
    seen = set()
    for hit in hits:
        node = hit
        while node is not None and not isinstance(node, ElementItem):
            node = node.parentItem()
        if node is None or node.identity is None:
            continue
        eid = node.identity.element_id
        if eid in seen:
            continue
        seen.add(eid)
        out.append(node)
    return out


def _area(rect: QRectF) -> float:
    return rect.width() * rect.height()


def ink_point(item: ElementItem) -> QPointF:
    """A point genuinely ON the element's ink.

    A bbox CENTRE is the wrong probe for anything curved or hollow: a
    slur's centre is the empty air under its arc, and a system barline's
    centre falls in the gap between two staves. Once parents are
    hit-transparent, only real ink answers — so the census has to click
    where a user would, i.e. on the stroke itself. Midpoint of the
    element's longest path child."""
    best = None
    for child in item.childItems():
        if not hasattr(child, "path"):
            continue
        path = child.path()
        if path.isEmpty():
            continue
        length = path.length()
        if best is None or length > best[0]:
            best = (length, child, path)
    if best is None:
        return item.bbox.center() if item.bbox is not None else QPointF()
    _, child, path = best
    return child.mapToScene(path.pointAtPercent(0.5))


def describe(item: ElementItem) -> str:
    bbox_a = _area(item.bbox) if item.bbox is not None else -1.0
    ink_a = _area(item.childrenBoundingRect())
    return (f"{item.identity.kind.name:<12} bbox={bbox_a:9.1f} "
            f"ink={ink_a:9.1f}  {item.identity.element_id}")


def build(layout, shaped: bool) -> ScoreScenes:
    """Build scenes with either the stock ElementItem or the shaped one,
    by swapping the name scene.py resolves at construction time."""
    import scoreanim.render.scene as scene_mod
    original = scene_mod.ElementItem
    scene_mod.ElementItem = ShapedElementItem if shaped else original
    try:
        return ScoreScenes(layout, StageConfig())
    finally:
        scene_mod.ElementItem = original


def probe_score(path: Path, label: str) -> None:
    print(f"\n{'=' * 72}\n{label}  ({path.name})\n{'=' * 72}")
    engraved = VerovioEngravingProvider().load_detailed(
        path, EngravingParams(), strict=False)
    layout = engraved.layout

    # -- B. bbox vs ink, over EVERY element ---------------------------
    scenes = build(layout, shaped=False)
    print(f"\n-- B. authored bbox vs actual ink "
          f"({len(layout.elements)} elements) --")
    worst = []
    for el in layout.elements:
        item = scenes.items[el.identity.element_id]
        if item.bbox is None:
            continue
        ink = item.childrenBoundingRect()
        if ink.isEmpty() or item.bbox.isEmpty():
            continue
        ratio = _area(ink) / _area(item.bbox)     # relative disagreement
        worst.append((abs(ratio - 1.0), ratio, el.identity))
    worst.sort(key=lambda w: w[0], reverse=True)
    print(f"   median |ratio-1| = "
          f"{sorted(w[0] for w in worst)[len(worst) // 2]:.4f}")
    print("   5 worst disagreements (ink_area / bbox_area):")
    for _, ratio, ident in worst[:5]:
        print(f"     {ratio:8.3f}x  {ident.kind.name:<12} "
              f"{ident.element_id}")

    # -- A. shape pollution -------------------------------------------
    # One representative element per probe kind, from anywhere in the
    # score (a hairpin may not be on page 1).
    targets = {}
    for kind in PROBE_KINDS:
        el = next((e for e in layout.elements
                   if e.identity.kind is kind), None)
        if el is not None:
            targets[kind] = el

    for shaped in (False, True):
        built = scenes if not shaped else build(layout, shaped=True)
        tag = ("WITH shape() override" if shaped
               else "WITHOUT override (stock Qt)")
        for tol in (0.0, TOL, 3 * TOL):
            print(f"\n-- A. candidates, tol={tol:g}, {tag} --")
            for kind, target in targets.items():
                item = built.items[target.identity.element_id]
                scene = built.scene_for_page(target.page)
                found = candidates(scene, ink_point(item), tol)
                kinds = Counter(c.identity.kind.name for c in found)
                hit = any(c.identity.element_id
                          == target.identity.element_id for c in found)
                print(f"   probe {kind.name:<12} p{target.page} "
                      f"n={len(found):<3} target_present={hit}  "
                      f"{dict(kinds)}")
                for cand in sorted(
                        found,
                        key=lambda c: _area(c.bbox) if c.bbox else 0.0)[:4]:
                    print(f"        {describe(cand)}")


def probe_exactness(path: Path, label: str) -> None:
    """C. The stem trap.

    A stem's authored Rect has w=0, so its AREA IS 0 — under a plain
    'smallest area wins' rule a stem beats the notehead it belongs to,
    and clicking a notehead would select its stem. This measures the
    fix: split candidates into those whose ink actually CONTAINS the
    click (exact) and those merely within the tolerance rect, and rank
    exact first."""
    print(f"\n{'=' * 72}\nC. exact-vs-tolerance   {label}\n{'=' * 72}")
    engraved = VerovioEngravingProvider().load_detailed(
        path, EngravingParams(), strict=False)
    layout = engraved.layout
    built = build(layout, shaped=True)

    probes = (ElementKind.NOTEHEAD, ElementKind.BARLINE, ElementKind.SLUR,
              ElementKind.HAIRPIN, ElementKind.STAFF_LINES)
    for kind in probes:
      for where in ("bbox centre", "on ink"):
        target = next((e for e in layout.elements
                       if e.identity.kind is kind), None)
        if target is None:
            continue
        item = built.items[target.identity.element_id]
        scene = built.scene_for_page(target.page)
        pos = item.bbox.center() if where == "bbox centre" \
            else ink_point(item)
        found = candidates(scene, pos, TOL)
        print(f"\n   click at {kind.name} {where}, tol={TOL:g} "
              f"-> {len(found)} candidates")
        if not found:
            print("      (nothing)")
            continue
        rows = []
        for cand in found:
            exact = any(
                child.isVisible()
                and child.shape().contains(child.mapFromScene(pos))
                for child in cand.childItems()
                if hasattr(child, "shape"))
            rows.append((not exact, _area(cand.bbox) if cand.bbox else 0.0,
                         str(cand.identity.element_id), cand, exact))
        for inexact, area, eid, cand, exact in sorted(rows,
                                                      key=lambda r: r[:3]):
            print(f"      exact={str(exact):<5} area={area:9.1f}  "
                  f"{cand.identity.kind.name:<12} {eid}")
        winner_area_only = min(
            rows, key=lambda r: (r[1], r[2]))
        winner_tiered = min(rows, key=lambda r: r[:3])
        print(f"      area-only winner : "
              f"{winner_area_only[3].identity.kind.name}")
        print(f"      exact-first     : "
              f"{winner_tiered[3].identity.kind.name}")


def probe_ranking(path: Path, label: str) -> None:
    """D. Does a ranking rule actually return what the user clicked?

    For a sample of elements per kind, click at several points on that
    element's OWN ink and ask: did the rule pick it? Compares the
    brief's area-only rule against the tiered rule the earlier sections
    forced out:

        (not exact, tier, area, element_id)
        tier 0 animated ink | 1 scaffold | 2 STAFF_LINES (the backdrop)

    STAFF_LINES needs its own tier because it is exact ink under a huge
    part of the page and its bbox is SMALLER than a system barline's —
    so area alone hands every barline click to the staff."""
    print(f"\n{'=' * 72}\nD. ranking accuracy   {label}\n{'=' * 72}")
    engraved = VerovioEngravingProvider().load_detailed(
        path, EngravingParams(), strict=False)
    layout = engraved.layout
    built = build(layout, shaped=True)
    from scoreanim.core.animation.schedule import STATIC_KINDS

    def tier(kind) -> int:
        if kind is ElementKind.STAFF_LINES:
            return 2
        return 1 if kind in STATIC_KINDS else 0

    def rank(cand, pos, tiered: bool):
        exact = any(
            child.isVisible()
            and child.shape().contains(child.mapFromScene(pos))
            for child in cand.childItems() if hasattr(child, "shape"))
        area = _area(cand.bbox) if cand.bbox is not None else 0.0
        eid = str(cand.identity.element_id)
        if tiered:
            return (not exact, tier(cand.identity.kind), area, eid)
        return (area, cand.identity.kind in STATIC_KINDS, eid)

    print(f"   {'kind':<13}{'n':>5}{'area-only':>12}{'tiered':>10}")
    for kind in PROBE_KINDS:
        sample = [e for e in layout.elements if e.identity.kind is kind][:40]
        if not sample:
            continue
        tries = hits_area = hits_tier = 0
        for el in sample:
            item = built.items[el.identity.element_id]
            scene = built.scene_for_page(el.page)
            # ONE realistic click per element: the interior for a solid
            # glyph (notehead, text — a user aims at the middle), a
            # point on the stroke for thin/hollow ink (slur, hairpin,
            # barline, staff lines), whose bbox centre is empty air.
            points = []
            centre = item.bbox.center() if item.bbox is not None else None
            solid = centre is not None and any(
                child.isVisible()
                and child.shape().contains(child.mapFromScene(centre))
                for child in item.childItems() if hasattr(child, "shape"))
            if solid:
                points.append(centre)
            else:
                for child in item.childItems():
                    if not hasattr(child, "path") or child.path().isEmpty():
                        continue
                    for pct in (0.25, 0.5, 0.75):
                        points.append(child.mapToScene(
                            child.path().pointAtPercent(pct)))
                    break
            for pos in points:
                found = candidates(scene, pos, TOL)
                if not found:
                    continue
                tries += 1
                for tiered, counter in ((False, "area"), (True, "tier")):
                    win = min(found, key=lambda c: rank(c, pos, tiered))
                    ok = win.identity.element_id == el.identity.element_id
                    if ok and counter == "area":
                        hits_area += 1
                    elif ok and counter == "tier":
                        hits_tier += 1
        if tries:
            print(f"   {kind.name:<13}{tries:>5}"
                  f"{100 * hits_area / tries:>11.0f}%"
                  f"{100 * hits_tier / tries:>9.0f}%")


def probe_reachability(path: Path, label: str) -> None:
    """E. Is every element actually reachable by clicking it?

    Section D clicks ONE point per element, which for a hollow notehead
    is its centre — i.e. the hole, where the ledger dash or staff line
    genuinely is the ink under the cursor. That understates real usage:
    a user aiming at a note hits the ring, not the hole. This samples a
    3x3 grid inside each element's bbox and reports both the hit rate
    and whether the element is selectable AT ALL.

    CAVEAT: the grid is only meaningful for COMPACT elements. A system
    barline's bbox spans the inter-staff gaps, so most grid points sit
    in empty air and 'reachable' reads ~10% — an artifact of the metric,
    not of selection. Section D clicks barlines on their ink: 100%."""
    print(f"\n{'=' * 72}\nE. reachability (3x3 grid in bbox)   {label}\n"
          f"{'=' * 72}")
    engraved = VerovioEngravingProvider().load_detailed(
        path, EngravingParams(), strict=False)
    layout = engraved.layout
    built = build(layout, shaped=True)
    from scoreanim.core.animation.schedule import STATIC_KINDS

    def tier(kind) -> int:
        if kind is ElementKind.STAFF_LINES:
            return 2
        return 1 if kind in STATIC_KINDS else 0

    def rank(cand, pos):
        exact = any(
            child.isVisible()
            and child.shape().contains(child.mapFromScene(pos))
            for child in cand.childItems() if hasattr(child, "shape"))
        return (not exact, tier(cand.identity.kind),
                _area(cand.bbox) if cand.bbox is not None else 0.0,
                str(cand.identity.element_id))

    print(f"   {'kind':<13}{'elems':>7}{'click hit':>11}{'reachable':>11}")
    for kind in PROBE_KINDS:
        sample = [e for e in layout.elements if e.identity.kind is kind][:60]
        if not sample:
            continue
        pts = wins = reach = 0
        for el in sample:
            item = built.items[el.identity.element_id]
            if item.bbox is None or item.bbox.isEmpty():
                continue
            scene = built.scene_for_page(el.page)
            b = item.bbox
            any_win = False
            for fx in (0.3, 0.5, 0.7):
                for fy in (0.3, 0.5, 0.7):
                    pos = QPointF(b.x() + fx * b.width(),
                                  b.y() + fy * b.height())
                    found = candidates(scene, pos, TOL)
                    if not found:
                        continue
                    pts += 1
                    win = min(found, key=lambda c: rank(c, pos))
                    if win.identity.element_id == el.identity.element_id:
                        wins += 1
                        any_win = True
            reach += any_win
        if pts:
            print(f"   {kind.name:<13}{len(sample):>7}"
                  f"{100 * wins / pts:>10.0f}%"
                  f"{100 * reach / len(sample):>10.0f}%")


def main() -> None:
    QApplication.instance() or QApplication([])
    probe_score(TESTSCORE, "testscore")
    if COMPLEX3.exists():
        probe_score(COMPLEX3, "complex3")
    else:
        print("\ncomplex3.musicxml absent — skipped")
    probe_exactness(TESTSCORE, "testscore")
    if COMPLEX3.exists():
        probe_exactness(COMPLEX3, "complex3")
    probe_ranking(TESTSCORE, "testscore")
    if COMPLEX3.exists():
        probe_ranking(COMPLEX3, "complex3")
    probe_reachability(TESTSCORE, "testscore")
    if COMPLEX3.exists():
        probe_reachability(COMPLEX3, "complex3")


if __name__ == "__main__":
    main()
