"""The recolour pass: what it reaches, what it must not disturb, and the
proof that leaving it alone changes nothing.

Headless via the offscreen Qt platform. The scenes here are built per
test rather than shared, because a recolour is global by definition and
a leaked white ink would quietly break every test that runs after it.
"""
from __future__ import annotations

import hashlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import (QApplication,  # noqa: E402
                               QGraphicsPathItem, QGraphicsSimpleTextItem)

from scoreanim.core.animation import StyleRules  # noqa: E402
from scoreanim.core.animation.style import ElementStyle  # noqa: E402
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import (ElementId,  # noqa: E402
                                           ElementKind, PartId)
from scoreanim.render.scene import ScoreScenes, apply_style_colors  # noqa: E402

WHITE = QColor("#ffffff")
BLACK = QColor("#000000")
PAPER = QColor("#1d1f24")     # what dark mode resolves to


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _stage(engraved):
    return default_stage_config(engraved.prepared,
                                page_content_top(engraved.layout))


@pytest.fixture
def scenes(qapp, engraved) -> ScoreScenes:
    """Function-scoped on purpose — see the module docstring."""
    return ScoreScenes(engraved.layout, _stage(engraved))


def _child_paints(child, fill_tracks: bool, stroke_tracks: bool) -> set[str]:
    """The colours one child actually paints, asking only about the
    channels that track the element colour — a hairpin is `fill="none"`
    and carries its colour on the pen, so reading its brush would report
    a meaningless black."""
    out = set()
    if fill_tracks:
        out.add(child.brush().color().name())
    if stroke_tracks and isinstance(child, QGraphicsPathItem):
        out.add(child.pen().color().name())
    return out


def _painted(item) -> set[str]:
    """Every colour actually on this item's colour-tracking children."""
    out: set[str] = set()
    for child, fill_tracks, stroke_tracks in item._tracked:
        out |= _child_paints(child, fill_tracks, stroke_tracks)
    return out


# -- what the pass reaches -----------------------------------------------------

def test_the_ink_reaches_every_kind_on_the_page(scenes, engraved) -> None:
    """Scope is EVERYTHING, unlike a part tint. A white-on-black page
    with black staff lines is not a page anyone can read, so this walks
    the whole registry rather than TINTED_KINDS."""
    scenes.set_ink_color(WHITE)
    seen = set()
    for el in engraved.layout.elements:
        item = scenes.items[el.identity.element_id]
        assert item.color == WHITE, el.identity.element_id
        assert _painted(item) <= {"#ffffff"}, el.identity.element_id
        seen.add(el.identity.kind)
    # the kinds a part tint deliberately leaves black must be in here,
    # or the scope claim above is untested
    for kind in (ElementKind.NOTEHEAD, ElementKind.CLEF, ElementKind.REST,
                 ElementKind.DYNAMIC, ElementKind.BARLINE,
                 ElementKind.STAFF_LINES):
        assert kind in seen, kind


def test_the_ink_reaches_texts_and_stage_texts(scenes, engraved) -> None:
    """Texts are their own child type (QGraphicsSimpleTextItem, not a
    path), so they are worth naming separately — the title and composer
    are stage texts, which are built on a different code path again."""
    scenes.set_ink_color(WHITE)
    text_items = 0
    for eid, item in scenes.items.items():
        for child, fill_tracks, _ in item._tracked:
            if isinstance(child, QGraphicsSimpleTextItem) and fill_tracks:
                assert child.brush().color().name() == "#ffffff", eid
                text_items += 1
    assert text_items >= 3, "expected the title/composer/expression texts"
    title = scenes.items[ElementId("stage:title")]
    assert _painted(title) == {"#ffffff"}


