"""SelectionController (M2.3/M2.4) against a real testscore load,
offscreen.

Candidate collection, the click->identity path, and the highlight
overlay's lifetime. The hit-priority ORDER itself is pinned purely in
tests/test_hit_priority.py; here we check the Qt half feeds it the right
data and acts on the answer.
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


# -- highlight overlay (M2.4) -------------------------------------------

def test_overlay_appears_in_the_elements_own_page_scene(controller) -> None:
    ctrl, state, loaded = controller
    note = _first(loaded, ElementKind.NOTEHEAD)
    ctrl.select_at(_centre(loaded, note))
    overlay = ctrl.overlay
    assert overlay is not None
    item = loaded.scenes.items[note.identity.element_id]
    assert overlay.scene() is item.scene()
    assert overlay.scene() is loaded.scenes.scene_for_page(note.page)


def test_overlay_is_not_an_addressable_element(controller) -> None:
    """It must never enter the element registry — nothing may resolve it
    as score ink, tint it, or animate it."""
    ctrl, _, loaded = controller
    ctrl.select_at(_centre(loaded, _first(loaded, ElementKind.NOTEHEAD)))
    assert ctrl.overlay not in loaded.scenes.items.values()


def test_exactly_one_overlay_survives_repeated_selection(controller) -> None:
    ctrl, _, loaded = controller
    layout = loaded.animation_inputs.layout
    notes = [el for el in layout.elements
             if el.identity.kind is ElementKind.NOTEHEAD][:4]
    for note in notes:
        ctrl.select_at(_centre(loaded, note))
    scenes = {s for s in loaded.scenes.scenes}
    overlays = [it for s in scenes for it in s.items()
                if it is ctrl.overlay]
    assert len(overlays) == 1


def test_deselect_removes_the_overlay(controller) -> None:
    ctrl, state, loaded = controller
    ctrl.select_at(_centre(loaded, _first(loaded, ElementKind.NOTEHEAD)))
    assert ctrl.overlay is not None
    ctrl.clear()
    assert ctrl.overlay is None
    assert state.selected is None


def test_overlay_contains_the_visible_ink(controller) -> None:
    """The box is built from childrenBoundingRect, not the authored
    bbox, so it actually surrounds what you see (M2.0 finding B: the
    authored rect underruns curved spanners and text)."""
    ctrl, state, loaded = controller
    slur = _first(loaded, ElementKind.SLUR)
    item = loaded.scenes.items[slur.identity.element_id]
    # set the selection directly: this is about the overlay's geometry,
    # not about hit-testing (a slur's bbox CENTRE is the air under its
    # arc, so clicking there legitimately selects a neighbour).
    state.set_selection(item.identity)
    assert ctrl.overlay is not None
    assert ctrl.overlay.rect().contains(item.childrenBoundingRect())
    # and the authored bbox would NOT have contained it — the reason
    # childrenBoundingRect is used (M2.0 finding B)
    assert not item.bbox.contains(item.childrenBoundingRect())


# -- lifecycle -----------------------------------------------------------

def test_bind_scenes_clears_selection_and_drops_the_overlay(
        controller) -> None:
    """A re-engrave rebuilds every ElementItem; the held identity would
    point at objects that no longer exist."""
    ctrl, state, loaded = controller
    ctrl.select_at(_centre(loaded, _first(loaded, ElementKind.NOTEHEAD)))
    assert state.selected is not None and ctrl.overlay is not None
    ctrl.bind_scenes(loaded.scenes)
    assert state.selected is None
    assert ctrl.overlay is None


def test_selection_survives_a_page_flip(controller) -> None:
    """D2, pinned: scenes are all retained and the overlay lives in its
    element's own page scene, so browsing other pages neither clears the
    selection nor destroys the highlight. Flip back and it is there."""
    ctrl, state, loaded = controller
    note = _first(loaded, ElementKind.NOTEHEAD)
    ctrl.select_at(_centre(loaded, note))
    held, overlay = state.selected, ctrl.overlay
    page_scene = loaded.scenes.scene_for_page(note.page)
    # "flip": the window swaps which scene the view shows; the
    # controller and the scenes are untouched
    for page in range(1, loaded.scenes.page_count + 1):
        loaded.scenes.scene_for_page(page)
    assert state.selected == held
    assert ctrl.overlay is overlay
    assert overlay.scene() is page_scene
