"""What the hint bar says (D3): the selection, and what you can do to it.

The status bar is the one place in the app that can answer "I clicked a
thing — now what?" without the user opening a menu to find out. So with
something selected it reads

    Note · Trumpets · m. 19 — drag its onset line to re-time it, F flips
    the stem

and with nothing selected it names the recording that is loaded.

**This module owns the wording and nothing else.** It is pure (rule 1),
so every sentence the bar can say is headless-testable, and it decides
none of the availability: `Gestures` arrives already answered by the
controllers that own each gesture — the delete and flip actions'
enabled state, the break policy's resolve, the onset cursor's own "is
the line up", the nudge policy. That keeps one source of truth per
gesture, so the bar cannot promise a key the app would ignore.

Two deliberate limits:

- **At most three phrases** (`MAX_PHRASES`). A text can do four things
  at once and the bar is one line; the menus stay the complete list.
  The order below is the priority: what the pointer can do first, then
  what a key does.
- **The printed measure number**, not the document ordinal. The bar
  names what is on the page in front of you; the Selection panel is
  where the two are told apart.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from scoreanim.core.project.document import SystemBreak
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.selection.context import Selection

# Plain names for what you picked. Every kind is here on purpose: a new
# ElementKind should be named by a person, not title-cased by accident
# (tests/test_hints.py pins the table complete).
KIND_LABELS: dict[ElementKind, str] = {
    ElementKind.NOTEHEAD: "Note",
    ElementKind.STEM: "Stem",
    ElementKind.FLAG: "Flag",
    ElementKind.BEAM: "Beam",
    ElementKind.SLUR: "Slur",
    ElementKind.TIE: "Tie",
    ElementKind.HAIRPIN: "Hairpin",
    ElementKind.ACCIDENTAL: "Accidental",
    ElementKind.ARTICULATION: "Articulation",
    ElementKind.TREMOLO: "Tremolo",
    ElementKind.DYNAMIC: "Dynamic",
    ElementKind.REST: "Rest",
    ElementKind.MREST: "Whole-bar rest",
    ElementKind.SLASH: "Slash",
    ElementKind.BAR_REPEAT: "Bar repeat",
    ElementKind.CLEF: "Clef",
    ElementKind.KEY_SIG: "Key signature",
    ElementKind.METER_SIG: "Time signature",
    ElementKind.BARLINE: "Barline",
    ElementKind.STAFF_LINES: "Staff lines",
    ElementKind.GROUP_SYMBOL: "Bracket",
    ElementKind.SYSTEM_DIVIDER: "System divider",
    ElementKind.LEDGER_LINES: "Ledger lines",
    ElementKind.LYRIC: "Lyric",
    ElementKind.CHORD_SYMBOL: "Chord symbol",
    ElementKind.TEXT: "Text",
    ElementKind.OTHER: "Element",
}

# Idle wording: what the bar rests on with nothing selected.
NO_RECORDING = "No recording loaded — File ▸ Open Audio…"

MOVE = "drag to move it"
RETIME = "drag its onset line to re-time it"
EDIT_TEXT = "double-click to edit the words"
FLIP_STEM = "F flips the stem"
DELETE = "Delete hides it"
BREAK = {
    SystemBreak.FORCE: "breaks the system after this bar",
    SystemBreak.SUPPRESS: "joins the next bar onto this system",
    None: "clears the break override here",
}

# The canonical break binding, used only when the caller does not say
# how the platform draws it (the UI passes Qt's native text: ⇧⌘B here).
BREAK_KEYS = "Ctrl+Shift+B"

MAX_PHRASES = 3


@dataclass(frozen=True)
class Gestures:
    """What the app would actually do to the current selection.

    Every field is an answer, not a question — the caller reads each one
    off the controller that owns that gesture. `break_mode` matters only
    when `break_offered` is set: it is what the toggle would write, and
    the three modes read as three different sentences.
    """
    move: bool = False
    retime: bool = False
    edit_text: bool = False
    flip_stem: bool = False
    delete: bool = False
    break_offered: bool = False
    break_mode: SystemBreak | None = None
    break_keys: str = BREAK_KEYS


def idle_hint(recording: str | None) -> str:
    """The resting line with nothing selected: the loaded recording."""
    return f"Recording: {recording}" if recording else NO_RECORDING


def hint_for(selection: Selection, gestures: Gestures = Gestures(),
             measures: Sequence[MeasureInfo] = ()) -> str:
    """The full line: what is selected, then what can be done to it."""
    subject = describe(selection, measures)
    phrases = phrases_for(gestures)
    return f"{subject} — {', '.join(phrases)}" if phrases else subject


def describe(selection: Selection,
             measures: Sequence[MeasureInfo] = ()) -> str:
    """"Note · Trumpets · m. 19" — the object and the context it carries
    (rule 13), dropping whichever levels it has none of."""
    parts = [KIND_LABELS.get(selection.kind, "Element")]
    part_name = selection.part_name or (
        str(selection.part) if selection.part is not None else None)
    if part_name:
        parts.append(part_name)
    measure = _measure_text(selection, measures)
    if measure:
        parts.append(measure)
    return " · ".join(parts)


def phrases_for(gestures: Gestures) -> tuple[str, ...]:
    """The gestures on offer, most direct first, capped at MAX_PHRASES."""
    out: list[str] = []
    if gestures.move:
        out.append(MOVE)
    if gestures.retime:
        out.append(RETIME)
    if gestures.edit_text:
        out.append(EDIT_TEXT)
    if gestures.flip_stem:
        out.append(FLIP_STEM)
    if gestures.delete:
        out.append(DELETE)
    if gestures.break_offered:
        out.append(f"{gestures.break_keys} {BREAK[gestures.break_mode]}")
    return tuple(out[:MAX_PHRASES])


def _measure_text(selection: Selection,
                  measures: Sequence[MeasureInfo]) -> str | None:
    """The measure as the page prints it. System-scoped ink and page
    furniture carry no measure at all, and say nothing rather than
    guessing one."""
    ordinal = selection.measure_ordinal
    if ordinal is None:
        return None
    if 1 <= ordinal <= len(measures):
        return f"m. {measures[ordinal - 1].number}"
    return f"m. {ordinal}"