def test_a_spanner_ghost_takes_the_ink_and_keeps_its_floor(
        qapp, engraved_spanners) -> None:
    """The ghost is the same ink at the floor opacity, whatever colour
    the ink now is — the opacity and the colour are separate inputs and
    neither pass touches the other's."""
    scenes = ScoreScenes(engraved_spanners.layout, _stage(engraved_spanners),
                         ghost_opacity=0.3)
    tracking = {id(child): (fill, stroke) for item in scenes.items.values()
                for child, fill, stroke in item._tracked}
    ghosts = [(child, tracking[id(child)])
              for item in scenes.items.values()
              for child in item._ghost_children if id(child) in tracking]
    assert ghosts, "fixture has no colour-tracking spanner ghosts"
    scenes.set_ink_color(WHITE)
    for ghost, (fill_tracks, stroke_tracks) in ghosts:
        assert _child_paints(ghost, fill_tracks, stroke_tracks) == {"#ffffff"}
        assert ghost.opacity() == pytest.approx(0.3)


def test_the_paper_changes_colour_but_never_its_visibility(scenes) -> None:
    """Export hides these rects to keep frames transparent (ruling R1),
    so a recolour that touched visibility would quietly make every
    exported video opaque."""
    scenes.set_page_background_visible(False)
    scenes.set_page_color(PAPER)
    for rect in scenes.page_rects:
        assert rect.brush().color().name() == "#1d1f24"
        assert not rect.isVisible()
    scenes.set_page_background_visible(True)
    assert all(r.isVisible() for r in scenes.page_rects)


def test_a_stage_text_rebuilt_after_a_recolour_is_born_in_the_new_ink(
        scenes, engraved) -> None:
    """`set_stage_texts` throws its items away and builds fresh ones, so
    without the scene retaining the ink, editing the title on a black
    page would turn it black-on-black — and no diff cache upstream could
    see it happen, because nothing about the colour changed."""
    scenes.set_ink_color(WHITE)
    texts = _stage(engraved).texts
    edited = tuple(
        t if t.element_id != "stage:title"
        else type(t)(**{**t.__dict__, "content": "Renamed"})
        for t in texts)
    scenes.set_stage_texts(edited)
    title = scenes.items[ElementId("stage:title")]
    assert title.color == WHITE
    assert _painted(title) == {"#ffffff"}


# -- what it must not disturb --------------------------------------------------

def test_an_authored_colour_wins_over_the_ink_either_way_round(
        scenes, engraved) -> None:
    """Ink and authored colour are separate inputs, which is what lets
    them be applied in any order — and what stops a page recolour from
    corrupting the authored-colour diff cache upstream."""
    part = PartId("P3")
    red = QColor("#cc2222")
    tinted = next(el.identity.element_id for el in engraved.layout.elements
                  if el.identity.part == part
                  and el.identity.kind is ElementKind.NOTEHEAD)
    untinted = next(el.identity.element_id for el in engraved.layout.elements
                    if el.identity.kind is ElementKind.CLEF)

    scenes.set_part_color(part, red)
    scenes.set_ink_color(WHITE)
    assert scenes.items[tinted].color == red        # authored survives
    assert scenes.items[untinted].color == WHITE    # unclaimed takes ink

    other = ScoreScenes(engraved.layout, _stage(engraved))
    other.set_ink_color(WHITE)                      # the other order
    other.set_part_color(part, red)
    assert other.items[tinted].color == red
    assert other.items[untinted].color == WHITE

    # and dropping the tint falls back to the INK, not to black
    scenes.set_part_color(part, None)
    assert scenes.items[tinted].color == WHITE
    assert scenes.items[tinted].authored_color is None


def test_selection_stays_tellable_apart_on_a_white_ink_page(
        scenes, engraved) -> None:
    """The tint composites over the EFFECTIVE colour, so on a white-ink
    page it is checked against the white — not against a black nobody
    can see."""
    eid = next(el.identity.element_id for el in engraved.layout.elements
               if el.identity.kind is ElementKind.NOTEHEAD)
    item = scenes.items[eid]
    scenes.set_ink_color(WHITE)
    item.set_selected(True)
    painted = _painted(item)
    assert painted and painted != {"#ffffff"}       # not lost in the ink
    assert painted == {"#ff6a00"}
    item.set_selected(False)
    assert _painted(item) == {"#ffffff"}            # back to the ink


