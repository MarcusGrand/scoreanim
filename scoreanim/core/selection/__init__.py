"""Selection policy and shape — pure, Qt-free (rule 1).

Selection LIVES as transient UI state on AppState; this package holds
only what must be testable headless: which of the overlapping elements
under a click wins (policy.py), and what a selection IS once made —
the object plus the measure and part it carries (context.py, rule 13).
"""

from scoreanim.core.selection.context import Selection
from scoreanim.core.selection.policy import (BACKDROP_KINDS, HitCandidate,
                                             measure_ordinal_of, pick,
                                             sort_key, tier_of)

__all__ = [
    "BACKDROP_KINDS",
    "HitCandidate",
    "Selection",
    "measure_ordinal_of",
    "pick",
    "sort_key",
    "tier_of",
]
