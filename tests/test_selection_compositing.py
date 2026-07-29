"""The selection compositing rule (M2.8), pinned on a real load.

    Selection composites LAST and modifies only the two channels it
    needs. An element's painted appearance is a function of three inputs
    in fixed order — authored color (document intent) -> animation state
    (opacity/scale) -> selection (transient). Selection replaces the
    color and raises an opacity floor; it never touches scale, never
    touches the reveal clip, and never writes back into the first two.
    Deselecting re-derives the composite of the first two; nothing is
    remembered.

Each measurement behind that sentence is a test here.
"""
from __future__ import annotations

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import StyleRules  # noqa: E402
from scoreanim.core.animation.style import ElementStyle  # noqa: E402
from scoreanim.core.project import ProjectDoc  # noqa: E402
from scoreanim.core.project.document import StageConfig  # noqa: E402
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.core.selection.highlight import (  # noqa: E402
    SELECTION_ALT_COLOR, SELECTION_COLOR, SELECTION_MIN_OPACITY)
from scoreanim.core.timing import TempoEvent, TempoMap  # noqa: E402
from scoreanim.render.animate import AnimationApplier  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def scenes(qapp, engraved):
    return ScoreScenes(engraved.layout, StageConfig())


def _first(engraved, kind: ElementKind):
    return next(el for el in engraved.layout.elements
                if el.identity.kind is kind)


def _painted(item) -> str:
    """The color actually on the ink, read off a color-tracking child."""
    child = item._tracked[0][0]
    return child.brush().color().name()


# -- color: selection replaces, never overwrites -------------------------

def test_selection_replaces_the_painted_color(scenes, engraved) -> None:
    item = scenes.items[_first(engraved, ElementKind.NOTEHEAD)
                        .identity.element_id]
    assert _painted(item) == "#000000"
    item.set_selected(True)
    assert _painted(item) == SELECTION_COLOR


def test_the_authored_color_survives_underneath(scenes, engraved) -> None:
    """The load-bearing one. DocumentSync's style pass is a diff cache,
    so if selection overwrote the authored color the cache would believe
    a color it could no longer restore."""
    item = scenes.items[_first(engraved, ElementKind.NOTEHEAD)
                        .identity.element_id]
    item.set_color(QColor("#3366cc"))
    item.set_selected(True)
    assert _painted(item) == SELECTION_COLOR
    assert item.color.name() == "#3366cc"      # intent, untouched
    item.set_selected(False)
    assert _painted(item) == "#3366cc"         # re-derived, not remembered


def test_a_tint_applied_while_selected_lands_when_deselected(
        scenes, engraved) -> None:
    """Order-independence: the document may change under a live
    selection, and the element must end up right either way."""
    item = scenes.items[_first(engraved, ElementKind.NOTEHEAD)
                        .identity.element_id]
    item.set_selected(True)
    item.set_color(QColor("#3366cc"))
    assert _painted(item) == SELECTION_COLOR   # selection still wins
    item.set_selected(False)
    assert _painted(item) == "#3366cc"


def test_an_orange_element_is_still_visibly_selected(scenes,
                                                     engraved) -> None:
    """M3's constraint, met today: a user who colors a note the
    selection color must still be able to tell it is selected."""
    item = scenes.items[_first(engraved, ElementKind.NOTEHEAD)
                        .identity.element_id]
    item.set_color(QColor(SELECTION_COLOR))
    item.set_selected(True)
    assert _painted(item) == SELECTION_ALT_COLOR
    assert _painted(item) != item.color.name()   # tellable apart


def test_diff_sync_is_undisturbed_by_a_live_selection(scenes,
                                                      engraved) -> None:
    """The whole DocumentSync path, not just set_color: a sync pass that
    runs while an element is lit must neither be confused by the tint nor
    lose the intent it is caching."""
    from scoreanim.ui.document_sync import DocumentSync

    note = _first(engraved, ElementKind.NOTEHEAD)
    item = scenes.items[note.identity.element_id]

    class _Menu:
        def part_ids(self):
            return [note.identity.part]

        def sync_checks(self, pid, rule):
            pass

    sync = DocumentSync(_Menu())
    sync.bind_scenes(scenes, ())
    doc = ProjectDoc()
    doc = replace(doc, style=replace(
        doc.style,
        parts={note.identity.part: ElementStyle(color="#3366cc")}))

    sync.sync_styles(doc)
    assert _painted(item) == "#3366cc"
    item.set_selected(True)
    sync.sync_styles(doc)                        # no-op diff pass, lit
    assert _painted(item) == SELECTION_COLOR
    assert item.color.name() == "#3366cc"
    item.set_selected(False)
    assert _painted(item) == "#3366cc"


