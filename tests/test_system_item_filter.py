"""Systems mode hides the OTHER systems' ITEMS, not their region
(2026-08-30).

Stage 1 of the rework put every system in one fixed frame, and that
frame is taller than a band, so a neighbour's paper is inside it. The
view masked the neighbour's REGION. A region can only be as accurate as
the band edges it is cut from, and bands are the union of element
BBOXES — so ink that grows past its bbox (a system pulse or a note's
pop scaling it, a stroke wider than its path) lands in the one strip the
mask must leave alone: the current system's own. Marcus saw the result
as slivers of the next system inside the frame.

Filtering items has no such hole. What these pin: only the current
system's ink is ever visible, ink with no system still shows, per-element
hiding survives, the leak the mask cannot reach is gone, nothing becomes
selectable that should not be, the camera is untouched, and export
cannot see any of it.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.engraving.systems import (  # noqa: E402
    neighbour_bounds, system_bands, systems_frame, unattributed_elements)
from scoreanim.core.engraving.types import (  # noqa: E402
    Layout, PageGeometry, Point, Rect, RenderedElement, RenderPrimitive)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.identity import (  # noqa: E402
    ElementId, ElementIdentity, ElementKind)
from scoreanim.render.items import ElementItem  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402
from scoreanim.ui.stage_view import StageView  # noqa: E402

# the page's own background: what the frame fills with, and so what an
# ink-free spot inside the frame reads as
_FILL = "#ffffff"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def scenes(qapp, engraved) -> ScoreScenes:
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    return ScoreScenes(engraved.layout, stage)


@pytest.fixture(scope="module")
def bands(engraved) -> dict:
    return {b.system: b for b in system_bands(engraved.layout)}


@pytest.fixture(scope="module")
def frame(bands):
    return systems_frame(tuple(bands.values()))


@pytest.fixture(scope="module")
def bounds(bands):
    return neighbour_bounds(tuple(bands.values()))


@pytest.fixture(autouse=True)
def _pristine(scenes):
    """The scenes are shared by this module, and two of these tests
    scale a system or hide an element to make their point. Put both back
    afterwards, so no test can inherit another's stage."""
    yield
    scenes.set_visible_system(None)
    for group in scenes.system_groups.values():
        group.set_system_scale(1.0)
    for item in scenes.items.values():
        item.setVisible(True)


def _qrect(rect) -> QRectF:
    return QRectF(rect.x, rect.y, rect.w, rect.h)


def _view(frame, size=(600, 850)) -> StageView:
    view = StageView()
    view.resize(*size)
    view.viewport().grab()               # force offscreen layout/resize
    view.set_systems_frame(frame)        # what ViewRouter.bind does
    return view


def _show(view, scenes, band, bounds=None) -> None:
    """One system, the way ViewRouter.show_system does it: filter the
    items first, then swap the band."""
    scenes.set_visible_system(band.system)
    view.show_system_band(scenes.scene_for_page(band.page),
                          _qrect(band.rect),
                          (bounds or {}).get(band.system, (None, None)))


def _element_at(scene, scene_pos: QPointF) -> ElementItem | None:
    """The element under a scene point, the way ui/selection.py finds
    it: the scene's own hit list, then up to the owning element."""
    area = QRectF(scene_pos.x() - 2, scene_pos.y() - 2, 4, 4)
    for hit in scene.items(area):
        node = hit
        while node is not None and not isinstance(node, ElementItem):
            node = node.parentItem()
        if node is not None:
            return node
    return None


# how far in from the viewport's edges the pixel scans stay. The
# transient scroll hint paints a dark line there (ui/stage_scrollbars.py)
# and it is not the score.
_EDGE = 6


def _ink_pixels(view: StageView, rect: QRectF) -> int:
    """How many pixels inside this scene rect are not the frame's own
    fill — i.e. how much ink is showing there."""
    image = view.viewport().grab().toImage()
    top_left: QPoint = view.mapFromScene(rect.topLeft())
    bottom_right: QPoint = view.mapFromScene(rect.bottomRight())
    count = 0
    for y in range(max(_EDGE, top_left.y()),
                   min(image.height() - _EDGE, bottom_right.y() + 1)):
        for x in range(max(_EDGE, top_left.x()),
                       min(image.width() - _EDGE, bottom_right.x() + 1)):
            if image.pixelColor(x, y).name() != _FILL:
                count += 1
    return count


# -- the filter itself ----------------------------------------------------

