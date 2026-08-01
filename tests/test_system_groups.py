"""Every system's ink hangs off one group item, and the group does not
move it.

This is the structural half of a change whose whole point was that
nothing looks different: the pixel half is a before/after render of the
real pages (tools/render_page_png.py). What these pin is that the tree
is the shape it claims to be, that reparenting left every child at the
scene coordinates it had, and that the scale seam turns on the centre of
the system's own ink — with 1.0 exactly identity, so a system nobody
scaled renders as if the parent were not there.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.render.items import ElementItem  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402
from scoreanim.render.system_group import SystemGroupItem  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _stage(engraved):
    return default_stage_config(engraved.prepared,
                                page_content_top(engraved.layout))


@pytest.fixture(scope="module")
def scenes(qapp, engraved) -> ScoreScenes:
    return ScoreScenes(engraved.layout, _stage(engraved))


def _fresh(engraved) -> ScoreScenes:
    """A private build, for the tests that scale or nudge."""
    return ScoreScenes(engraved.layout, _stage(engraved))


# -- the tree ------------------------------------------------------------


def test_every_element_sits_under_its_own_systems_group(scenes,
                                                        engraved) -> None:
    for el in engraved.layout.elements:
        item = scenes.items[el.identity.element_id]
        group = item.parentItem()
        assert isinstance(group, SystemGroupItem), el.identity.element_id
        assert (group.page, group.system) == (el.page, el.system)
        assert group is scenes.system_groups[(el.page, el.system)]
        assert group.scene() is scenes.scene_for_page(el.page)


def test_the_groups_are_exactly_the_systems_present(scenes,
                                                    engraved) -> None:
    expected = {(el.page, el.system) for el in engraved.layout.elements
                if el.system is not None}
    assert set(scenes.system_groups) == expected


def test_ink_with_no_system_is_left_top_level(scenes, engraved) -> None:
    """Stage texts (titles, page furniture) belong to no system and must
    stay exactly where they were: children of the scene itself."""
    stage_ids = {t.element_id for t in _stage(engraved).texts}
    assert stage_ids                       # the fixture really has some
    for eid in stage_ids:
        assert scenes.items[eid].parentItem() is None
    for rect in scenes.page_rects:
        assert rect.parentItem() is None


# -- reparenting moved nothing -------------------------------------------


def test_no_group_and_no_element_carries_a_transform(scenes,
                                                     engraved) -> None:
    """With every child untouched, an identity scene transform on both
    the group and the element IS the proof that scene coordinates are
    what they were before there was a parent."""
    for group in scenes.system_groups.values():
        assert group.sceneTransform().isIdentity()
        assert group.pos() == QPointF(0.0, 0.0)
    for el in engraved.layout.elements:
        item = scenes.items[el.identity.element_id]
        assert item.sceneTransform().isIdentity()
        assert item.scenePos() == QPointF(0.0, 0.0)


def test_a_path_still_lands_exactly_where_core_says_it_does(
        scenes, engraved) -> None:
    """The independent check, against core geometry rather than against
    the item tree: take a point on the glyph and push it through the
    whole parent chain — element, group, scene — and it must land on the
    same point the Layout's own affine puts it. Bit-exact, no tolerance:
    if the group contributed anything at all, these diverge."""
    from scoreanim.render.qpath import to_qpainter_path, to_qtransform

    checked = 0
    for el in engraved.layout.elements:
        if not el.glyph.paths:
            continue
        prim = el.glyph.paths[0]
        path = to_qpainter_path(prim.d)
        if path.isEmpty():
            continue
        item = scenes.items[el.identity.element_id]
        child = item.childItems()[0]
        point = path.pointAtPercent(0.5)
        assert child.mapToScene(point) == to_qtransform(
            prim.transform).map(point)
        checked += 1
    assert checked > 500


# -- the group's own ink -------------------------------------------------


def test_the_frozen_ink_rect_is_the_union_of_this_systems_ink(
        scenes, engraved) -> None:
    """This system's ink and no other's — the union computed here from
    the members the Layout names, so a group that had swallowed a
    neighbour's element would show up as a taller rect."""
    for (page, system), group in scenes.system_groups.items():
        union = None
        for el in engraved.layout.elements:
            if (el.page, el.system) != (page, system):
                continue
            rect = scenes.items[el.identity.element_id].sceneBoundingRect()
            union = rect if union is None else union.united(rect)
        assert group.ink_rect == union
        assert group.pivot == union.center()
        geo = engraved.layout.pages[page - 1]
        assert group.ink_rect.height() < geo.height   # a band, not the page


