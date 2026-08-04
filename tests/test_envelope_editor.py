"""The envelope canvas, offscreen: a drag emits continuously and
commits once, the picture is the envelope that plays, and what a drag
emits survives the step-1 consumption path — the document keys go in,
a valid `Envelope` comes out.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import (EnvelopeSpec,  # noqa: E402
                                      glow_track, read_glow_shape,
                                      spec_envelope)
from scoreanim.core.editing import Handle, handle_points, x_of  # noqa: E402
from scoreanim.ui.envelope_editor import EnvelopeEditor  # noqa: E402

SPEC = EnvelopeSpec(attack=0.10, sustain=1.0, swell_on=True, swell_pos=0.5,
                    swell_level=1.0, release=0.20)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(qapp) -> EnvelopeEditor:
    widget = EnvelopeEditor(SPEC)
    widget.resize(250, 130)          # the panel's width, near enough
    return widget


def press(widget, x, y) -> None:
    widget.mousePressEvent(_event(QMouseEvent.Type.MouseButtonPress, x, y))


def move(widget, x, y) -> None:
    widget.mouseMoveEvent(_event(QMouseEvent.Type.MouseMove, x, y))


def release(widget, x, y) -> None:
    widget.mouseReleaseEvent(_event(QMouseEvent.Type.MouseButtonRelease, x, y))


def _event(kind, x, y) -> QMouseEvent:
    return QMouseEvent(kind, QPointF(x, y), Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def drag_handle(widget, handle: Handle, to_x: float, to_y: float,
                steps: int = 5) -> tuple[list, list]:
    """A whole gesture on one handle, in `steps` moves. Returns what
    each signal saw."""
    seen: list = []
    done: list = []
    widget.changed.connect(seen.append)
    widget.committed.connect(done.append)
    x, y = handle_points(widget.spec, widget.box())[handle]
    press(widget, x, y)
    for step in range(1, steps + 1):
        move(widget, x + (to_x - x) * step / steps,
             y + (to_y - y) * step / steps)
    release(widget, to_x, to_y)
    return seen, done


# -- the gesture --------------------------------------------------------------

def test_a_drag_emits_on_every_move_and_commits_once(editor) -> None:
    box = editor.box()
    seen, done = drag_handle(editor, Handle.ATTACK, x_of(0.35, box),
                             editor.box().y)
    assert len(seen) == 5                     # one per move: the live feel
    assert len(done) == 1                     # one undo entry
    assert done[0] is editor.spec
    assert seen[-1].attack == pytest.approx(0.35, abs=0.01)


def test_a_press_that_misses_every_handle_starts_nothing(editor) -> None:
    seen: list = []
    editor.changed.connect(seen.append)
    box = editor.box()
    press(editor, x_of(0.5, box), box.y + box.h - 2.0)   # low, on nothing
    assert not editor.dragging()
    move(editor, x_of(0.9, box), box.y)
    release(editor, x_of(0.9, box), box.y)
    assert seen == []


def test_a_drag_that_ends_where_it_started_still_commits(editor) -> None:
    """The caller's no-op guard decides whether that was an edit, the
    way it does for a typed field — the widget just says the gesture is
    over."""
    before = editor.spec
    x, y = handle_points(before, editor.box())[Handle.ATTACK]
    done: list = []
    editor.committed.connect(done.append)
    press(editor, x, y)
    release(editor, x, y)
    assert done == [before]
    assert editor.spec == before


def test_the_handle_stops_at_its_neighbour_while_dragging(editor) -> None:
    """Dragged well past the swell point, the attack stops beside it —
    and what the widget SHOWS is the stopped shape, so it can never
    emit something that will not play."""
    box = editor.box()
    seen, _done = drag_handle(editor, Handle.ATTACK, x_of(1.5, box), box.y)
    assert seen[-1].attack < editor.spec.swell_pos
    assert all(s.attack < s.swell_pos for s in seen)


def test_the_swell_point_drags_both_ways(editor) -> None:
    box = editor.box()
    seen, done = drag_handle(editor, Handle.SWELL, x_of(0.6, box),
                             box.y + 0.4 * box.h)
    assert done[0].swell_pos == pytest.approx(0.6, abs=0.01)
    assert done[0].swell_level == pytest.approx(0.6, abs=0.02)


def test_a_resync_is_ignored_mid_drag(editor) -> None:
    """A preview comes straight back as a resync; it must not rewrite
    what the hand is holding (the LiveField rule)."""
    box = editor.box()
    x, y = handle_points(editor.spec, box)[Handle.ATTACK]
    press(editor, x, y)
    move(editor, x_of(0.4, box), y)
    held = editor.spec
    editor.set_spec(SPEC)
    assert editor.spec == held
    release(editor, x_of(0.4, box), y)
    editor.set_spec(SPEC)                     # and it lands again after
    assert editor.spec == SPEC


# -- the picture --------------------------------------------------------------

def test_the_drawn_curve_is_the_envelope_that_plays(editor) -> None:
    """Sampled, not guessed: every drawn point sits on the envelope the
    score runs, easings and all."""
    box = editor.box()
    envelope = spec_envelope(editor.spec, 1.0, 1.0)
    for point in editor._curve(box):
        frac = (point.x() - box.x) / box.w
        level = 1.0 - (point.y() - box.y) / box.h
        assert level == pytest.approx(envelope.value_at(frac), abs=1e-9)


def test_an_instant_rise_is_drawn_as_the_step_it_is(editor) -> None:
    """With no attack the level is up AT the trigger. The curve starts
    from nothing anyway, so the picture shows the vertical edge instead
    of opening part-way up the box with no explanation."""
    editor.set_spec(EnvelopeSpec(attack=0.0, sustain=1.0, swell_on=False,
                                 swell_pos=0.5, swell_level=1.0,
                                 release=1.0))
    box = editor.box()
    first, second = editor._curve(box)[:2]
    assert (first.x(), first.y()) == (box.x, box.y + box.h)   # at nothing
    assert second.x() == box.x and second.y() == box.y        # and full


def test_it_paints_at_any_size(editor, qapp) -> None:
    """A widget is laid out before it is sized, and a zero-height box
    must not raise."""
    editor.repaint()
    editor.resize(250, 20)
    editor.repaint()
    editor.resize(0, 0)
    editor.repaint()


# -- the consumption path -----------------------------------------------------

def test_a_drag_builds_a_valid_envelope_through_the_glow_path(editor) -> None:
    """The integration test: drag a handle, write what it emits into the
    document keys the glow uses, and read it back out the way
    `build_presets` does. What plays is what was dragged."""
    box = editor.box()
    _seen, done = drag_handle(editor, Handle.RELEASE, x_of(0.55, box), box.y)
    dragged = done[0]
    params = {"attack": dragged.attack, "sustain": dragged.sustain,
              "swell_on": dragged.swell_on, "swell_pos": dragged.swell_pos,
              "swell_level": dragged.swell_level, "release": dragged.release}
    shape = read_glow_shape(params)
    assert shape == dragged                   # nothing was corrected on read
    envelope = glow_track(shape, 1.0, 2.0)    # a two-second note
    assert envelope.value_at(0.0) == 0.0
    assert envelope.value_at(2.0) == 0.0      # out exactly as the note stops
    assert envelope.value_at(2.0 * (1.0 - dragged.release)) \
        == pytest.approx(dragged.sustain)
