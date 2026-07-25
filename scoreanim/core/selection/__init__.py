"""Selection policy — pure, Qt-free (rule 1).

Selection itself is transient UI state living on AppState; this package
holds only the decisions that must be testable headless: which of the
overlapping elements under a click wins, and how to read the measure
ordinal out of a minted ElementId.
"""

from scoreanim.core.selection.policy import (BACKDROP_KINDS, HitCandidate,
                                             measure_ordinal_of, pick,
                                             sort_key, tier_of)

__all__ = [
    "BACKDROP_KINDS",
    "HitCandidate",
    "measure_ordinal_of",
    "pick",
    "sort_key",
    "tier_of",
]
