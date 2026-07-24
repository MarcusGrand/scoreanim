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
from scoreanim.core.score.identity import Beats, ElementId, PartId
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
class StaffGroup:
    """One bracket/brace group (schema v3 slot; consumed from Phase 8).
    Intent only: the document stores WHICH contiguous parts group and
    how; bracket geometry is re-derived by injecting <part-group>
    elements at the prep seam and re-engraving (rule 5)."""
    parts: tuple[PartId, ...]        # contiguous, in score order
    symbol: str = "bracket"          # MusicXML group-symbol vocabulary
    join_barlines: bool = True


@dataclass(frozen=True)
class PartTextOverride:
    """Part-label edits (schema v3 slot; consumed from Phase 9). Applied
    to the part-list at the prep seam → re-engrave; None fields keep
    the score's own text."""
    name: str | None = None
    abbreviation: str | None = None


@dataclass(frozen=True)
class CondenseGroup:
    """Contiguous like parts merged onto one staff, one voice per source
    player (schema v5 slot; consumed from Phase 12.3). Intent only: the
    document stores WHICH parts merge and the combined label; the merge
    is re-derived by rewriting the part-list at the prep seam and
    re-engraving (rule 5). ElementIds shift when condensing changes —
    part identity is an engraving input, like a rename."""
    parts: tuple[PartId, ...]        # >= 2, contiguous, in score order
    name: str = ""                   # combined part-name (e.g. "Flute 1.2");
                                     # "" → derived from the sources at the seam
    abbreviation: str = ""           # combined abbreviation (e.g. "Fl. 1.2")


# New documents hide empty staves (Phase 10R ruling: the layouts our
# scores encode assume Dorico's hide-empty-staves). Projects saved at
# schema <= 3 load with it OFF so their look is unchanged (serialize.py).
HIDE_EMPTY_STAVES_DEFAULT = True


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
    staff_groups: tuple[StaffGroup, ...] = ()
    text_overrides: Mapping[PartId, PartTextOverride] = \
        field(default_factory=dict)
    # Intent only (rule 5): whether staves empty for a whole system are
    # hidden; the hidden layout is re-derived at every engrave.
    hide_empty_staves: bool = HIDE_EMPTY_STAVES_DEFAULT
    # Also hide on the FIRST system (schema v6, Marcus 2026-07-24) —
    # off by default: first-system-full is the engraving convention the
    # Phase 10R hide deliberately kept. Meaningful only with
    # hide_empty_staves; rides the same re-engrave.
    hide_first_system: bool = False
    # Contiguous like parts merged onto one staff (schema v5, consumed
    # Phase 12.3); the merged part-list is re-derived at the prep seam.
    condense_groups: tuple[CondenseGroup, ...] = ()


__all__ = ["DEFAULT_BPM", "FileRef", "HIDE_EMPTY_STAVES_DEFAULT",
           "LayoutOverride", "PartTextOverride", "ProjectDoc", "StaffGroup",
           "StyleRules", "TimingConfig", "Beats"]
