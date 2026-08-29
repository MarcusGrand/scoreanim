"""What the hint bar says, headless.

The wording module is pure, so every sentence the bar can produce is
checked here on hand-built selections; the wiring — that the right
gestures are true for a real click on a real score — is
tests/test_hint_bar.py.

The point of the split is that this file can be read as the app's
vocabulary: one place to see every phrase, and a pin that no
ElementKind is left without a plain name.
"""
from __future__ import annotations

import pytest

from scoreanim.core.editing.hints import (BREAK, DELETE, EDIT_TEXT,
                                          FLIP_STEM, KIND_LABELS,
                                          MAX_PHRASES, MOVE, NO_RECORDING,
                                          RETIME, Gestures, describe,
                                          hint_for, idle_hint, phrases_for)
from scoreanim.core.project.document import SystemBreak
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind)
from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.selection.context import Selection


def _selection(kind: ElementKind = ElementKind.NOTEHEAD,
               eid: str = "P1:m19:s1:v1:note:0",
               part_name: str | None = "Trumpets") -> Selection:
    return Selection(ElementIdentity(
        element_id=ElementId(eid), kind=kind, part=None,
        part_name=part_name, staff=1, voice=1, onset=0.0))


def _measures(count: int, first_number: int = 1) -> tuple[MeasureInfo, ...]:
    return tuple(MeasureInfo(number=first_number + i, start=float(i * 4),
                             quarter_length=4.0) for i in range(count))


# -- the subject ------------------------------------------------------------

def test_the_subject_is_the_object_then_what_it_carries():
    assert describe(_selection(), _measures(20)) == "Note · Trumpets · m. 19"


def test_a_missing_level_is_left_out_rather_than_dashed():
    """Score-level ink has no part; page furniture has no measure. The
    panel prints "—" for those because it has a row to fill; a sentence
    just says less."""
    assert describe(_selection(ElementKind.BARLINE, "score:m19:barline:0",
                               part_name=None)) == "Barline · m. 19"
    assert describe(_selection(ElementKind.TEXT, "P1:text:label:0")) \
        == "Text · Trumpets"


def test_the_measure_is_the_printed_number_not_the_ordinal():
    """A Dorico "X0" pickup makes the two differ for a whole score, and
    the bar names what is printed on the page in front of you."""
    printed = describe(_selection(), _measures(20, first_number=0))
    assert printed.endswith("m. 18")


def test_an_ordinal_past_the_measure_table_still_says_something():
    """A selection can outlive a re-engrave that shortened the score."""
    assert describe(_selection(), _measures(3)).endswith("m. 19")


def test_every_kind_has_a_plain_name():
    """A new ElementKind should be named by a person. Without this the
    fallback would quietly ship "Ledger Lines"-style title case."""
    assert set(KIND_LABELS) == set(ElementKind)
    assert KIND_LABELS[ElementKind.NOTEHEAD] == "Note"


# -- the gestures -----------------------------------------------------------

def test_no_gestures_means_the_subject_alone():
    """A rest is neither nudgeable, re-timeable, deletable nor
    flippable — so the bar says what it is and promises nothing."""
    assert hint_for(_selection(ElementKind.REST), Gestures(),
                    _measures(20)) == "Rest · Trumpets · m. 19"


def test_a_note_offers_the_flip():
    line = hint_for(_selection(), Gestures(flip_stem=True), _measures(20))
    assert line == f"Note · Trumpets · m. 19 — {FLIP_STEM}"


def test_phrases_run_pointer_first_then_keys():
    assert phrases_for(Gestures(delete=True, move=True, flip_stem=True)) \
        == (MOVE, FLIP_STEM, DELETE)


def test_at_most_three_phrases():
    """A text can do four things at once; the bar is one line and the
    menus stay the complete list."""
    everything = Gestures(move=True, retime=True, edit_text=True,
                          flip_stem=True, delete=True, break_offered=True)
    assert phrases_for(everything) == (MOVE, RETIME, EDIT_TEXT)
    assert len(phrases_for(everything)) == MAX_PHRASES


@pytest.mark.parametrize("mode", [SystemBreak.FORCE, SystemBreak.SUPPRESS,
                                  None])
def test_the_break_says_which_of_its_three_things_it_would_do(mode):
    """The toggle renames itself in the menu for the same reason: force,
    remove and clear are three different edits on one key."""
    phrase, = phrases_for(Gestures(break_offered=True, break_mode=mode,
                                   break_keys="⇧⌘B"))
    assert phrase == f"⇧⌘B {BREAK[mode]}"


def test_the_break_mode_is_ignored_when_the_break_is_not_offered():
    assert phrases_for(Gestures(break_mode=SystemBreak.FORCE)) == ()


# -- the idle line ----------------------------------------------------------

def test_idle_names_the_recording():
    assert idle_hint("take3.wav") == "Recording: take3.wav"


def test_idle_with_no_recording_says_where_to_get_one():
    assert idle_hint(None) == NO_RECORDING
    assert "Open Audio" in NO_RECORDING
