"""Break commands: the system map (M5) and the page map (M6).

Split out of `layout.py` when that module passed the ~400-line ceiling
(the no-monoliths rule). Its own module because the two break commands
are one domain: they share `_write_breaks`, they write each other's map
through the `also_*` fields, and `core/editing/` already splits the same
way (`breaks.py` / `page_breaks.py`). No behaviour changed in the move.

Both are ENGRAVING INPUTS: the window re-engraves on an override diff,
so they arrive through execute(), never preview().
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from scoreanim.core.project.commands.base import Command, CommandError
from scoreanim.core.project.document import PageBreak, ProjectDoc, SystemBreak


def _write_breaks(overrides: dict, entries) -> dict:
    """Apply (ordinal, mode-or-None) entries to one override map.

    Shared by both break commands: `mode=None` POPS so the doc stays
    sparse, and an ordinal is validated as >= 1 only — the commands
    deliberately do not know the engraved layout (no command does), so
    an ordinal past the end of the score is stored and left inert, with
    the load-time warning doing the telling (rule 5's stated staleness
    trade, and `_repaginate`'s own behaviour for an out-of-range plan
    entry).
    """
    for ordinal, mode in entries:
        if ordinal < 1:
            raise CommandError(f"measure ordinal {ordinal} is not >= 1")
        if mode is None:
            overrides.pop(ordinal, None)
        else:
            overrides[ordinal] = mode
    return overrides


@dataclass(frozen=True)
class SetSystemBreak(Command):
    """Force or suppress the system break at one measure — the app's first
    layout-INTENT edit, and an ENGRAVING INPUT like staff_groups: the
    window re-engraves on the system_break_overrides diff (measured 0.25 s
    on testscore, 1.28 s on bigband1 — brief §3.6 F4), so this arrives via
    execute(), never preview().

    `ordinal` is the 1-based document-order ordinal of the measure that
    would START the system (D2), never a printed number — the same
    identity `_repaginate`'s break_measures use, so the two break
    mechanisms read the same way at the seam.

    `mode=None` POPS the entry, returning that measure to whatever the
    file encodes, so the doc stays sparse (the SetElementStyle idiom) and
    the gesture is perfectly reversible. Ordinals are validated as >= 1
    only: the command deliberately does NOT know the engraved layout (no
    command does), so an ordinal past the end of the score is stored and
    left inert, with the load-time warning of D10 doing the telling —
    rule 5's stated staleness trade, and `_repaginate`'s own behaviour
    for an out-of-range plan entry.

    `also` carries ADDITIONAL (ordinal, mode-or-clear) entries applied in
    the same step (M5.7, D12). One gesture can need more than one break
    written: "move to previous system" is SUPPRESS at the first measure
    of this system plus FORCE at the next one, and rule 8 counts
    gestures, not documents touched. The 'fat apply' idiom
    `ApplyScoreSetup` and `SetElementStyle.segments` already use — there
    being no generic macro command — and the one ROADMAP §M5's
    inheritance note (c) named for exactly this case. Empty for a plain
    toggle, which is the common case.

    `also_page` (M6, D3) is the cross-map half of the same idiom: a
    system SUPPRESS at an ordinal carrying a page FORCE is the one
    INCOHERENT pair the two maps admit (a page break implies a system
    break, so the seam's precedence would let the page half win and the
    gesture would appear to do nothing). The toggle clears the
    contradicting page override in the SAME step rather than leaving the
    document holding a pair that argues with itself — one gesture, one
    undo entry (rule 8). Additive: every existing call site is unchanged.
    """
    ordinal: int
    mode: SystemBreak | None
    also: tuple[tuple[int, SystemBreak | None], ...] = ()
    also_page: tuple[tuple[int, PageBreak | None], ...] = ()

    @property
    def entries(self) -> tuple[tuple[int, SystemBreak | None], ...]:
        """Every (ordinal, mode) this command writes to the SYSTEM map,
        primary first."""
        return ((self.ordinal, self.mode), *self.also)

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return replace(
            doc,
            system_break_overrides=_write_breaks(
                dict(doc.system_break_overrides), self.entries),
            page_break_overrides=_write_breaks(
                dict(doc.page_break_overrides), self.also_page))

    def describe(self) -> str:
        # The M3.5 rule: the phrase must be true for every caller of the
        # mechanism, not named for the first one. A composed gesture
        # names itself in its own menu label ("Move to Previous
        # System"); here it can only honestly say what it wrote.
        if self.also_page:
            return "change breaks"          # both maps written
        if self.also:
            return "change system breaks"
        if self.mode is None:
            return "clear system break"
        if self.mode is SystemBreak.FORCE:
            return "force system break"
        return "suppress system break"


@dataclass(frozen=True)
class SetPageBreak(Command):
    """Force or suppress the page break at one measure (M6) — the fourth
    use of the fat-apply idiom, and `SetSystemBreak`'s sibling in every
    respect the two maps share.

    An ENGRAVING INPUT like `system_break_overrides`: the window
    re-engraves on the `page_break_overrides` diff (measured 0.27 s on
    testscore, 0.68 s on bigband1 — brief §3.5 E4), so this arrives via
    execute(), never preview().

    `ordinal` is the 1-based document-order ordinal of the measure that
    would START the page (D2), never a printed number. `mode=None` POPS
    the entry, so the doc stays sparse and the gesture is perfectly
    reversible. `also` carries additional PAGE entries; `also_system`
    carries SYSTEM entries written in the same step (D3's prevention
    half — a page FORCE at an ordinal carrying a system SUPPRESS clears
    that suppression rather than relying on the seam's precedence to
    overrule it, so the document never holds a contradicting pair).

    What this command does NOT promise, and the reason D1 was a
    stop-and-ask: a SUPPRESS is a request, not a guarantee. Never-clip
    owns the final page plan (rule 7), so the planner may put a page
    break back somewhere the overrides did not ask for — measured as a
    normal outcome, and reported by the D8 `page-break-repaginated`
    warning rather than failing silently.
    """
    ordinal: int
    mode: PageBreak | None
    also: tuple[tuple[int, PageBreak | None], ...] = ()
    also_system: tuple[tuple[int, SystemBreak | None], ...] = ()

    @property
    def entries(self) -> tuple[tuple[int, PageBreak | None], ...]:
        """Every (ordinal, mode) this command writes to the PAGE map,
        primary first."""
        return ((self.ordinal, self.mode), *self.also)

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return replace(
            doc,
            page_break_overrides=_write_breaks(
                dict(doc.page_break_overrides), self.entries),
            system_break_overrides=_write_breaks(
                dict(doc.system_break_overrides), self.also_system))

    def describe(self) -> str:
        # the M3.5 rule again: only ever says what it wrote
        if self.also_system:
            return "change breaks"          # both maps written
        if self.also:
            return "change page breaks"
        if self.mode is None:
            return "clear page break"
        if self.mode is PageBreak.FORCE:
            return "force page break"
        return "suppress page break"