def test_a_nudge_after_construction_does_not_move_the_pivot(
        qapp, engraved) -> None:
    """The rect is frozen on purpose: overrides and animation both run
    after construction, and neither may drag the point a whole system
    turns around."""
    scenes = _fresh(engraved)
    group = next(iter(scenes.system_groups.values()))
    before = group.pivot
    member = next(el for el in engraved.layout.elements
                  if (el.page, el.system) == (group.page, group.system))
    scenes.set_element_offset(member.identity.element_id, 400.0, 400.0)
    assert group.pivot == before


# -- the scale seam ------------------------------------------------------


def test_scale_one_is_exactly_identity(qapp, engraved) -> None:
    scenes = _fresh(engraved)
    group = next(iter(scenes.system_groups.values()))
    rects = {i: i.sceneBoundingRect() for i in group.childItems()}

    group.set_system_scale(1.0)              # from the construction 1.0
    assert group.sceneTransform().isIdentity()
    group.set_system_scale(1.02)
    group.set_system_scale(1.0)              # and back down again
    assert group.sceneTransform().isIdentity()
    assert group.system_scale == 1.0
    for item, rect in rects.items():
        assert item.sceneBoundingRect() == rect


def test_scale_pivots_on_the_centre_of_the_systems_own_ink(
        qapp, engraved) -> None:
    scenes = _fresh(engraved)
    group = next(iter(scenes.system_groups.values()))
    pivot, ink = group.pivot, group.ink_rect

    group.set_system_scale(1.02)

    # the pivot is the one point that does not move
    assert group.mapToScene(pivot) == pivot
    grown = group.sceneTransform().mapRect(ink)
    assert grown.center().x() == pytest.approx(pivot.x(), abs=1e-9)
    assert grown.center().y() == pytest.approx(pivot.y(), abs=1e-9)
    assert grown.width() == pytest.approx(ink.width() * 1.02, abs=1e-9)
    assert grown.height() == pytest.approx(ink.height() * 1.02, abs=1e-9)
    # and it is the SYSTEM's centre, not the page's
    assert group.system_scale == 1.02


def test_scale_moves_the_systems_elements_away_from_that_centre(
        qapp, engraved) -> None:
    scenes = _fresh(engraved)
    group = next(iter(scenes.system_groups.values()))
    pivot = group.pivot
    members = [el for el in engraved.layout.elements
               if (el.page, el.system) == (group.page, group.system)]
    leftmost = min(members, key=lambda el: el.bbox.x)
    item = scenes.items[leftmost.identity.element_id]
    before = item.sceneBoundingRect().center()

    group.set_system_scale(1.02)

    after = item.sceneBoundingRect().center()
    assert after.x() < before.x()            # left of the pivot, so left
    assert after.x() - pivot.x() == pytest.approx(
        (before.x() - pivot.x()) * 1.02, abs=1e-6)


def test_scaling_one_system_leaves_the_others_alone(qapp, engraved) -> None:
    scenes = _fresh(engraved)
    groups = list(scenes.system_groups.values())
    assert len(groups) > 1
    others = {g: {i: i.sceneBoundingRect() for i in g.childItems()}
              for g in groups[1:]}

    groups[0].set_system_scale(1.02)

    for group, rects in others.items():
        assert group.sceneTransform().isIdentity()
        for item, rect in rects.items():
            assert item.sceneBoundingRect() == rect


def test_scaling_re_derives_the_reveal_clips(qapp, engraved_spanners) -> None:
    """A scale changes every descendant's scene transform, which is what
    a reveal clip's cached inverse is built from — the same trap a nudge
    sprang at M3.2. The clip must follow the ink, not stay behind at the
    old scale."""
    from scoreanim.core.animation import REVEALED_KINDS

    scenes = ScoreScenes(engraved_spanners.layout, _stage(engraved_spanners))
    el = next(e for e in engraved_spanners.layout.elements
              if e.identity.kind in REVEALED_KINDS and e.bbox.w > 20)
    item = scenes.items[el.identity.element_id]
    group = scenes.system_groups[(el.page, el.system)]

    # reveal it half way, in scene x
    edge = el.bbox.x + el.bbox.w / 2
    item.set_reveal_edge(edge)
    child = item.reveal_children[0]
    assert child.clip_right is not None
    local_before = child.clip_right

    group.set_system_scale(1.02)

    # same scene edge, so the clip now sits at a DIFFERENT local x — and
    # it must still map back to that scene x through the new transform
    assert child.clip_right != local_before
    mapped = child.sceneTransform().map(QPointF(child.clip_right, 0.0)).x()
    assert mapped == pytest.approx(edge, abs=1e-6)
