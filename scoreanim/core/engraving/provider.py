"""EngravingProvider seam (CLAUDE.md rule 4). Verovio lives behind this."""

from __future__ import annotations

import abc
from pathlib import Path

from scoreanim.core.engraving.types import EngravingParams, Layout
from scoreanim.core.score.musicxml_prep import PartGroupSpec


class EngravingProvider(abc.ABC):
    @abc.abstractmethod
    def load(self, score_path: Path, params: EngravingParams,
             groups: tuple[PartGroupSpec, ...] = ()) -> Layout:
        """Engrave the score and decompose it into an identity-tagged,
        paged Layout. Must be deterministic for (file contents, params,
        groups). `groups` are staff groups injected as <part-group> at
        the prep seam (Phase 8) — engraving inputs, never persisted."""