# -- opacity: selection raises a floor -----------------------------------

@pytest.fixture()
def popping(qapp, engraved, schedule_for_compositing):
    """A scene + applier whose default effect is pop, at a given floor."""
    built = []                    # retained: dropping the ScoreScenes
                                  # deletes the C++ items under the applier
    def build(floor: float):
        style = StyleRules(floor_opacity=floor, default_effect="pop")
        s = ScoreScenes(engraved.layout, StageConfig(), ghost_opacity=floor)
        built.append(s)
        applier = AnimationApplier(s.items, schedule_for_compositing,
                                   TempoMap([TempoEvent(0.0, 120.0)]),
                                   style, ())
        note = _first(engraved, ElementKind.NOTEHEAD)
        eid = note.identity.element_id
        trigger = next(applier._trigger_seconds[i]
                       for i, tr in enumerate(
                           schedule_for_compositing.triggers)
                       if eid in tr.element_ids)
        return s.items[eid], applier, trigger
    return build


@pytest.mark.parametrize("floor", [0.3, 0.0])
def test_a_selection_stays_visible_across_the_whole_envelope(
        popping, floor: float) -> None:
    """M1. Including at floor 0, where the ghost score is invisible and
    an unfloored tint would be a tint on nothing."""
    item, applier, trigger = popping(floor)
    item.set_selected(True)
    for dt in (-1.0, -0.25, -0.05, 0.0, 0.05, 0.15, 0.3, 0.6, 1.5):
        applier.refresh(trigger + dt)
        assert item.opacity() >= SELECTION_MIN_OPACITY, f"at t{dt:+}"


@pytest.mark.parametrize("floor", [0.3, 0.0])
def test_selection_never_dims_an_element_the_animation_had_lit(
        popping, floor: float) -> None:
    """A floor, not an override: past the trigger the element is at 1.0
    and selection leaves it there."""
    item, applier, trigger = popping(floor)
    applier.refresh(trigger + 0.5)
    assert item.opacity() == pytest.approx(1.0)
    item.set_selected(True)
    assert item.opacity() == pytest.approx(1.0)


@pytest.mark.parametrize("floor", [0.3, 0.0])
def test_the_animation_input_is_untouched_underneath(popping,
                                                     floor: float) -> None:
    """The evaluator keeps writing what it always wrote; only the
    composite differs. Deselecting restores it exactly."""
    item, applier, trigger = popping(floor)
    applier.refresh(trigger - 0.3)
    item.set_selected(True)
    assert item.animated_opacity == pytest.approx(floor)
    item.set_selected(False)
    assert item.opacity() == pytest.approx(floor)


def test_scale_is_untouched_by_selection(popping) -> None:
    """M8. Selection owns color and an opacity floor — nothing else. The
    old bbox overlay deliberately did NOT follow a pop; the tint does,
    for free, because it is on the ink."""
    item, applier, trigger = popping(0.3)
    unselected = []
    for dt in (-0.05, 0.0, 0.05, 0.15, 0.3, 0.6):
        applier.refresh(trigger + dt)
        unselected.append(item.scale())
    item.set_selected(True)
    selected = []
    for dt in (-0.05, 0.0, 0.05, 0.15, 0.3, 0.6):
        applier.refresh(trigger + dt)
        selected.append(item.scale())
    assert selected == unselected
    assert max(selected) > 1.0            # non-vacuous: it really pops


# -- the reveal clip: sidestepped, not fought ----------------------------

