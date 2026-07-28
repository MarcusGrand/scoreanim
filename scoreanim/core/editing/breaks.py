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

**M5.7 adds a second gesture over the same two primitives.** "Move to
previous system" is SUPPRESS at the first measure of N's system plus
FORCE at N+1 — one composition, one command, one undo entry (D11/D12).
It needs no barline: any object carries its measure (rule 13), and the
gesture needs a measure rather than a break position.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from scoreanim.core.editing.break_coherence import normalize
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_prep import PageBreak, SystemBreak
from scoreanim.core.selection.context import Selection

# Status-tip text for each disabled case (D1 rider: the disabled state
# names WHY). Phrased for a status bar, not a log.
NO_SELECTION = "Select a barline to toggle a system break"
NOT_A_BARLINE = "System breaks are toggled from a barline"
NO_MEASURE = ("This barline opens a system and carries no measure — "
              "use the barline at the end of a measure")
LAST_MEASURE = "There is no music after the last measure to start a system"
NO_SCORE = "No score is loaded"

# ... and for the move-up gesture, which reads any object, not a barline
MOVE_NO_SELECTION = "Select an object in the measure you want to move"
MOVE_NO_MEASURE = "This object carries no measure to move"
FIRST_SYSTEM = "This measure is already in the first system"
UNKNOWN_MEASURE = "That measure is not in the engraved score"
NO_EFFECT = "Moving this measure would not change the layout"


@dataclass(frozen=True)
class BreakAction:
    """What a Score-menu break action should do with the current
    selection.

    `ordinal`, `mode` and `also` are `SetSystemBreak`'s three arguments,
    ready to pass. When `reason` is set the action is disabled and the
    others are meaningless.

    A plain toggle fills `ordinal`/`mode` and leaves `also` empty; a
    composed gesture (M5.7) puts its essential half first and the rest in
    `also` — which is also the order the view's re-anchor diff reads,
    since the primary ordinal is the lowest one (D14).

    `also_page` (M6, D3) is the cross-map half: a system SUPPRESS at an
    ordinal carrying a page FORCE is the one incoherent pair the two maps
    admit, and the gesture clears it rather than leaving the document
    arguing with itself. Same command, same undo entry (rule 8). The page
    twin of this type is `PageBreakAction` in `core/editing/page_breaks`.
    """
    ordinal: int | None = None
    mode: SystemBreak | None = None
    also: tuple[tuple[int, SystemBreak | None], ...] = ()
    also_page: tuple[tuple[int, PageBreak | None], ...] = ()
    reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self.reason is None


def system_starts(system_of_measure: Mapping[int, int]) -> frozenset[int]:
    """The measure ordinals that currently START a system."""
    return frozenset(first_measures(system_of_measure).values())


def first_measures(system_of_measure: Mapping[int, int]) -> dict[int, int]:
    """System index → the measure ordinal that starts it."""
    first: dict[int, int] = {}
    for measure, system in system_of_measure.items():
        if measure < first.get(system, 1 << 30):
            first[system] = measure
    return first


def contradicting_page_entries(target: int,
                               mode: SystemBreak | None,
                               page_overrides: Mapping[int, PageBreak]
                               ) -> tuple[tuple[int, PageBreak | None], ...]:
    """The page-map entries a system gesture must also write (M6, D3) —
    the mirror of `page_breaks.contradicting_system_entries`.

    At most one entry: a system SUPPRESS where a page FORCE is stored is
    the one incoherent pair, and the coherent resolution drops the SYSTEM
    entry, not the page one. So the gesture the user just made would be
    the one thrown away — which is the wrong way round for a toggle they
    pressed on purpose. The page FORCE is cleared instead, and the
    clearing travels in the same command so it is one undo entry.
    """
    stored = page_overrides.get(target)
    if not stored or normalize(mode, stored) == (mode, stored):
        return ()
    return ((target, None),)


def resolve(selection: Selection | None,
            overrides: Mapping[int, SystemBreak],
            system_of_measure: Mapping[int, int],
            page_overrides: Mapping[int, PageBreak] | None = None
            ) -> BreakAction:
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
    mode = toggle_mode(target, overrides, system_of_measure)
    return BreakAction(
        ordinal=target, mode=mode,
        also_page=contradicting_page_entries(target, mode,
                                             page_overrides or {}))


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


