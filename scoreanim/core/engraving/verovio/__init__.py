"""Verovio adapter package: MusicXML → identity-tagged, paged Layout
(plan D2/D3/D5), one module per pipeline stage.

Verovio types, ids, and SVG never leak past this package (CLAUDE.md
rule 4). ElementIds are minted here from musical identity (part/measure/
staff/voice/kind/index), so they are deterministic across loads and
survive engraving reflows. A fixed xmlIdSeed keeps Verovio's internal
ids reproducible for the timemap ↔ SVG ↔ MEI cross-referencing inside a
load.

Pipeline order (one function names it: provider._engrave_prepared):
engrave → parse MEI → timemap → decompose pages → rehome strays →
attribute ledger dashes → attribute spanner segments → flag implausible
ties → build elements → synthesize slashes/repeats.
"""

from scoreanim.core.engraving.verovio.provider import \
    VerovioEngravingProvider
from scoreanim.core.engraving.verovio.records import (AdapterNoteRecord,
                                                      EngravedScore)

__all__ = ["AdapterNoteRecord", "EngravedScore",
           "VerovioEngravingProvider"]
