"""Qt-touching pieces shared by the L1/L2 checks: scene + applier
construction as the window builds them, the observable-state snapshot,
and the fresh-transform clip expectation. Everything else in the oracle
stays importable without a display stack.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from scoreanim.core.animation import StyleRules
from scoreanim.core.project.stage_config import (default_stage_config,
                                                 page_content_top)
from scoreanim.render.animate import AnimationApplier
from scoreanim.render.scene import ScoreScenes
from scoreanim.tools.live_oracle.bundle import OracleBundle


def _ensure_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def build_scene_applier(bundle: OracleBundle,
                        style: StyleRules) -> tuple[ScoreScenes,
                                                    AnimationApplier]:
    """Scenes + applier as the window builds them (fresh-document
    defaults; ghost opacity = the style's floor, as _sync_styles ends up
    applying)."""
    _ensure_app()
    stage = default_stage_config(bundle.engraved.prepared,
                                 page_content_top(bundle.engraved.layout))
    scenes = ScoreScenes(bundle.engraved.layout, stage,
                         ghost_opacity=style.floor_opacity)
    applier = AnimationApplier(scenes.items, bundle.schedule,
                               bundle.tempo_map, style, bundle.tracks)
    return scenes, applier


def _snapshot(scenes: ScoreScenes) -> dict:
    out = {}
    for eid, item in scenes.items.items():
        clips = tuple(
            (None if c.clip_right is None else round(c.clip_right, 4),
             c.hidden)
            for c in item.reveal_children)
        out[eid] = (round(item.opacity(), 6), round(item.scale(), 6), clips)
    return out


def _expected_clip(child, edge_scene_x: float):
    """set_clip_right's math with a FRESHLY inverted scene transform (the
    cached one is an F5 suspect)."""
    inv, ok = child.sceneTransform().inverted()
    if not ok:
        return None, False
    local_x = inv.map(QPointF(edge_scene_x, 0.0)).x()
    br = child.boundingRect()
    clip = min(max(local_x, br.left()), br.right())
    if clip >= br.right():
        return None, False
    return clip, clip <= br.left()