def test_only_the_named_system_is_visible(scenes, bands) -> None:
    for system in bands:
        scenes.set_visible_system(system)
        shown = {g.system for g in scenes.system_groups.values()
                 if g.isVisible()}
        assert shown == {system}


def test_none_shows_every_system_again(scenes, bands) -> None:
    scenes.set_visible_system(3)
    scenes.set_visible_system(None)
    assert all(g.isVisible() for g in scenes.system_groups.values())
    assert {g.system for g in scenes.system_groups.values()} == set(bands)


def test_asking_twice_changes_nothing(scenes) -> None:
    """A switch runs this on every system; a repeat must be a no-op, not
    a second walk over every group."""
    scenes.set_visible_system(2)
    before = {(g.page, g.system): g.isVisible()
              for g in scenes.system_groups.values()}
    scenes.set_visible_system(2)
    after = {(g.page, g.system): g.isVisible()
             for g in scenes.system_groups.values()}
    assert before == after


def test_ink_with_no_system_always_shows(scenes) -> None:
    """The stage texts — the title and the composer — belong to no
    system, so they cannot be hidden with one and must not be. That is
    the same ink the mask was opened above the first system for."""
    loose = [i for i in scenes.items.values() if i.identity is None]
    assert loose, "the fixture should carry stage texts"
    scenes.set_visible_system(1)
    assert all(item.isVisible() for item in loose)
    assert all(rect.isVisible() for rect in scenes.page_rects)


def test_per_element_hiding_survives_a_filter(scenes, engraved,
                                              bands) -> None:
    """The filter writes the GROUP's flag and hiding writes the ITEM's,
    so a deleted or hidden element stays hidden through any number of
    switches and its neighbours stay shown."""
    on_two = [el for el in engraved.layout.elements
              if el.system == 2 and el.identity.kind is ElementKind.NOTEHEAD]
    hidden, other = on_two[0].identity.element_id, on_two[1].identity.element_id
    scenes.set_element_hidden(hidden, True)
    for system in list(bands) + [2]:
        scenes.set_visible_system(system)
    assert scenes.items[hidden].isVisible() is False
    assert scenes.items[other].isVisible() is True


# -- the leak the region mask cannot reach --------------------------------

def test_a_neighbours_ink_above_its_own_band_is_gone(scenes, bands,
                                                     frame, bounds) -> None:
    """The bug, in pixels.

    A band is the union of its elements' layout BBOXES, and painted ink
    is bigger than that — a text item's glyph box carries the font's
    ascent and descent, a stroke is wider than its path. So a system's
    ink pokes out of its own band (measured on testscore: system 3's
    reaches 1.0 page unit above it, and on the grieg and condense
    fixtures it is 3 to 17 units). The mask is cut from the band edges,
    so it stops exactly where that overhang starts: the ink lands in the
    strip the mask must leave alone, the current system's own region.
    There is no way to paint over it without erasing the music.

    Framed on a big window so one page unit is about one device pixel."""
    assert bands[2].page == bands[3].page == 2
    over = QRectF(0.0, bands[3].rect.y - 12.0, bands[3].rect.w, 12.0)
    assert over.top() > bands[2].rect.y + bands[2].rect.h   # not our ink

    view = _view(frame, size=(2200, 3000))
    _show(view, scenes, bands[2], bounds)
    scenes.set_visible_system(None)          # what the mask alone leaves
    leaked = _ink_pixels(view, over)
    assert leaked > 0, "the leak did not reproduce — nothing to fix"

    scenes.set_visible_system(2)
    assert _ink_pixels(view, over) == 0, (
        f"{leaked} leaked pixels survived the filter")


def test_a_neighbour_growing_out_of_its_band_is_gone(scenes, bands,
                                                     frame, bounds) -> None:
    """The same hole, opened as wide as the animation opens it.

    A system pulse scales a whole system about its own ink centre, so a
    neighbour reaches further out of its band the louder the music gets
    — and the mask, cut once from the resting bands, cannot follow. Here
    the middle of the gap between systems 2 and 3 is ink-free at rest,
    and system 3 is scaled until it is not."""
    gap_top = bands[2].rect.y + bands[2].rect.h
    gap = bands[3].rect.y - gap_top
    assert gap > 0
    middle = QRectF(0.0, gap_top + gap / 3.0, bands[2].rect.w, gap / 3.0)

    view = _view(frame)
    _show(view, scenes, bands[2], bounds)
    scenes.set_visible_system(None)
    assert _ink_pixels(view, middle) == 0, "the gap's middle starts empty"

    group = scenes.system_groups[(2, 3)]
    rise = 0.9 * gap
    group.set_system_scale(1.0 + 2.0 * rise / group.ink_rect.height())
    leaked = _ink_pixels(view, middle)
    assert leaked > 0, "the leak did not reproduce — nothing to fix"

    scenes.set_visible_system(2)
    assert _ink_pixels(view, middle) == 0, (
        f"{leaked} leaked pixels survived the filter")


