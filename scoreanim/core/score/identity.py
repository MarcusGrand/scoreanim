"""Musical identity types — the shared currency across all layers.

ElementIds are minted by the engraving adapter from musical identity
(part/measure/staff/voice/kind/index), never by wrapping provider ids,
so layout overrides keyed to them survive engraving reflows
(ARCHITECTURE.md §4).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import NewType

ElementId = NewType("ElementId", str)
PartId = NewType("PartId", str)          # MusicXML part id, e.g. "P1"

# Musical time in quarter notes from score start (matches Verovio's qstamp
# and music21's flattened offsets). float is sufficient for v1.
Beats = float


class ElementKind(enum.Enum):
    NOTEHEAD = enum.auto()
    STEM = enum.auto()
    FLAG = enum.auto()
    BEAM = enum.auto()
    SLUR = enum.auto()
    TIE = enum.auto()
    HAIRPIN = enum.auto()
    ACCIDENTAL = enum.auto()
    ARTICULATION = enum.auto()
    TREMOLO = enum.auto()                # tremolo stroke ink (Phase 11);
                                         # animates with its owning note
                                         # (ruling a), untinted
    DYNAMIC = enum.auto()
    REST = enum.auto()
    MREST = enum.auto()                  # whole-measure rest
    SLASH = enum.auto()                  # synthesized (CLAUDE.md rule 10)
    CLEF = enum.auto()
    KEY_SIG = enum.auto()
    METER_SIG = enum.auto()
    BARLINE = enum.auto()
    STAFF_LINES = enum.auto()
    GROUP_SYMBOL = enum.auto()           # staff-group bracket/brace ink
                                         # (Phase 8) — static, untinted
    SYSTEM_DIVIDER = enum.auto()         # between-system divider glyph
                                         # (Phase 10 ruling a) — static by
                                         # construction, like GROUP_SYMBOL
    LEDGER_LINES = enum.auto()           # per-dash, note-owned (BACKLOG 6)
    LYRIC = enum.auto()
    CHORD_SYMBOL = enum.auto()
    TEXT = enum.auto()                   # directions, tempo text, rehearsal marks
    OTHER = enum.auto()                  # fallback — unknown classes never crash


@dataclass(frozen=True)
class ElementIdentity:
    element_id: ElementId
    kind: ElementKind
    part: PartId | None                  # None for score-level elements
    part_name: str | None
    staff: int | None                    # part-local, 1-based (a grand
                                         # staff is staff 1/2 of its part)
    voice: int | None
    onset: Beats | None                  # None for non-timed elements
    extent: tuple[Beats, Beats] | None = None   # spanners: (start, end)
