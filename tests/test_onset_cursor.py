"""The on-page onset cursor, on a real MainWindow offscreen: the line
marks the selected element's fire time, a drag snaps stop to stop and
commits one SetTriggerBeat, and the DragRouter keeps the nudge and the
cursor from fighting over the stage's one probe slot."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import (stops_for_system, x_at)  # noqa: E402
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.ui.drag_router import DragRouter  # noqa: E402
from scoreanim.ui.main_window import MainWindow  # noqa: E402

FIXTURE = Path(__file__).parent.parent / "testdata" / "testscore.musicxml"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    from PySide6.QtCore import QSettings
    settings = QSettings(str(tmp_path / "ui.ini"),
                         QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(FIXTURE)
    return win


def _select(window, kind: ElementKind):
    for el in window.animation_inputs.layout.elements:
        if el.identity.kind is kind and el.identity.onset is not None:
            window.app_state.set_selection(el.identity)
            return el
    raise AssertionError(f"no {kind} in the fixture")


def _cursor(window):
    return window.onset_cursor._item


def test_cursor_appears_for_a_dynamic_at_its_fire_x(window) -> None:
    el = _select(window, ElementKind.DYNAMIC)
    item = _cursor(window)
    assert item is not None
    band = window.installer  # noqa: F841  (window built; band from loader)
    bands = {b: v for b, v in window.onset_cursor._bands.items()}
    band = bands[el.system]
    stops = stops_for_system(window.animation_inputs.layout, el.system)
    beat = window.animation_inputs.schedule.beats_by_element[
        el.identity.element_id]
    assert item.x_pos == x_at(stops, beat)
    assert item.scene() is window._scenes.scene_for_page(band.page)
    line = item.line()
    assert (line.y1(), line.y2()) == (band.rect.y,
                                      band.rect.y + band.rect.h)


def test_no_cursor_for_a_notehead_or_no_selection(window) -> None:
    _select(window, ElementKind.NOTEHEAD)
    assert _cursor(window) is None
    window.app_state.set_selection(None)
    assert _cursor(window) is None


def test_probe_grabs_the_line_and_only_the_line(window) -> None:
    _select(window, ElementKind.DYNAMIC)
    item = _cursor(window)
    line = item.line()
    mid_y = (line.y1() + line.y2()) / 2
    on = QPointF(item.x_pos + 3.0, mid_y)
    far = QPointF(item.x_pos + 60.0, mid_y)
    assert window.onset_cursor.probe(on, item.scene())
    assert not window.onset_cursor.probe(far, item.scene())
    # the router hands the cursor the press before the nudge sees it
    assert window.drag_router.probe(on, item.scene())
    assert window.drag_router._owner is window.onset_cursor


def test_a_drag_snaps_to_the_next_stop_and_commits_once(window) -> None:
    el = _select(window, ElementKind.DYNAMIC)
    eid = el.identity.element_id
    item = _cursor(window)
    stops = stops_for_system(window.animation_inputs.layout, el.system)
    beat = window.animation_inputs.schedule.beats_by_element[eid]
    start_x = item.x_pos
    target = next(s for s in stops if s.x > start_x + 1.0)

    line = item.line()
    origin = QPointF(start_x, (line.y1() + line.y2()) / 2)
    delta = QPointF(target.x - start_x, 0.0)
    window.onset_cursor.start(origin, item.scene())
    window.onset_cursor.move(delta * 0.5)      # mid-drag: live snap
    window.onset_cursor.finish(delta)

    assert dict(window.app_state.doc.trigger_overrides) == {
        eid: target.beats}
    assert window.app_state.undo_text() == "move onset"
    assert window.animation_inputs.schedule.beats_by_element[eid] \
        == target.beats
    # the line re-synced onto the rebuilt schedule
    assert _cursor(window).x_pos == target.x
    assert target.beats != beat


def test_a_zero_move_release_changes_nothing(window) -> None:
    _select(window, ElementKind.DYNAMIC)
    item = _cursor(window)
    line = item.line()
    origin = QPointF(item.x_pos, (line.y1() + line.y2()) / 2)
    doc_before = window.app_state.doc
    window.onset_cursor.start(origin, item.scene())
    window.onset_cursor.finish(QPointF(0.0, 0.0))
    assert window.app_state.doc is doc_before
    assert _cursor(window).x_pos == item.x_pos


def test_undo_moves_the_line_back(window) -> None:
    el = _select(window, ElementKind.DYNAMIC)
    item = _cursor(window)
    stops = stops_for_system(window.animation_inputs.layout, el.system)
    start_x = item.x_pos
    target = next(s for s in stops if s.x > start_x + 1.0)
    line = item.line()
    origin = QPointF(start_x, (line.y1() + line.y2()) / 2)
    window.onset_cursor.start(origin, item.scene())
    window.onset_cursor.finish(QPointF(target.x - start_x, 0.0))
    assert _cursor(window).x_pos == target.x
    window.app_state.undo()
    assert _cursor(window).x_pos == start_x


def test_router_falls_through_to_the_nudge() -> None:
    class Claims:
        def __init__(self, yes): self.yes = yes; self.calls = []
        def probe(self, pos, scene=None): return self.yes
        def start(self, pos, scene=None): self.calls.append("start")
        def move(self, delta): self.calls.append("move")
        def finish(self, delta): self.calls.append("finish")

    first, second = Claims(False), Claims(True)
    router = DragRouter((first, second))
    assert router.probe(QPointF(0, 0))
    router.start(QPointF(0, 0))
    router.move(QPointF(1, 0))
    router.finish(QPointF(1, 0))
    assert second.calls == ["start", "move", "finish"]
    assert first.calls == []
    # nobody claims: the drag goes nowhere
    assert not DragRouter((first,)).probe(QPointF(0, 0))
