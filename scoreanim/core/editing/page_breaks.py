"""What would "toggle the page break here" do? (M6.4)

The page twin of `core/editing/breaks.py`, and its own module rather than
a second half of that one: 233 lines were already close enough to the
no-monoliths ceiling that adding this would have crossed it, and the seam
is real — one module per document map, with the rule that couples them in
`break_coherence`.

Everything M5 decided about the toggle is reused wholesale (D4). The
BARLINE is the handle (rule 13 — nothing else on a staff carries a break
position, and M2's tiering made scaffold selectable precisely so a
barline could answer a click with a measure ordinal). "Here" means after
this measure, so the document key is N+1, the measure that would START
the page (D2) — exactly what `<print new-page="yes">` and `_repaginate`'s
`break_measures` already mean. The same five disable cases apply, each
saying WHY.

Two things are new, and both come from pages being the one layout input
the app already OWNED:

- The toggle reads `page_of_measure`, derived per load from the system
  bands and the measure→system map (§1.2), so "does this already start a
  page" is answered by what is on screen — including a page start that
  never-clip derived rather than the file encoding. That is the honest
  question after a repagination.
- A page FORCE can contradict a system SUPPRESS at the same ordinal, so
  the gesture carries the clearing of that contradiction with it
  (`also_system`) and stays ONE undo entry (rule 8, D3's prevention
  half).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from scoreanim.core.editing.break_coherence import normalize
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_prep import PageBreak, SystemBreak
from scoreanim.core.selection.context import Selection

# Status-tip text for each disabled case (the standing rider: a disabled
# control names WHY). Phrased for a status bar, not a log — and phrased
# for PAGES, which is why they are their own constants rather than the
# system half's strings with a word swapped.
NO_SCORE = "No score is loaded"
NO_SELECTION = "Select a barline to toggle a page break"
NOT_A_BARLINE = "Page breaks are toggled from a barline"
NO_MEASURE = ("This barline opens a system and carries no measure — "
              "use the barline at the end of a measure")
LAST_MEASURE = "There is no music after the last measure to start a page"


@dataclass(frozen=True)
class PageBreakAction:
    """What the page-break action should do with the current selection —
    `SetPageBreak`'s arguments, ready to pass.

    Its own type rather than a reuse of `BreakAction`: the two carry
    different vocabularies in `mode`, and a single dataclass typed
    `SystemBreak | PageBreak` would let a page gesture be handed to the
    system command without anything complaining. When `reason` is set the
    action is disabled and the rest is meaningless.
    """
    ordinal: int | None = None
    mode: PageBreak | None = None
    also: tuple[tuple[int, PageBreak | None], ...] = ()
    also_system: tuple[tuple[int, SystemBreak | None], ...] = ()
    reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self.reason is None


def page_starts(page_of_measure: Mapping[int, int]) -> frozenset[int]:
    """The measure ordinals that currently START a page.

    A thin re-export of the engraving-side derivation so this policy
    reads like its system twin (`breaks.system_starts`) and callers need
    only one import.
    """
    first: dict[int, int] = {}
    for measure, page in page_of_measure.items():
        if measure < first.get(page, 1 << 30):
            first[page] = measure
    return frozenset(first.values())


def toggle_mode(target: int,
                overrides: Mapping[int, PageBreak],
                page_of_measure: Mapping[int, int]) -> PageBreak | None:
    """The three-step toggle sense (D5), M5's exactly:

    1. An override already exists for the target → CLEAR it (None), back
       to whatever the file encodes. Keeps the doc sparse and makes the
       gesture perfectly reversible — press twice, nothing stored.
    2. No override, and the target already starts a page in the CURRENT
       layout → SUPPRESS.
    3. No override, and it does not → FORCE.

    Step 2 reads the engraved layout, not the encoded break set, and for
    pages that matters more than it did for systems: after a never-clip
    repagination the page a measure starts may be the app's choice rather
    than the file's. The question the user is asking is "does this start
    a page on screen right now", and the answer is on screen.
    """
    if target in overrides:
        return None
    if target in page_starts(page_of_measure):
        return PageBreak.SUPPRESS
    return PageBreak.FORCE


def contradicting_system_entries(target: int,
                                 mode: PageBreak | None,
                                 system_overrides: Mapping[int, SystemBreak]
                                 ) -> tuple[tuple[int, SystemBreak | None], ...]:
    """The system-map entries this page gesture must also write, so the
    document never holds a contradicting pair (D3's prevention half).

    At most one entry, and only for the one incoherent combination: a
    page FORCE where a system SUPPRESS is stored. Clearing it travels in
    the SAME command, so the gesture is one undo entry (rule 8) — a
    second command would let undo leave the document in a state the user
    never authored.
    """
    stored = system_overrides.get(target)
    coherent, _ = normalize(stored, mode)
    return () if coherent is stored else ((target, coherent),)


def resolve(selection: Selection | None,
            page_overrides: Mapping[int, PageBreak],
            system_overrides: Mapping[int, SystemBreak],
            page_of_measure: Mapping[int, int]) -> PageBreakAction:
    """The whole policy, in the order the decisions were ruled (D4/D5)."""
    if not page_of_measure:
        return PageBreakAction(reason=NO_SCORE)
    if selection is None:
        return PageBreakAction(reason=NO_SELECTION)
    if selection.kind is not ElementKind.BARLINE:
        return PageBreakAction(reason=NOT_A_BARLINE)

    measure = selection.measure_ordinal
    if measure is None:                                   # D3's twin: the
        return PageBreakAction(reason=NO_MEASURE)         # system-start
    if measure >= max(page_of_measure):                   # barline, D6's
        return PageBreakAction(reason=LAST_MEASURE)       # twin

    target = measure + 1                                  # D2
    mode = toggle_mode(target, page_overrides, page_of_measure)
    return PageBreakAction(
        ordinal=target, mode=mode,
        also_system=contradicting_system_entries(target, mode,
                                                 system_overrides))
