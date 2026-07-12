"""The project document: user intent only, never derived data (rule 5).

One immutable value. Commands (core/project/commands.py) are the only
way it changes after load; serialization (core/project/serialize.py) is
"write the current value". Layouts, timemaps, peak caches and decomposed
geometry are always re-derived from (score file + engraving params +
overrides) and never appear here.

File binding is a document *reset*, not an intent edit (ruling
2026-07-11): opening a score builds a fresh doc and clears the undo
stack; binding audio replaces ``audio`` outside the stack. Everything
else mutates through commands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from scoreanim.core.animation.style import StyleRules
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.project.stage_config import StageConfig
from scoreanim.core.score.identity import Beats, ElementId
from scoreanim.core.timing.swing import SwingRegion
from scoreanim.core.timing.taps import TapSession
from scoreanim.core.timing.tempo_map import TempoEvent

DEFAULT_BPM = 120.0


@dataclass(frozen=True)
class FileRef:
    path: str                    # absolute at runtime; relativized on save
    sha256: str | None = None


@dataclass(frozen=True)
class LayoutOverride:
    """Schema slot only in Phase 4 — no editing UI yet. Deltas keyed by
    musical ElementId, never absolute pixels (rule 5)."""
    dx: float = 0.0
    dy: float = 0.0
    hidden: bool = False


@dataclass(frozen=True)
class TimingConfig:
    offset_seconds: float = 0.0          # audio time of beat 0
    tempo_events: tuple[TempoEvent, ...] = (TempoEvent(0.0, DEFAULT_BPM),)
    swing_regions: tuple[SwingRegion, ...] = ()
    tap_sessions: tuple[TapSession, ...] = ()   # raw taps, kept (rule 5)


# Styling is the rule-based StyleRules model (core/animation/style.py):
# per-part color/effect rules + per-element overrides + reveal mode.
# It subsumed Phase 2's StyleConfig.part_colors in Phase 5.3; legacy
# files migrate at load (serialize.py).

@dataclass(frozen=True)
class ProjectDoc:
    score: FileRef | None = None
    audio: FileRef | None = None
    engraving: EngravingParams = field(default_factory=EngravingParams)
    layout_overrides: Mapping[ElementId, LayoutOverride] = \
        field(default_factory=dict)
    timing: TimingConfig = field(default_factory=TimingConfig)
    style: StyleRules = field(default_factory=StyleRules)
    stage: StageConfig = field(default_factory=StageConfig)


__all__ = ["DEFAULT_BPM", "FileRef", "LayoutOverride", "ProjectDoc",
           "StyleRules", "TimingConfig", "Beats"]
