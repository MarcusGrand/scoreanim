"""M2.8: clicking empty staff space deselects (measurement M6, pinned).

The pure order lives in test_hit_priority.py; this pins the ruling
against real engraved geometry on both exit fixtures, because the whole
argument for it is what a click in the middle of a staff actually does.

Before the ruling, probing points inside staff rectangles picked
STAFF_LINES on 17.5% of testscore probes and 73.5% of complex3's — the
answer tracked rastral size, not intent. It also STOLE clicks from real
objects: an exact staff-line hit outranks a merely-tolerated notehead
beside it (exactness is the first key), so 6 testscore and 15 complex3
probes that sat next to real ink resolved to the staff instead of to the
thing the user was aiming at. Both are gone.
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


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _built(engraved):
    scenes = ScoreScenes(engraved.layout, StageConfig())
    state = AppState()
    controller = SelectionController(state)
    controller.bind_scenes(scenes)
    return scenes, state, controller


def _staff_probe_kinds(engraved, staves: int = 8) -> set[str]:
    """What a grid of clicks inside staff rectangles selects."""
    scenes, state, controller = _built(engraved)
    elements = [el for el in engraved.layout.elements
                if el.identity.kind is ElementKind.STAFF_LINES][:staves]
    assert elements, "fixture has no staff lines to probe"
    seen: set[str] = set()
    for el in elements:
        item = scenes.items[el.identity.element_id]
        for fx in (0.25, 0.4, 0.55, 0.7, 0.85):
            for fy in (0.15, 0.35, 0.5, 0.65, 0.85):
                controller.select_at(
                    QPointF(el.bbox.x + el.bbox.w * fx,
                            el.bbox.y + el.bbox.h * fy),
                    item.scene())
                selected = state.selected
                seen.add(selected.kind.name if selected is not None
                         else "NOTHING")
    return seen


def test_staff_space_never_selects_the_staff_on_testscore(
        qapp, engraved) -> None:
    kinds = _staff_probe_kinds(engraved)
    assert "STAFF_LINES" not in kinds
    assert "NOTHING" in kinds          # empty staff space really deselects


def test_staff_space_never_selects_the_staff_on_complex3(
        qapp, engraved_complex3_hidden) -> None:
    kinds = _staff_probe_kinds(engraved_complex3_hidden)
    assert "STAFF_LINES" not in kinds
    assert "NOTHING" in kinds


def test_a_direct_hit_on_staff_line_ink_also_deselects(
        qapp, engraved) -> None:
    """Not "the backdrop loses ties" — it is out of the running. Clicking
    a staff line's own stroke, where the hit is EXACT and the staff is
    the only candidate, still deselects; a rule that turned on sub-pixel
    aim would be worse than either answer."""
    scenes, state, controller = _built(engraved)
    staff = next(el for el in engraved.layout.elements
                 if el.identity.kind is ElementKind.STAFF_LINES)
    item = scenes.items[staff.identity.element_id]

    on_ink = None
    for child in item.childItems():
        if not hasattr(child, "path") or child.path().isEmpty():
            continue
        point = child.mapToScene(child.path().pointAtPercent(0.5))
        cands = controller.candidates_at(point, item.scene())
        if (len(cands) == 1 and cands[0].exact
                and cands[0].kind is ElementKind.STAFF_LINES):
            on_ink = point
            break
    assert on_ink is not None, "no isolated exact staff-line hit found"

    controller.select_at(on_ink, item.scene())
    assert state.selected is None


def test_the_backdrop_no_longer_steals_a_neighbouring_object(
        qapp, engraved) -> None:
    """The reason this is a fix and not just a policy preference:
    exactness is the FIRST key, so an exact staff-line hit used to beat a
    notehead that the click merely fell within tolerance of. Now the
    object wins, because it is the only candidate."""
    from scoreanim.core.selection import HitCandidate, pick
    from scoreanim.core.score.identity import ElementId

    scenes, state, controller = _built(engraved)
    note = next(el for el in engraved.layout.elements
                if el.identity.kind is ElementKind.NOTEHEAD)
    staff_id = ElementId(next(
        el.identity.element_id for el in engraved.layout.elements
        if el.identity.kind is ElementKind.STAFF_LINES))
    contested = [
        HitCandidate(staff_id, ElementKind.STAFF_LINES, 9984.1, exact=True),
        HitCandidate(note.identity.element_id, ElementKind.NOTEHEAD,
                     note.bbox.w * note.bbox.h, exact=False),
    ]
    assert pick(contested) == note.identity.element_id
