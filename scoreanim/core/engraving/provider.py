"""EngravingProvider seam (CLAUDE.md rule 4). Verovio lives behind this."""

from __future__ import annotations

import abc
from pathlib import Path

from scoreanim.core.engraving.types import EngravingParams, Layout
from scoreanim.core.score.musicxml_prep import PartGroupSpec, PartTextSpec


class EngravingProvider(abc.ABC):
    @abc.abstractmethod
    def load(self, score_path: Path, params: EngravingParams,
             groups: tuple[PartGroupSpec, ...] = (),
             texts: tuple[PartTextSpec, ...] = ()) -> Layout:
        """Engrave the score and decompose it into an identity-tagged,
        paged Layout. Must be deterministic for (file contents, params,
        groups, texts). `groups` are staff groups injected as
        <part-group> at the prep seam (Phase 8); `texts` are part-label
        overrides rewritten into the part-list there (Phase 9.3) —
        engraving inputs, never persisted, and separate arguments (NOT
        EngravingParams fields: params serialize in the doc and would
        duplicate doc.staff_groups / doc.text_overrides)."""
