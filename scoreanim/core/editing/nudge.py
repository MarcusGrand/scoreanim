"""May this element be dragged, and by how much?

`LayoutOverride.dx/dy` have been schema slots since Phase 4 ("no editing
UI yet"); M3 is what consumes them. Deltas are in PAGE units and keyed
by musical `ElementId` — never absolute pixels (rule 5). Override
staleness across a re-engrave stays the accepted trade (ARCHITECTURE §4).

**NUDGEABLE_KINDS starts narrow** — the roadmap's three named targets,
and nothing else. What is left out, and why:

  notehead, stem, flag, beam, accidental, ledger lines
      separate elements with separate ids, so nudging one tears a note
      apart. Compound-object dragging is not M3's problem.
  slur, tie
      anchored to notes at BOTH ends, so moving one desynchronizes it
      from the notes it belongs to. (TIE is also 66 of testscore's 73
      clip-revealed elements — high blast radius, low value.)
  staff lines, barline, group symbol, system divider
      scaffold. The barline is M5's handle and nothing else.
  clef, key sig, meter sig
      placed by the engraver as a consequence of the music.
  rest, mrest, slash, bar repeat, lyric, chord symbol
      plausible later additions, deliberately not v1.

HAIRPIN is in `REVEALED_KINDS`, so nudging it moves ink that a growing
clip is revealing. `spikes/nudge_reveal.py` measured that interaction
rather than assuming it: the clip edge arrives as a SCENE x and is
mapped through an inverse transform that `RevealPathItem` caches, so a
moved element reveals as if the playhead were dx further right — the
error is exactly dx. Invalidating that cache on a move makes the local
clip track exactly −dx and stay y-independent. Ruling (Marcus,
2026-07-27): fix the cache, keep HAIRPIN.
"""
from __future__ import annotations

from scoreanim.core.score.identity import ElementKind

# The roadmap's three named targets (start narrow; see module docstring).
NUDGEABLE_KINDS = frozenset({
    ElementKind.DYNAMIC,
    ElementKind.HAIRPIN,
    ElementKind.TEXT,
})

# Keyboard nudge, in PAGE units. One unit is the arrow-key step; Shift
# multiplies it. Page units are Verovio's own, so these are rastral-
# relative and stay sensible on a scaled-to-fit orchestral score.
NUDGE_STEP = 1.0
COARSE_NUDGE = 10.0


def is_nudgeable(kind: ElementKind | None) -> bool:
    return kind is not None and kind in NUDGEABLE_KINDS


def nudged_delta(dx: float, dy: float,
                 step_dx: float, step_dy: float) -> tuple[float, float]:
    """Accumulate a keyboard nudge onto an element's existing delta.

    Arithmetic, not state: the caller reads the current override off the
    document and writes the result back through one command, so a held
    arrow key produces one undo entry per press — the same "one gesture,
    one entry" rule a drag obeys (rule 8).
    """
    return (dx + step_dx, dy + step_dy)
