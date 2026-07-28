"""What would "toggle the system break here" do? (M5.3)

Pure policy, the `core/editing/nudge.py` shape: no Qt, no document
writes, no engraving. It answers two questions the UI needs and nothing
else — may the action fire, and if so what should `SetSystemBreak`
receive — from three pieces of already-derived data: the selection, the
document's override map, and the engraved measure→system map.

**The barline is the handle (rule 13).** M2's tiering made scaffold
selectable precisely so that a barline could answer a click with a
measure ordinal, and rule 13 names it "M5's only handle": nothing else
on a staff carries a break position. So the action requires a selected
BARLINE — a notehead sits in a measure but not at a break.

**"Here" means after this measure, and the key is the NEXT one (D2).**
The selectable barline is the measure's RIGHT barline — measured, one
per measure, no measure without one (brief §3.5) — so clicking it
unambiguously means "the break falls after measure N". The document key
is therefore N+1, the measure that would START the new system: exactly
what `<print new-system="yes">` means and exactly what `_repaginate`'s
`break_measures` mean, so the seam is a lookup with no arithmetic and
the two break mechanisms read the same way.

**Two barlines carry nothing to key on.** The system-start (left)
barline is minted page-scoped (`score:p{page}:barline:{k}`) and returns
None from `Selection.measure_ordinal` — 5 of 24 barlines on testscore,
9 of 37 on bigband1 (D3). And the last measure's barline has no music
after it to start a system (D6). Both disable the action rather than
firing it into nothing, and each says why: a disabled control that
explains itself is the D1 rider.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_prep import SystemBreak
from scoreanim.core.selection.context import Selection

# Status-tip text for each disabled case (D1 rider: the disabled state
# names WHY). Phrased for a status bar, not a log.
NO_SELECTION = "Select a barline to toggle a system break"
NOT_A_BARLINE = "System breaks are toggled from a barline"
NO_MEASURE = ("This barline opens a system and carries no measure — "
              "use the barline at the end of a measure")
LAST_MEASURE = "There is no music after the last measure to start a system"
NO_SCORE = "No score is loaded"


@dataclass(frozen=True)
class BreakAction:
    """What the Score-menu action should do with the current selection.

    `ordinal` and `mode` are `SetSystemBreak`'s two arguments, ready to
    pass. When `reason` is set the action is disabled and the other two
    are meaningless.
    """
    ordinal: int | None = None
    mode: SystemBreak | None = None
    reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self.reason is None


def system_starts(system_of_measure: Mapping[int, int]) -> frozenset[int]:
    """The measure ordinals that currently START a system."""
    first: dict[int, int] = {}
    for measure, system in system_of_measure.items():
        if measure < first.get(system, 1 << 30):
            first[system] = measure
    return frozenset(first.values())


def resolve(selection: Selection | None,
            overrides: Mapping[int, SystemBreak],
            system_of_measure: Mapping[int, int]) -> BreakAction:
    """The whole policy, in the order the decisions were ruled."""
    if not system_of_measure:
        return BreakAction(reason=NO_SCORE)
    if selection is None:
        return BreakAction(reason=NO_SELECTION)
    if selection.kind is not ElementKind.BARLINE:
        return BreakAction(reason=NOT_A_BARLINE)

    measure = selection.measure_ordinal
    if measure is None:                                   # D3
        return BreakAction(reason=NO_MEASURE)
    if measure >= max(system_of_measure):                 # D6
        return BreakAction(reason=LAST_MEASURE)

    target = measure + 1                                  # D2
    return BreakAction(ordinal=target, mode=toggle_mode(
        target, overrides, system_of_measure))


def toggle_mode(target: int,
                overrides: Mapping[int, SystemBreak],
                system_of_measure: Mapping[int, int]) -> SystemBreak | None:
    """The three-step toggle sense (D4), in this order:

    1. An override already exists for the target → CLEAR it (None), back
       to whatever the file encodes. Keeps the doc sparse and makes the
       gesture perfectly reversible — press twice, nothing stored.
    2. No override, and the target already starts a system in the CURRENT
       layout → SUPPRESS.
    3. No override, and it does not → FORCE.

    Step 2 reads the engraved layout rather than the encoded break set,
    which is what makes the toggle honest after a repagination: the
    question is "does this measure start a system on screen right now",
    and the answer is on screen. The alternative — a second no-override
    load to recover the encoded set — was rejected as the cost of a
    menu-enable check.
    """
    if target in overrides:
        return None
    if target in system_starts(system_of_measure):
        return SystemBreak.SUPPRESS
    return SystemBreak.FORCE