# ---------------------------------------------------------------------------
# M5.7 — move to previous system
# ---------------------------------------------------------------------------

def move_up_entries(measure: int,
                    overrides: Mapping[int, SystemBreak],
                    system_of_measure: Mapping[int, int]
                    ) -> tuple[tuple[int, SystemBreak | None], ...]:
    """The (ordinal, mode-or-clear) entries that move `measure` — and any
    earlier measures of its system — onto the previous system (D11).

    Two halves, over the two shipped primitives:

    - **merge**: the first measure S of this system must stop starting
      one, so S…N join the previous system.
    - **split**: the remainder N+1… must start a system of its own —
      present ONLY when there IS a remainder.

    Each half prefers CLEARING an opposite override to writing a new one.
    That is what keeps the document sparse and the gesture reversible,
    and it is sound because a FORCE is only ever written where nothing
    was encoded (`toggle_mode` step 3, and this function's own split
    half), so removing it is exactly enough to remove the break. Writing
    SUPPRESS over our own FORCE would instead leave a permanent entry the
    prep seam can find nothing to suppress with — inert, and reported as
    such by D10's warning for a gesture that worked.

    The split half is omitted when N+1 already starts a system, and this
    is a correctness rule rather than tidiness: measured (brief §M5.7.2
    M1), writing FORCE over an encoded break changes nothing at the seam
    and so trips the same "break-override-inert" warning.

    Entries that would not change the document at all are dropped last —
    defensive only; it needs a system that starts where nothing is
    encoded and nothing is forced, which break-respect mode does not
    produce (§M5.7.2 M2).
    """
    system = system_of_measure[measure]
    start = first_measures(system_of_measure)[system]
    entries: list[tuple[int, SystemBreak | None]] = []

    merge = (None if overrides.get(start) is SystemBreak.FORCE
             else SystemBreak.SUPPRESS)
    entries.append((start, merge))

    if system_of_measure.get(measure + 1) == system:      # a remainder
        split = (None if overrides.get(measure + 1) is SystemBreak.SUPPRESS
                 else SystemBreak.FORCE)
        entries.append((measure + 1, split))

    return tuple((ordinal, mode) for ordinal, mode in entries
                 if overrides.get(ordinal) is not mode)


def resolve_move_up(selection: Selection | None,
                    overrides: Mapping[int, SystemBreak],
                    system_of_measure: Mapping[int, int],
                    page_overrides: Mapping[int, PageBreak] | None = None
                    ) -> BreakAction:
    """The move-up policy, in the order the decisions were ruled (D13).

    Unlike the toggle this reads ANY selected object, not only a barline:
    selecting an object carries its containing measure (rule 13), and the
    gesture needs a measure rather than a break position. The barline
    remains the handle for the raw toggle, whose "the break falls after
    measure N" arithmetic is specific to a measure's right barline.
    """
    if not system_of_measure:
        return BreakAction(reason=NO_SCORE)
    if selection is None:
        return BreakAction(reason=MOVE_NO_SELECTION)

    measure = selection.measure_ordinal
    if measure is None:
        return BreakAction(reason=MOVE_NO_MEASURE)
    system = system_of_measure.get(measure)
    if system is None:                                    # stale ordinal
        return BreakAction(reason=UNKNOWN_MEASURE)
    if system <= min(system_of_measure.values()):
        return BreakAction(reason=FIRST_SYSTEM)

    entries = move_up_entries(measure, overrides, system_of_measure)
    if not entries:
        return BreakAction(reason=NO_EFFECT)
    (ordinal, mode), *rest = entries
    # the composed gesture writes up to two ordinals, so it clears a
    # contradicting page FORCE at either of them (M6, D3)
    also_page = tuple(entry for o, m in entries
                      for entry in contradicting_page_entries(
                          o, m, page_overrides or {}))
    return BreakAction(ordinal=ordinal, mode=mode, also=tuple(rest),
                       also_page=also_page)
