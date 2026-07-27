"""Drag-to-nudge (M3.2): the command, the gesture, the reveal clip, and
export parity.

`LayoutOverride.dx/dy` have been schema slots since Phase 4 with the
comment "no editing UI yet". This is what consumes them, so the tests
that matter most are the two that keep the consumption honest: a drag is
ONE undo entry (rule 8), and an exported frame matches the stage
(otherwise the override means two different things in two places).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.editing import (COARSE_NUDGE, NUDGEABLE_KINDS,  # noqa: E402
                                    NUDGE_STEP, is_nudgeable)
from scoreanim.core.project import (LayoutOverride,  # noqa: E402
                                    ProjectDoc, SetLayoutOverride)
from scoreanim.core.project.commands.base import CommandError  # noqa: E402
from scoreanim.core.score.identity import (ElementId,  # noqa: E402
                                           ElementKind)
from scoreanim.ui.main_window import MainWindow  # noqa: E402

# a fixture with real hairpins AND a hairpin broken across systems —
# testscore has no wedges at all (its revealed ink is all ties/slurs)
FIXTURE = (Path(__file__).parent.parent / "testdata"
           / "broken_hairpin_and_slur_test.musicxml")
EID = ElementId("P1:m1:s1:v1:hairpin:0")


# -- the command (headless, no Qt) ---------------------------------------

def test_sets_a_delta_and_stays_sparse() -> None:
    doc = SetLayoutOverride(EID, 3.0, -2.0).apply(ProjectDoc())
    assert doc.layout_overrides[EID] == LayoutOverride(dx=3.0, dy=-2.0)
    # back to zero and the entry disappears entirely (sparse-doc idiom)
    assert SetLayoutOverride(EID, 0.0, 0.0).apply(doc).layout_overrides == {}


def test_the_delta_is_absolute_not_incremental() -> None:
    """What makes one command per gesture possible: the second write
    REPLACES rather than accumulates, so a drag can preview freely and
    still commit the whole gesture once."""
    doc = SetLayoutOverride(EID, 3.0, -2.0).apply(ProjectDoc())
    doc = SetLayoutOverride(EID, 10.0, 5.0).apply(doc)
    assert doc.layout_overrides[EID] == LayoutOverride(dx=10.0, dy=5.0)


def test_nudging_preserves_hidden() -> None:
    """A tempo mark hidden behind its overlay must stay hidden when
    moved — the two fields are independent intents on one entry."""
    doc = ProjectDoc(layout_overrides={EID: LayoutOverride(hidden=True)})
    out = SetLayoutOverride(EID, 4.0, 0.0).apply(doc)
    assert out.layout_overrides[EID] == LayoutOverride(dx=4.0, hidden=True)
    # ...and zeroing the delta keeps the entry alive, because hidden is
    # still non-default
    back = SetLayoutOverride(EID, 0.0, 0.0).apply(out)
    assert back.layout_overrides[EID] == LayoutOverride(hidden=True)


@pytest.mark.parametrize("dx,dy", [(float("nan"), 0.0),
                                   (0.0, float("inf"))])
def test_non_finite_deltas_are_rejected(dx, dy) -> None:
    with pytest.raises(CommandError):
        SetLayoutOverride(EID, dx, dy).apply(ProjectDoc())


def test_overrides_round_trip_through_the_project_file(tmp_path) -> None:
    from scoreanim.core.project.serialize import load_project, save_project
    doc = SetLayoutOverride(EID, 3.5, -2.25).apply(ProjectDoc())
    path = tmp_path / "p.scoreanim"
    save_project(doc, path)
    assert load_project(path).layout_overrides[EID] == \
        LayoutOverride(dx=3.5, dy=-2.25)


# -- the policy set ------------------------------------------------------

def test_nudgeable_kinds_is_the_roadmaps_three() -> None:
    """Started narrow on purpose (see core/editing/nudge.py for what is
    left out and why). HAIRPIN is in there despite being clip-revealed —
    the spike measured that interaction rather than assuming it."""
    assert NUDGEABLE_KINDS == {ElementKind.DYNAMIC, ElementKind.HAIRPIN,
                               ElementKind.TEXT}
    assert not is_nudgeable(ElementKind.NOTEHEAD)
    assert not is_nudgeable(ElementKind.BARLINE)
    assert not is_nudgeable(None)


# -- the gesture, on a real window ---------------------------------------

@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    from PySide6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(FIXTURE)
    return win


def _select(window, kind: ElementKind):
    el = next(e for e in window.animation_inputs.layout.elements
              if e.identity.kind is kind)
    window.app_state.set_selection(el.identity)
    return el


def _drag(window, dx: float, dy: float) -> None:
    item = window._scenes.items[window.nudge.target()]
    origin = item.sceneBoundingRect().center()
    window.nudge.start(origin, item.scene())
    window.nudge.move(QPointF(dx / 2, dy / 2))       # a mid-gesture frame
    window.nudge.finish(QPointF(dx, dy))


def test_a_whole_drag_is_one_undo_entry(window) -> None:
    """Rule 8, in the form the roadmap called out: 'a drag is one entry,
    not forty'. The mid-gesture move must leave the document alone."""
    el = _select(window, ElementKind.HAIRPIN)
    eid = el.identity.element_id
    depth = _undo_depth(window)

    item = window._scenes.items[eid]
    window.nudge.start(item.sceneBoundingRect().center(), item.scene())
    for step in range(1, 21):                        # twenty mouse-moves
        window.nudge.move(QPointF(step, -step))
    assert window.app_state.doc.layout_overrides == {}   # nothing committed
    assert item.pos() == QPointF(20.0, -20.0)           # but it DID move
    window.nudge.finish(QPointF(20.0, -20.0))

    assert window.app_state.doc.layout_overrides[eid] == \
        LayoutOverride(dx=20.0, dy=-20.0)
    assert _undo_depth(window) == depth + 1
    assert window.app_state.undo_text() == "move element"

    window.app_state.undo()
    assert window.app_state.doc.layout_overrides == {}
    assert item.pos() == QPointF(0.0, 0.0)              # scene follows undo


