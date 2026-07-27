"""M3.1 spike: does moving a reveal-clipped spanner break its clip?

The roadmap's M3 drag-to-nudge task says: "A reveal-clipped spanner
moved in x interacts with its clip edge — spike first, and if it
misbehaves, exclude REVEALED_KINDS from NUDGEABLE_KINDS in v1 and flag."

This measures it rather than reasoning about it. The mechanism under
suspicion is in `render/items.py`:

    def set_clip_right(self, scene_x):
        if self._inverse is None:
            inv, ok = self.sceneTransform().inverted()
            self._inverse = inv                 # <-- cached ONCE
        local_x = self._inverse.map(QPointF(scene_x, 0.0)).x()

`set_clip_right` takes a SCENE x (the reveal edge / playhead position)
and maps it into the path child's LOCAL coordinates through the inverse
of its scene transform — which it caches on first use. A nudge moves
the parent `ElementItem` via `setPos`, which changes every child's
sceneTransform. So the question is whether the cache goes stale, and by
how much, and whether re-pushing the edge repairs it.

Run: python spikes/nudge_reveal.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF                       # noqa: E402
from PySide6.QtWidgets import QApplication               # noqa: E402

from scoreanim.core.animation.reveal import REVEALED_KINDS   # noqa: E402
from scoreanim.core.engraving.types import EngravingParams   # noqa: E402
from scoreanim.core.engraving.verovio import (               # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.project import StageConfig                # noqa: E402
from scoreanim.render.scene import ScoreScenes                # noqa: E402

FIXTURE = Path(__file__).resolve().parent.parent / "testdata" / \
    "testscore.musicxml"


def _load() -> ScoreScenes:
    provider = VerovioEngravingProvider()
    layout = provider.load(FIXTURE, EngravingParams())
    return ScoreScenes(layout, StageConfig()), layout


def main() -> None:
    app = QApplication.instance() or QApplication([])
    scenes, layout = _load()

    # a spanner with real horizontal extent, mid-page
    target = None
    for el in layout.elements:
        if el.identity.kind not in REVEALED_KINDS:
            continue
        if el.bbox is not None and el.bbox.w > 40.0:
            target = el
            break
    if target is None:
        print("no wide revealed spanner in the fixture — spike inconclusive")
        return

    item = scenes.items[target.identity.element_id]
    eid = target.identity.element_id
    left = target.bbox.x
    right = target.bbox.x + target.bbox.w
    mid = left + target.bbox.w / 2.0
    print(f"target  {eid}")
    print(f"  kind={target.identity.kind.name} "
          f"x=[{left:.1f}, {right:.1f}] w={target.bbox.w:.1f}")
    child = item.reveal_children[0]

    def clip_scene_x() -> float:
        """Where the clip edge actually IS, back in scene coords — the
        honest readout, independent of what we asked for."""
        if child.clip_right is None:
            return float("inf")
        return child.sceneTransform().map(
            QPointF(child.clip_right, 0.0)).x()

    # -- 1. baseline: reveal the spanner halfway, unmoved ------------------
    item.set_reveal_edge(mid)
    base = clip_scene_x()
    print(f"\n1. unmoved, edge pushed to x={mid:.1f}")
    print(f"   clip lands at scene x = {base:.2f}   "
          f"(error {base - mid:+.2f})")

    # -- 2. nudge the element, then push the SAME edge again ---------------
    DX, DY = 30.0, -12.0
    item.setPos(DX, DY)
    item.set_reveal_edge(mid)
    after = clip_scene_x()
    print(f"\n2. nudged by ({DX:+.0f}, {DY:+.0f}), same edge x={mid:.1f}")
    print(f"   clip lands at scene x = {after:.2f}   "
          f"(error {after - mid:+.2f})")
    print(f"   -> stale-cache displacement: {after - base:+.2f} "
          f"(dx was {DX:+.0f})")

    # -- 3. does invalidating the cache repair it? -------------------------
    child._inverse = None                     # what a fix would do
    item.set_reveal_edge(mid)
    repaired = clip_scene_x()
    print(f"\n3. same, with the inverse cache invalidated first")
    print(f"   clip lands at scene x = {repaired:.2f}   "
          f"(error {repaired - mid:+.2f})")

    # -- 3b. isolate that residual: is it dx, dy, or the readout? ---------
    # The clip is a LOCAL vertical line; the honest correctness statement
    # is about clip_right in local coords, not about a scene-x readout at
    # an arbitrary y (a sheared transform makes the painted boundary a
    # SLANTED line, so "its scene x" depends on which y you sample).
    t = child.sceneTransform()
    print(f"\n3b. child sceneTransform: m11={t.m11():.4f} m12={t.m12():.4f} "
          f"m21={t.m21():.4f} m22={t.m22():.4f}")

    def local_clip(dx: float, dy: float) -> float:
        item.setPos(dx, dy)
        child._inverse = None
        child._clip_right = float("-inf")     # force a real recompute
        item.set_reveal_edge(mid)
        return child.clip_right

    home = local_clip(0.0, 0.0)
    print(f"    local clip_right, unmoved        : {home:.4f}")
    for dx, dy in ((10.0, 0.0), (-10.0, 0.0), (0.0, 20.0), (0.0, -20.0)):
        got = local_clip(dx, dy)
        print(f"    nudged ({dx:+5.0f},{dy:+5.0f}) -> {got:9.4f}   "
              f"moved {got - home:+.4f} (ink moved {dx:+.0f} in x)")
    print("    A pure-x nudge must move the local clip by exactly -dx;")
    print("    a pure-y nudge must not move it at all.")

    # -- 4. the semantic question, once the mechanism is correct ----------
    # With a correct inverse the clip stays at the PLAYHEAD's scene x, so
    # the moved ink is revealed by a different fraction than before.
    br = child.boundingRect()

    def revealed_fraction(dx: float, dy: float) -> float:
        local_clip(dx, dy)
        if child.clip_right is None:
            return 1.0
        return max(0.0, min(1.0, (child.clip_right - br.left())
                            / max(br.width(), 1e-9)))

    home_frac = revealed_fraction(0.0, 0.0)
    right_frac = revealed_fraction(+15.0, 0.0)
    left_frac = revealed_fraction(-15.0, 0.0)
    up_frac = revealed_fraction(0.0, -20.0)
    print(f"\n4. semantics with a correct inverse (edge = playhead scene x)")
    print(f"   revealed fraction at home     : {home_frac:.3f}")
    print(f"   nudged +15 in x (later)       : {right_frac:.3f}")
    print(f"   nudged -15 in x (earlier)     : {left_frac:.3f}")
    print(f"   nudged -20 in y (the exit case): {up_frac:.3f}")
    print("   (the edge is a playhead position in SCENE space, so moving")
    print("    ink right means the playhead reaches it later — the ink")
    print("    is revealed less. That is the behaviour we want.)")

    # -- 5. how many elements would be affected? ---------------------------
    revealed = [el for el in layout.elements
                if el.identity.kind in REVEALED_KINDS]
    kinds = {}
    for el in revealed:
        kinds[el.identity.kind.name] = kinds.get(el.identity.kind.name, 0) + 1
    print(f"\n5. revealed (clip-grown) elements on this fixture: "
          f"{len(revealed)}")
    for name, n in sorted(kinds.items()):
        print(f"   {name:10s} {n}")

    del app


if __name__ == "__main__":
    main()