@pytest.mark.parametrize("floor", [0.3, 0.0])
def test_selecting_an_unrevealed_spanner_lifts_its_ghost(
        qapp, engraved, floor: float) -> None:
    """M2. A spanner reveals by clip-grow over a dimmed ghost of the
    whole curve, and the ghost's opacity MULTIPLIES the parent's — so at
    floor 0 a parent-only floor would still composite to nothing. The
    ghost carries the tint, which is why selection never has to fight
    the clip."""
    scenes = ScoreScenes(engraved.layout, StageConfig(), ghost_opacity=floor)
    item = scenes.items[_first(engraved, ElementKind.SLUR)
                        .identity.element_id]
    ghosts = [c for c in item.childItems() if not hasattr(c, "clip_right")]
    assert ghosts, "a spanner should have ghost children"

    def visible_alpha() -> float:
        return item.opacity() * ghosts[0].opacity()

    assert visible_alpha() == pytest.approx(floor)
    item.set_selected(True)
    assert visible_alpha() >= SELECTION_MIN_OPACITY
    item.set_selected(False)
    assert visible_alpha() == pytest.approx(floor)


def test_selection_does_not_move_the_reveal_edge(qapp, engraved) -> None:
    """Selecting a spanner must not reveal it early — the clip is the
    evaluator's, and selection never touches it."""
    scenes = ScoreScenes(engraved.layout, StageConfig())
    item = scenes.items[_first(engraved, ElementKind.SLUR)
                        .identity.element_id]
    before = [c.clip_right for c in item.reveal_children]
    item.set_selected(True)
    assert [c.clip_right for c in item.reveal_children] == before


def test_the_document_ghost_floor_still_reaches_a_selected_element(
        qapp, engraved) -> None:
    """Ghost opacity is now owned by the item so it can compose with
    selection; the document must still be able to change it underneath a
    live selection, and have it take effect on deselect."""
    scenes = ScoreScenes(engraved.layout, StageConfig(), ghost_opacity=0.3)
    item = scenes.items[_first(engraved, ElementKind.SLUR)
                        .identity.element_id]
    ghosts = [c for c in item.childItems() if not hasattr(c, "clip_right")]
    item.set_selected(True)
    scenes.set_ghost_opacity(0.6)
    assert ghosts[0].opacity() >= SELECTION_MIN_OPACITY   # still lit
    item.set_selected(False)
    assert ghosts[0].opacity() == pytest.approx(0.6)      # doc value lands


@pytest.fixture(scope="module")
def schedule_for_compositing(engraved, join_mapping, score_model):
    from scoreanim.core.animation import build_trigger_schedule
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures)


# -- every visible element tints, including the ones Verovio fills black --
#
# The gap this closes (Marcus, 2026-07-29): selecting the expression
# text "bucket mute" went from dimmed to BLACK instead of orange. Its
# runs carry an explicit fill="#000000" from Verovio, and the render
# layer read any explicit fill as an authored colour choice not to be
# overwritten — so the ink tracked nothing and the tint had nowhere to
# land. Black is not a choice; it is the default written out.

def test_a_black_filled_text_run_still_takes_the_tint(scenes,
                                                      engraved) -> None:
    direction = next(el for el in engraved.layout.elements
                     if el.text_class == "dir")
    # non-vacuous: this is the element with the explicit fill
    assert any(run.fill == "#000000"
               for prim in direction.glyph.texts for run in prim.runs)

    item = scenes.items[direction.identity.element_id]
    assert item._tracked                       # it tracks something now
    assert _painted(item) == "#000000"
    item.set_selected(True)
    assert _painted(item) == SELECTION_COLOR
    item.set_selected(False)
    assert _painted(item) == "#000000"


def test_every_element_with_ink_can_show_a_selection(scenes) -> None:
    """The general form: an element nobody can see selected is a bug,
    whatever kind it is."""
    unshowable = [str(eid) for eid, item in scenes.items.items()
                  if item.identity is not None and item.childItems()
                  and not item._tracked]
    assert unshowable == []


def test_an_authored_colour_is_still_never_overwritten(qapp) -> None:
    """The rule that made explicit fills untracked in the first place
    still holds for real colour choices — only black is exempt."""
    from scoreanim.render.items import fill_tracks_color

    assert fill_tracks_color(None) is True          # SVG said nothing
    assert fill_tracks_color("#000000") is True     # the default, written out
    assert fill_tracks_color("black") is True
    assert fill_tracks_color("none") is False       # nothing to paint
    assert fill_tracks_color("#808080") is False    # a choice
    assert fill_tracks_color("#ff6a00") is False
