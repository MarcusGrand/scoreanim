"""Which stem `F` flips — the pure policy, headless (rule 1).

`tests/test_stem_flip_action.py` pins the wiring; this pins the
decisions. The awkward part, and the reason the module exists, is that
the user selects a NOTEHEAD while the document keys a STEM: the two are
joined through the schedule's note group, never stored.
"""
from __future__ import annotations

import pytest

from scoreanim.core.editing.stem_flip import (NO_SELECTION, NO_STEM,
                                              NOT_A_NOTE, SCAFFOLD_INK,
                                              FlipAction, is_flippable,
                                              resolve, stem_of)
from scoreanim.core.engraving.types import Layout
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_stems import StemDirection
from scoreanim.core.selection.context import Selection


def _pick(layout: Layout, kind: ElementKind, **want):
    for element in layout.elements:
        ident = element.identity
        if ident.kind is not kind:
            continue
        if all(getattr(ident, k) == v for k, v in want.items()):
            return element
    raise AssertionError(f"no {kind} matching {want}")


@pytest.fixture(scope="module")
def layout(engraved) -> Layout:
    return engraved.layout


# -- the join from what was clicked to what gets flipped --------------------

def test_a_notehead_resolves_to_its_own_stem(layout) -> None:
    stem = _pick(layout, ElementKind.STEM)
    head = next(el for el in layout.elements
                if el.identity.kind is ElementKind.NOTEHEAD
                and el.identity.part == stem.identity.part
                and el.identity.staff == stem.identity.staff
                and el.identity.voice == stem.identity.voice
                and el.identity.onset == stem.identity.onset)
    action = resolve(Selection(head.identity), layout)
    assert action.enabled
    assert action.element_id == stem.identity.element_id
    assert "note" in str(head.identity.element_id)      # non-vacuous:
    assert "stem" in str(action.element_id)             # they differ


def test_selecting_the_stem_itself_works_too(layout) -> None:
    stem = _pick(layout, ElementKind.STEM)
    action = resolve(Selection(stem.identity), layout)
    assert action.enabled and action.element_id == stem.identity.element_id


def test_every_head_of_a_chord_names_the_same_stem(layout) -> None:
    """A chord has ONE stem, so it does not matter which head was
    clicked — and that is also why the command needs no fan-out."""
    from collections import defaultdict
    groups = defaultdict(list)
    for el in layout.elements:
        i = el.identity
        if i.kind is ElementKind.NOTEHEAD:
            groups[(i.part, i.staff, i.voice, i.onset)].append(el)
    chord = next(heads for heads in groups.values() if len(heads) > 1)
    named = {resolve(Selection(h.identity), layout).element_id for h in chord}
    assert len(chord) > 1 and len(named) == 1


# -- the direction is READ off the ink, and F asks for the opposite ---------

def test_the_flip_asks_for_the_opposite_of_what_is_drawn(layout) -> None:
    from scoreanim.core.animation.scale_groups import (group_key,
                                                       heads_by_group,
                                                       stem_is_up)
    heads = heads_by_group(layout)
    seen = set()
    for el in layout.elements:
        if el.identity.kind is not ElementKind.STEM:
            continue
        group = heads.get(group_key(el.identity))
        if not group:
            continue
        drawn_up = stem_is_up(el, group)
        action = resolve(Selection(el.identity), layout)
        assert action.direction is (StemDirection.DOWN if drawn_up
                                    else StemDirection.UP)
        seen.add(drawn_up)
    # the fixture must contain BOTH directions or this proves nothing
    assert seen == {True, False}


# -- when it may not fire ---------------------------------------------------

def test_no_selection(layout) -> None:
    action = resolve(None, layout)
    assert not action.enabled and action.reason == NO_SELECTION
    assert action.element_id is None and action.direction is None


def test_no_layout_yet(layout) -> None:
    stem = _pick(layout, ElementKind.STEM)
    assert not resolve(Selection(stem.identity), None).enabled


@pytest.mark.parametrize("kind,reason", [
    (ElementKind.TEXT, NOT_A_NOTE),
    (ElementKind.DYNAMIC, NOT_A_NOTE),
    (ElementKind.REST, NOT_A_NOTE),
    (ElementKind.SLUR, NOT_A_NOTE),
    (ElementKind.BARLINE, SCAFFOLD_INK),
])
def test_ink_with_no_stem_of_its_own(layout, kind, reason) -> None:
    element = _pick(layout, kind)
    action = resolve(Selection(element.identity), layout)
    assert not action.enabled and action.reason == reason


def test_a_note_that_draws_no_stem_says_so(engraved_complex1) -> None:
    """A whole note has no stem to flip. Refuse with a reason rather
    than write an override that can never land. complex1 because it has
    45 whole notes and testscore has none."""
    from scoreanim.core.animation.scale_groups import group_key
    other = engraved_complex1.layout
    stemmed = {group_key(el.identity) for el in other.elements
               if el.identity.kind is ElementKind.STEM}
    bare = next(el for el in other.elements
                if el.identity.kind is ElementKind.NOTEHEAD
                and group_key(el.identity) not in stemmed)
    action = resolve(Selection(bare.identity), other)
    assert not action.enabled and action.reason == NO_STEM


# -- the table ---------------------------------------------------------------

@pytest.mark.parametrize("kind,flippable", [
    (ElementKind.NOTEHEAD, True),
    (ElementKind.STEM, True),
    (ElementKind.FLAG, True),
    (ElementKind.BEAM, False),      # a beam belongs to several notes
    (ElementKind.REST, False),
    (ElementKind.TEXT, False),
    (ElementKind.STAFF_LINES, False),
    (None, False),
])
def test_which_kinds_are_flippable(kind, flippable) -> None:
    assert is_flippable(kind) is flippable


def test_a_disabled_action_carries_nothing_to_act_on() -> None:
    action = FlipAction(reason=NOT_A_NOTE)
    assert not action.enabled
    assert action.element_id is None and action.direction is None


def test_stem_of_returns_none_when_the_group_has_no_stem(layout) -> None:
    text = _pick(layout, ElementKind.TEXT)
    assert stem_of(text.identity, layout) is None