def _undo_depth(window) -> int:
    """Applied-command count — the thing "one entry per gesture" is a
    statement about."""
    return window.app_state._stack._index


def test_a_second_drag_accumulates_from_where_it_was_left(window) -> None:
    el = _select(window, ElementKind.HAIRPIN)
    _drag(window, 10.0, 0.0)
    _drag(window, 5.0, 3.0)
    assert window.app_state.doc.layout_overrides[el.identity.element_id] == \
        LayoutOverride(dx=15.0, dy=3.0)


def test_a_press_that_never_moves_is_not_an_edit(window) -> None:
    _select(window, ElementKind.HAIRPIN)
    depth = _undo_depth(window)
    _drag(window, 0.0, 0.0)
    assert _undo_depth(window) == depth
    assert window.app_state.doc.layout_overrides == {}


# -- what may be dragged -------------------------------------------------

def test_a_non_nudgeable_selection_pans_instead(window) -> None:
    """The probe is what keeps the pan intact: a notehead is selectable
    but not nudgeable, so a drag on it must still pan."""
    el = _select(window, ElementKind.NOTEHEAD)
    item = window._scenes.items[el.identity.element_id]
    assert window.nudge.target() is None
    assert not window.nudge.probe(item.sceneBoundingRect().center(),
                                  item.scene())


def test_pressing_off_the_selected_element_pans(window) -> None:
    """Only the selected element's own ink starts a nudge — the stage
    must never feel like it grabbed something the user did not pick."""
    el = _select(window, ElementKind.HAIRPIN)
    item = window._scenes.items[el.identity.element_id]
    assert window.nudge.probe(item.sceneBoundingRect().center(),
                              item.scene())
    far = item.sceneBoundingRect().center() + QPointF(400.0, 400.0)
    assert not window.nudge.probe(far, item.scene())


def test_nothing_selected_pans(window) -> None:
    window.app_state.set_selection(None)
    assert not window.nudge.probe(QPointF(100.0, 100.0), None)


# -- keyboard ------------------------------------------------------------

def test_arrow_keys_nudge_one_unit_shift_coarse(window) -> None:
    el = _select(window, ElementKind.HAIRPIN)
    eid = el.identity.element_id
    for key, expected in ((Qt.Key.Key_Right, (NUDGE_STEP, 0.0)),
                          (Qt.Key.Key_Down, (NUDGE_STEP, NUDGE_STEP))):
        window.view.keyPressEvent(QKeyEvent(
            QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
        got = window.app_state.doc.layout_overrides[eid]
        assert (got.dx, got.dy) == expected

    window.view.keyPressEvent(QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_Left,
        Qt.KeyboardModifier.ShiftModifier))
    got = window.app_state.doc.layout_overrides[eid]
    assert got.dx == NUDGE_STEP - COARSE_NUDGE


def test_arrow_keys_do_nothing_without_a_nudgeable_selection(window) -> None:
    _select(window, ElementKind.NOTEHEAD)
    depth = _undo_depth(window)
    window.view.keyPressEvent(QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_Right,
        Qt.KeyboardModifier.NoModifier))
    assert _undo_depth(window) == depth


