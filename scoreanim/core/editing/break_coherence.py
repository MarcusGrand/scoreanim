"""What the two break maps may say about ONE measure (M6, D3).

The document holds two sparse maps keyed the same way — the system-break
delta (M5) and the page-break delta (M6) — and they can disagree, because
a page break implies a system break. `_wanted_break_attrs` in
`core/score/musicxml_rewrite.py` states what the PREP SEAM does when they
do; this module states what the DOCUMENT should hold, which is the other
half of the same ruling and the reason the seam's precedence is almost
never exercised.

The two are deliberately separate. The seam must be total — it has to
answer for a hand-edited file, or for a pair gone stale under rule 5 —
while this module is what the toggles consult so the user cannot author
an incoherent pair in the first place. A precedence with no prevention
leaves the document holding entries that argue with each other and every
future reader re-deriving the rule; prevention with no precedence has
nothing to say when a file arrives holding one anyway.

Pure policy: no Qt, no document writes, no engraving (rule 1, the
`core/editing/nudge.py` shape).
"""
from __future__ import annotations

from scoreanim.core.score.musicxml_prep import PageBreak, SystemBreak


def contradicts(system_mode: SystemBreak | None,
                page_mode: PageBreak | None) -> bool:
    """Is this pair of overrides at ONE ordinal incoherent?

    Exactly one pair is, and it is the pair §3.4 measured resolving in
    OPPOSITE directions under the two possible pass orderings: **a page
    FORCE with a system SUPPRESS**. "Start a page here" and "do not start
    a system here" cannot both hold, because starting a page starts a
    system.

    Every other combination means what it says:

    - page FORCE + system FORCE — the same thing said twice.
    - page SUPPRESS + system SUPPRESS — two negatives, and the pair the
      seam reads as "remove both breaks" rather than preserving the
      implied system break.
    - page SUPPRESS + system FORCE — "keep the system break, drop the
      page break", which is what a page suppression asserts on its own
      anyway.
    """
    return (page_mode is PageBreak.FORCE
            and system_mode is SystemBreak.SUPPRESS)


def normalize(system_mode: SystemBreak | None,
              page_mode: PageBreak | None
              ) -> tuple[SystemBreak | None, PageBreak | None]:
    """The coherent pair a document should hold for one ordinal.

    Only the contradicting pair changes, and it changes the way the seam
    would resolve it anyway (`_wanted_break_attrs` rule 1): the page
    FORCE wins and the system SUPPRESS is dropped, because a page break
    that refuses its own system break is not a layout and the positive
    assertion is the one that can be honored.

    Dropping rather than flipping is what keeps the document sparse and
    the gesture reversible: the system entry disappears, so toggling the
    page break off later leaves nothing behind.
    """
    if contradicts(system_mode, page_mode):
        return None, page_mode
    return system_mode, page_mode