def test_recolouring_a_selected_element_recomposes_its_tint(
        scenes, engraved) -> None:
    """Order the other way: selected first, recoloured second."""
    eid = next(el.identity.element_id for el in engraved.layout.elements
               if el.identity.kind is ElementKind.NOTEHEAD)
    item = scenes.items[eid]
    item.set_selected(True)
    scenes.set_ink_color(WHITE)
    assert _painted(item) == {"#ff6a00"}
    item.set_selected(False)
    assert _painted(item) == {"#ffffff"}


# -- the one-shot seam ---------------------------------------------------------

def test_apply_style_colors_reads_the_mode(scenes) -> None:
    apply_style_colors(scenes, StyleRules(colors={"mode": "dark"}))
    assert scenes.page_rects[0].brush().color().name() == "#1d1f24"
    assert next(iter(scenes.items.values())).color == WHITE


def test_an_unreadable_mode_lands_on_light(scenes) -> None:
    """The whole reason validation is at consumption: a hand-edited file
    cannot produce an invisible score."""
    apply_style_colors(scenes, StyleRules(colors={"mode": "midnight"}))
    assert scenes.page_rects[0].brush().color().name() == "#ffffff"
    assert next(iter(scenes.items.values())).color == BLACK


def test_the_page_ink_does_not_override_an_element_override(
        scenes, engraved) -> None:
    eid = next(el.identity.element_id for el in engraved.layout.elements
               if el.identity.kind is ElementKind.NOTEHEAD)
    apply_style_colors(scenes, StyleRules(
        colors={"mode": "dark"},
        elements={eid: ElementStyle(color="#00aa00")}))
    assert scenes.items[eid].color == QColor("#00aa00")


# -- the bit-for-bit promise ---------------------------------------------------

def _digest(scenes, page: int = 1) -> str:
    """Rasterize one page through the real scene and hash the pixels."""
    scene = scenes.scene_for_page(page)
    rect = scene.sceneRect()
    width = 900
    image = QImage(width, round(width * rect.height() / rect.width()),
                   QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    scene.render(painter)
    painter.end()
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return hashlib.sha256(image.constBits().tobytes()).hexdigest()


def test_an_untouched_document_renders_exactly_as_it_did_before(
        qapp, engraved) -> None:
    """The promise: a document that never touches the entry is not
    merely equivalent, it is the same pixels.

    Two of the three comparisons here exist to keep the first one
    honest. A digest that never changes would make "identical" pass for
    free, so the same page must demonstrably move when either colour is
    actually set."""
    stage = _stage(engraved)
    before = _digest(ScoreScenes(engraved.layout, stage))

    untouched = ScoreScenes(engraved.layout, stage)
    apply_style_colors(untouched, StyleRules())
    assert _digest(untouched) == before

    # the defaults written out explicitly are the same look, and this
    # time the full sweep really runs rather than taking the early exit
    spelled_out = ScoreScenes(engraved.layout, stage)
    spelled_out.set_ink_color(BLACK)
    spelled_out.set_page_color(QColor("#ffffff"))
    assert _digest(spelled_out) == before

    # non-vacuity, both halves
    inked = ScoreScenes(engraved.layout, stage)
    dark = ScoreScenes(engraved.layout, stage)
    apply_style_colors(dark, StyleRules(colors={"mode": "dark"}))
    assert _digest(dark) != before

    # both halves of dark mode move pixels, checked apart so neither
    # can be carrying the other
    inked = ScoreScenes(engraved.layout, stage)
    inked.set_ink_color(WHITE)
    assert _digest(inked) != before

    papered = ScoreScenes(engraved.layout, stage)
    papered.set_page_color(PAPER)
    assert _digest(papered) != before


def test_the_default_entry_costs_no_sweep(scenes) -> None:
    """The early exit is what makes the identity structural rather than
    a coincidence of two colours happening to match."""
    item = next(iter(scenes.items.values()))
    marker = QBrush(QColor("#123456"))
    for child, fill_tracks, _ in item._tracked:
        if fill_tracks:
            child.setBrush(marker)
            break
    apply_style_colors(scenes, StyleRules())        # default: no sweep
    assert "#123456" in _painted(item)