# -- the reveal clip (the spike's finding, pinned) -----------------------

def test_nudging_a_spanner_keeps_its_reveal_clip_correct(window) -> None:
    """spikes/nudge_reveal.py measured a cached inverse scene transform
    in RevealPathItem: after a move the clip landed exactly dx off, so
    the spanner revealed as if the playhead were dx further right.
    ElementItem.set_offset invalidates it and re-pushes the edge.

    Checked in LOCAL clip coordinates, because the painted boundary is a
    vertical line in the child's own space — a scene-x readout at one y
    would confuse a clamp for a coordinate error."""
    el = _select(window, ElementKind.HAIRPIN)
    item = window._scenes.items[el.identity.element_id]
    child = item.reveal_children[0]
    mid = el.bbox.x + el.bbox.w / 2.0

    item.set_reveal_edge(mid)
    home = child.clip_right
    assert home is not None

    scale = child.sceneTransform().m11()
    item.set_offset(10.0, 0.0)
    assert child.clip_right == pytest.approx(home - 10.0 / scale, abs=1e-6)

    item.set_offset(0.0, -20.0)              # pure y: the clip must not move
    assert child.clip_right == pytest.approx(home, abs=1e-6)


def test_the_reveal_clip_pin_is_not_vacuous(window) -> None:
    """Guard: with the cache left stale the clip does NOT track the
    move, so the test above cannot pass by accident."""
    el = _select(window, ElementKind.HAIRPIN)
    item = window._scenes.items[el.identity.element_id]
    child = item.reveal_children[0]
    mid = el.bbox.x + el.bbox.w / 2.0

    item.set_reveal_edge(mid)
    home = child.clip_right
    item.setPos(10.0, 0.0)                   # a bare move: no invalidation
    item.set_reveal_edge(mid)
    assert child.clip_right == home          # stale: the clip did not move


# -- export parity (non-optional, per the roadmap) -----------------------

def _digest(image) -> str:
    rgba = image.convertToFormat(image.Format.Format_RGBA8888)
    return hashlib.sha256(bytes(rgba.constBits())).hexdigest()


def _render(window, page: int):
    """One export frame at t=0 through the real FrameRenderer, carrying
    the document's overrides exactly as FileActions passes them."""
    from scoreanim.core.animation import StyleRules
    from scoreanim.core.timing import TempoMap
    from scoreanim.render.export import ExportFormat, ExportSpec, FrameRenderer

    doc = window.app_state.doc
    spec = ExportSpec(fps=30, height=360, start_seconds=0.0,
                      end_seconds=0.1, offset_seconds=0.0,
                      format=ExportFormat.PNG_SEQUENCE, out_path=Path("x"))
    renderer = FrameRenderer(window.animation_inputs, doc.style or StyleRules(),
                             TempoMap(list(doc.timing.tempo_events)), (), spec,
                             overrides=dict(doc.layout_overrides))
    return renderer


def test_an_exported_frame_matches_the_stage_after_a_nudge(window) -> None:
    """The M3 exit criterion. `apply_hidden_overrides` grew into
    `apply_overrides` precisely so this cannot drift: whatever the stage
    shows for a nudged element, the exported frame shows too."""
    el = _select(window, ElementKind.HAIRPIN)
    eid = el.identity.element_id

    before = _render(window, el.page)
    assert before._scenes.items[eid].pos() == QPointF(0.0, 0.0)

    _drag(window, 24.0, -18.0)
    assert window._scenes.items[eid].pos() == QPointF(24.0, -18.0)

    after = _render(window, el.page)
    # the export's own private scenes carry the same delta the stage does
    assert after._scenes.items[eid].pos() == QPointF(24.0, -18.0)
    # ...and the rendered pixels actually changed because of it
    assert _digest(after.render_frame(0)) != _digest(before.render_frame(0))


def test_clearing_a_nudge_restores_the_exported_frame_exactly(window) -> None:
    """Round trip in bytes: nudge, clear, and the frame is the original
    again — so the delta is the ONLY thing the override contributes."""
    el = _select(window, ElementKind.HAIRPIN)
    home = _digest(_render(window, el.page).render_frame(0))

    _drag(window, 24.0, -18.0)
    assert _digest(_render(window, el.page).render_frame(0)) != home

    window.nudge.clear()
    assert window.app_state.doc.layout_overrides == {}
    assert _digest(_render(window, el.page).render_frame(0)) == home