def test_no_other_system_is_visible_in_the_frame(scenes, bands,
                                                 frame, bounds) -> None:
    """The invariant, over the whole score: with any system shown, no
    visible ink anywhere in the frame belongs to another one."""
    view = _view(frame)
    for system, band in bands.items():
        _show(view, scenes, band, bounds)
        scene = scenes.scene_for_page(band.page)
        placed = _qrect(frame.rect_for(band.rect))
        strays = set()
        for hit in scene.items(placed):
            node = hit
            while node is not None and not isinstance(node, ElementItem):
                node = node.parentItem()
            if (node is not None and node.system is not None
                    and node.system != system):
                strays.add(node.system)
        assert not strays, f"system {system} shows ink from {strays}"


def test_a_neighbour_cannot_be_clicked(scenes, bands, bounds) -> None:
    """Hidden ink is not hittable, so a click where the neighbour is
    reaches nothing — and reaches it again in paged mode."""
    page_two = scenes.scene_for_page(2)
    on_three = next(i for i in scenes.items.values()
                    if i.system == 3 and i.identity is not None
                    and i.identity.kind is ElementKind.NOTEHEAD)
    at = QPointF(on_three.bbox.center())

    scenes.set_visible_system(3)
    assert _element_at(page_two, at) is not None      # it is really there
    scenes.set_visible_system(2)
    assert _element_at(page_two, at) is None
    scenes.set_visible_system(None)                   # paged
    assert _element_at(page_two, at) is not None


# -- what must NOT change -------------------------------------------------

def test_the_camera_is_untouched_by_the_filter(scenes, bands, frame,
                                               bounds) -> None:
    """Visibility changes no transform and no scroll range, so stage 2's
    result stands: play up and down the score many times over, zoomed,
    and the camera lands on exactly one position per system and returns
    to the first bit-for-bit."""
    view = _view(frame)
    _show(view, scenes, bands[1], bounds)
    view.zoom_by(2.0)
    view.scroll_by(300.0, 0.0)
    _show(view, scenes, bands[1], bounds)
    first = view.mapToScene(0, 0)
    order = list(bands) + list(reversed(list(bands)))
    seen = set()
    for system in order * 6:
        _show(view, scenes, bands[system], bounds)
        seen.add(view.mapToScene(0, 0).toTuple())
    assert len(seen) == len(bands)
    _show(view, scenes, bands[1], bounds)
    assert view.mapToScene(0, 0) == first


def test_export_cannot_see_the_stage_filter(scenes, engraved) -> None:
    """Export builds its OWN ScoreScenes from the same inputs, which is
    why this is presentation state and not the document: filtering the
    stage down to one system leaves an export's scenes whole."""
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    theirs = ScoreScenes(engraved.layout, stage)
    scenes.set_visible_system(2)
    assert all(g.isVisible() for g in theirs.system_groups.values())


# -- ink no system owns ---------------------------------------------------

def test_the_fixture_has_no_unattributed_ink(engraved) -> None:
    """Nothing on a real score falls outside a system today: the
    engraver's own page furniture is suppressed, and the title and
    composer are stage texts rather than layout."""
    assert unattributed_elements(engraved.layout) == ()


def test_unattributed_ink_is_counted_and_named() -> None:
    def _element(eid: str, system: int | None) -> RenderedElement:
        return RenderedElement(
            identity=ElementIdentity(
                element_id=ElementId(eid), kind=ElementKind.TEXT,
                part=None, part_name=None, staff=None, voice=None,
                onset=None),
            page=1, x=0.0, y=0.0, bbox=Rect(0.0, 0.0, 1.0, 1.0),
            anchor=Point(0.0, 0.0),
            glyph=RenderPrimitive(paths=(), texts=()), system=system)

    layout = Layout(pages=(PageGeometry(1, 100.0, 100.0),),
                    elements=(_element("score:p1:text:0", None),
                              _element("score:p1:text:1", None),
                              _element("P1:m1:s1:v1:note:0", 1)))
    assert unattributed_elements(layout) == (
        ("TEXT", 2, "score:p1:text:0"),)
