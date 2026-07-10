"""EngravingProvider seam (CLAUDE.md rule 4). Verovio lives behind this."""

from __future__ import annotations

import abc
from pathlib import Path

from scoreanim.core.engraving.types import EngravingParams, Layout


class EngravingProvider(abc.ABC):
    @abc.abstractmethod
    def load(self, score_path: Path, params: EngravingParams) -> Layout:
        """Engrave the score and decompose it into an identity-tagged,
        paged Layout. Must be deterministic for (file contents, params)."""
