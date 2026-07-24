"""EngravingProvider seam (CLAUDE.md rule 4). Verovio lives behind this."""

from __future__ import annotations

import abc
from pathlib import Path

from scoreanim.core.engraving.types import EngravingParams, Layout
from scoreanim.core.score.musicxml_prep import (PartCondenseSpec,
                                                PartGroupSpec, PartTextSpec)


class EngravingProvider(abc.ABC):
    @abc.abstractmethod
    def load(self, score_path: Path, params: EngravingParams,
             groups: tuple[PartGroupSpec, ...] = (),
             texts: tuple[PartTextSpec, ...] = (),
             hide_empty_staves: bool = False,
             condense: tuple[PartCondenseSpec, ...] = (),
             hide_first_system: bool = False) -> Layout:
        """Engrave the score and decompose it into an identity-tagged,
        paged Layout. Must be deterministic for (file contents, params,
        groups, texts, hide_empty_staves, condense, hide_first_system).
        `groups` are staff groups injected as <part-group> at the prep
        seam (Phase 8); `texts` are part-label overrides rewritten into
        the part-list there (Phase 9.3); `hide_empty_staves` (Phase 10R)
        hides staves that are empty for a whole system, as the score's
        encoded page layout assumes; `hide_first_system` (2026-07-24)
        extends the hiding to the first system, dropping the
        first-system-full convention (no effect unless
        hide_empty_staves); `condense` (Phase 12.3) merges contiguous
        like parts onto one staff there — engraving inputs, never
        persisted, and separate arguments (NOT EngravingParams fields:
        params serialize in the doc and would duplicate
        doc.staff_groups / doc.text_overrides / doc.hide_empty_staves /
        doc.condense_groups)."""
