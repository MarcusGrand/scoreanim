"""SelectionController (M2.3/M2.4, highlight reworked M2.8) against a
real testscore load, offscreen.

Candidate collection, the click->identity path, and the highlight's
lifetime. The hit-priority ORDER itself is pinned purely in
tests/test_hit_priority.py, and the compositing RULE the highlight obeys
in tests/test_selection_compositing.py; here we check the Qt half feeds
the policy the right data, acts on the answer, and moves the tint to
exactly one element.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import StyleRules  # noqa: E402
from scoreanim.core.engraving.types import EngravingParams  # noqa: E402
from scoreanim.core.project import ProjectDoc  # noqa: E402
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.score_loader import ScoreLoader  # noqa: E402
from scoreanim.ui.selection import SelectionController  # noqa: E402

TESTSCORE = Path(__file__).parent.parent / "testdata" / "testscore.musicxml"


@pytest.fixture(scope="module")
def loaded():
    QApplication.instance() or QApplication([])
    loader = ScoreLoader()
    return loader.load(TESTSCORE, EngravingParams(), None, StyleRules(),
                       hide_empty_staves=ProjectDoc().hide_empty_staves)


@pytest.fixture()
def controller(loaded):
    # the scenes are module-scoped, so start each test from an unlit
    # one: a controller discarded mid-selection leaves its element
    # marked (in the app there is one controller for the window's life,
    # and bind_scenes unmarks)
    for item in loaded.scenes.items.values():
        item.set_selected(False)
    state = AppState()
    ctrl = SelectionController(state)
    ctrl.bind_scenes(loaded.scenes)
    return ctrl, state, loaded


def _first(loaded, kind: ElementKind):
    return next(el for el in loaded.animation_inputs.layout.elements
                if el.identity.kind is kind)


def _centre(loaded, element) -> QPointF:
    item = loaded.scenes.items[element.identity.element_id]
    return item.bbox.center()


# -- candidate collection ------------------------------------------------

def test_candidates_at_a_notehead_include_it(controller) -> None:
    ctrl, _, loaded = controller
    note = _first(loaded, ElementKind.NOTEHEAD)
    cands = ctrl.candidates_at(_centre(loaded, note))
    assert note.identity.element_id in {c.element_id for c in cands}


def test_candidates_carry_engraved_area_and_exactness(controller) -> None:
    ctrl, _, loaded = controller
    note = _first(loaded, ElementKind.NOTEHEAD)
    cands = ctrl.candidates_at(_centre(loaded, note))
    mine = next(c for c in cands
                if c.element_id == note.identity.element_id)
    assert mine.kind is ElementKind.NOTEHEAD
    assert mine.area == pytest.approx(
        note.bbox.w * note.bbox.h, rel=1e-6)     # authored, not Qt bounds
    assert mine.exact is True                    # clicked inside the glyph


def test_empty_paper_yields_no_candidates(controller) -> None:
    ctrl, _, _ = controller
    assert ctrl.candidates_at(QPointF(2.0, 2.0)) == []


def test_group_parents_are_hit_transparent(controller) -> None:
    """M2.3(a): without the GroupItem.shape() override every parent
    answers across its children's united bbox, so a notehead click also
    returned the staff lines and the part label (M2.0 finding A). The
    click is inside the notehead glyph, so no scaffold should be an
    EXACT hit there."""
    ctrl, _, loaded = controller
    note = _first(loaded, ElementKind.NOTEHEAD)
    cands = ctrl.candidates_at(_centre(loaded, note))
    exact_kinds = {c.kind for c in cands if c.exact}
    assert ElementKind.TEXT not in exact_kinds


# -- click -> selection --------------------------------------------------

def test_click_on_a_notehead_selects_it(controller) -> None:
    ctrl, state, loaded = controller
    note = _first(loaded, ElementKind.NOTEHEAD)
    ctrl.select_at(_centre(loaded, note))
    assert state.selected is not None
    assert state.selected.element_id == note.identity.element_id
    assert state.selected.kind is ElementKind.NOTEHEAD


def test_click_on_empty_paper_clears(controller) -> None:
    ctrl, state, loaded = controller
    ctrl.select_at(_centre(loaded, _first(loaded, ElementKind.NOTEHEAD)))
    assert state.selected is not None
    ctrl.select_at(QPointF(2.0, 2.0))
    assert state.selected is None


def test_hidden_elements_stop_hitting(controller) -> None:
    """scene.items() returns only visible items, so an element hidden by
    a tempo overlay (LayoutOverride.hidden) drops out for free."""
    ctrl, _, loaded = controller
    note = _first(loaded, ElementKind.NOTEHEAD)
    eid = note.identity.element_id
    pos = _centre(loaded, note)
    assert eid in {c.element_id for c in ctrl.candidates_at(pos)}
    loaded.scenes.set_element_hidden(eid, True)
    try:
        assert eid not in {c.element_id for c in ctrl.candidates_at(pos)}
    finally:
        loaded.scenes.set_element_hidden(eid, False)


# -- highlight (M2.8: the tint, superseding M2.4's outline) -------------

def test_the_highlight_is_the_selected_element_itself(controller) -> None:
    """No overlay item any more: the controller marks the element, and
    the element paints itself. There is nothing to add to a scene, and
    so nothing that could be mistaken for score ink."""
    ctrl, _, loaded = controller
    note = _first(loaded, ElementKind.NOTEHEAD)
    ctrl.select_at(_centre(loaded, note))
    item = loaded.scenes.items[note.identity.element_id]
    assert ctrl.highlighted is item
    assert item.selected is True


def test_exactly_one_element_is_lit_at_a_time(controller) -> None:
    """The invariant the old test spelled as "one overlay survives"."""
    ctrl, _, loaded = controller
    layout = loaded.animation_inputs.layout
    notes = [el for el in layout.elements
             if el.identity.kind is ElementKind.NOTEHEAD][:4]
    for note in notes:
        ctrl.select_at(_centre(loaded, note))
    lit = [item for item in loaded.scenes.items.values() if item.selected]
    assert len(lit) == 1
    assert lit[0] is ctrl.highlighted


def test_deselect_unlights_the_element(controller) -> None:
    ctrl, state, loaded = controller
    ctrl.select_at(_centre(loaded, _first(loaded, ElementKind.NOTEHEAD)))
    item = ctrl.highlighted
    assert item is not None
    ctrl.clear()
    assert ctrl.highlighted is None
    assert item.selected is False
    assert state.selected is None
    assert not any(i.selected for i in loaded.scenes.items.values())


def test_the_highlight_covers_the_ink_you_can_see(controller) -> None:
    """The M2.0 finding B problem — the authored bbox underruns a curved
    spanner's real extent by up to 3.7x in area — does not arise for a
    tint: the highlight IS the ink, so it covers exactly what is drawn,
    whatever shape that is."""
    ctrl, state, loaded = controller
    slur = _first(loaded, ElementKind.SLUR)
    item = loaded.scenes.items[slur.identity.element_id]
    # set the selection directly: this is about what gets lit, not about
    # hit-testing (a slur's bbox CENTRE is the air under its arc, so
    # clicking there legitimately selects a neighbour).
    state.set_selection(item.identity)
    assert item.selected is True
    assert not item.bbox.contains(item.childrenBoundingRect())   # as before
    assert ctrl.highlighted is item


def test_the_highlight_adds_nothing_to_any_scene(controller) -> None:
    """What the overlay had to be tested for, now true by construction:
    selecting changes no scene's item count, so nothing can leak into a
    render as an extra object."""
    ctrl, _, loaded = controller
    before = [len(s.items()) for s in loaded.scenes.scenes]
    ctrl.select_at(_centre(loaded, _first(loaded, ElementKind.NOTEHEAD)))
    assert [len(s.items()) for s in loaded.scenes.scenes] == before
    ctrl.clear()
    assert [len(s.items()) for s in loaded.scenes.scenes] == before


# -- lifecycle -----------------------------------------------------------

def test_bind_scenes_clears_selection_and_unlights(controller) -> None:
    """A re-engrave rebuilds every ElementItem; the held identity would
    point at objects that no longer exist."""
    ctrl, state, loaded = controller
    ctrl.select_at(_centre(loaded, _first(loaded, ElementKind.NOTEHEAD)))
    assert state.selected is not None and ctrl.highlighted is not None
    ctrl.bind_scenes(loaded.scenes)
    assert state.selected is None
    assert ctrl.highlighted is None
    assert not any(i.selected for i in loaded.scenes.items.values())


def test_selection_survives_a_page_flip(controller) -> None:
    """D2, pinned: scenes are all retained and the tint lives on the
    element itself, so browsing other pages neither clears the selection
    nor disturbs the highlight. Flip back and it is there."""
    ctrl, state, loaded = controller
    note = _first(loaded, ElementKind.NOTEHEAD)
    ctrl.select_at(_centre(loaded, note))
    held, item = state.selected, ctrl.highlighted
    page_scene = loaded.scenes.scene_for_page(note.page)
    # "flip": the window swaps which scene the view shows; the
    # controller and the scenes are untouched
    for page in range(1, loaded.scenes.page_count + 1):
        loaded.scenes.scene_for_page(page)
    assert state.selected == held
    assert ctrl.highlighted is item
    assert item.selected is True
    assert item.scene() is page_scene
