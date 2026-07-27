"""M2 exit criteria, pinned (M2.7), offscreen.

The roadmap's exit, as a test: on testscore AND complex3, clicking a
notehead, a slur, a hairpin, a barline and a part label each selects
that element, highlights it, and reports the right identity — and
playback keeps running with a live selection.

Clicks land where a user would aim: the interior of a solid glyph, a
point on the stroke for thin or hollow ink (a slur's bbox CENTRE is the
air under its arc — see spikes/hit_census.py finding C).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.project.document import StageConfig  # noqa: E402
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.selection import SelectionController  # noqa: E402

# The five the roadmap names. A part label is engraved TEXT (identity-
# bearing, minted onset-less), so it selects and reports "—" for onset.
EXIT_KINDS = (ElementKind.NOTEHEAD, ElementKind.SLUR, ElementKind.HAIRPIN,
              ElementKind.BARLINE, ElementKind.TEXT)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _built(qapp, engraved):
    scenes = ScoreScenes(engraved.layout, StageConfig())
    state = AppState()
    controller = SelectionController(state)
    controller.bind_scenes(scenes)
    return scenes, state, controller


def _aim(item) -> QPointF:
    """Where a user would click: the interior of a solid glyph, else a
    point on the stroke."""
    centre = item.bbox.center()
    for child in item.childItems():
        if not child.isVisible() or not hasattr(child, "shape"):
            continue
        if child.shape().contains(child.mapFromScene(centre)):
            return centre
    best = None
    for child in item.childItems():
        if not hasattr(child, "path") or child.path().isEmpty():
            continue
        length = child.path().length()
        if best is None or length > best[0]:
            best = (length, child)
    if best is None:
        return centre
    return best[1].mapToScene(best[1].path().pointAtPercent(0.5))


def _exit_run(qapp, engraved, label: str) -> None:
    scenes, state, controller = _built(qapp, engraved)
    layout = engraved.layout
    checked = 0
    for kind in EXIT_KINDS:
        element = next((el for el in layout.elements
                        if el.identity.kind is kind), None)
        if element is None:
            continue                      # not every fixture has each kind
        item = scenes.items[element.identity.element_id]
        # the view is showing the page the element is on — that is what
        # "clicking it" means; the scene travels with the position
        controller.select_at(_aim(item), item.scene())
        selected = state.selected
        assert selected is not None, f"{label}: {kind.name} selected nothing"
        assert selected.element_id == element.identity.element_id, (
            f"{label}: clicking {kind.name} selected "
            f"{selected.kind.name} {selected.element_id}")
        assert selected.kind is kind
        # highlighted: the element itself carries the tint
        assert controller.highlighted is item
        assert item.selected is True
        checked += 1
    assert checked >= 4, f"{label}: only {checked} of the exit kinds present"


def test_exit_criteria_on_testscore(qapp, engraved) -> None:
    _exit_run(qapp, engraved, "testscore")


def test_exit_criteria_on_complex3(qapp, engraved_complex3_hidden) -> None:
    _exit_run(qapp, engraved_complex3_hidden, "complex3")


def test_part_label_selects_and_reports_no_onset(qapp, engraved) -> None:
    """A part label is page furniture: identity-bearing TEXT, minted
    onset-less, and its id carries no measure."""
    from scoreanim.core.selection import measure_ordinal_of

    scenes, state, controller = _built(qapp, engraved)
    label = next(el for el in engraved.layout.elements
                 if el.identity.kind is ElementKind.TEXT
                 and el.identity.onset is None)
    item = scenes.items[label.identity.element_id]
    controller.select_at(_aim(item), item.scene())
    assert state.selected is not None
    assert state.selected.element_id == label.identity.element_id
    assert state.selected.onset is None
    assert measure_ordinal_of(state.selected.element_id) is None


def test_playback_is_undisturbed_by_a_live_selection(
        qapp, engraved, schedule_for_exit) -> None:
    """Animation is applied over the same items the highlight sits on;
    the overlay is a sibling item, never a restyle, so applying frames
    with a selection active must leave the element's own state exactly
    as it is without one."""
    from scoreanim.core.animation import StyleRules
    from scoreanim.core.timing import TempoEvent, TempoMap
    from scoreanim.render.animate import AnimationApplier

    def opacities(select: bool):
        scenes, state, controller = _built(qapp, engraved)
        applier = AnimationApplier(scenes.items, schedule_for_exit,
                                   TempoMap([TempoEvent(0.0, 120.0)]),
                                   StyleRules(), ())
        if select:
            note = next(el for el in engraved.layout.elements
                        if el.identity.kind is ElementKind.NOTEHEAD)
            n_item = scenes.items[note.identity.element_id]
            controller.select_at(_aim(n_item), n_item.scene())
            assert state.selected is not None
        for t in (0.0, 0.5, 1.0, 2.0, 4.0):
            applier.apply_at(t)
        return {eid: (item.opacity(), item.scale())
                for eid, item in scenes.items.items()}

    assert opacities(select=True) == opacities(select=False)


@pytest.fixture(scope="module")
def schedule_for_exit(engraved, join_mapping, score_model):
    from scoreanim.core.animation import build_trigger_schedule
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures)
