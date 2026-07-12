"""Commands + UndoStack (PHASES 4.5 groundwork, CLAUDE.md rule 8).

Every command: apply is pure (the before-doc is untouched), validation
raises CommandError, and the stack's undo/redo return exact document
values without re-running apply.
"""
from __future__ import annotations

import pytest

from scoreanim.core.project import (AddSwingRegion, AddTempoEvent, ApplyTaps,
                                    CommandError, ImportTempoSetup,
                                    MoveTempoEvent, ProjectDoc,
                                    RemoveSwingRegion, RemoveTapSession,
                                    RemoveTempoEvent, SetGlobalSwing,
                                    SetOffset, SetPartColor, SetSwingRegion,
                                    TimingConfig, UndoStack)
from scoreanim.core.score.identity import PartId
from scoreanim.core.timing import SwingRegion, Tap, TapSession, TempoEvent


@pytest.fixture
def doc() -> ProjectDoc:
    return ProjectDoc(timing=TimingConfig(
        offset_seconds=1.5,
        tempo_events=(TempoEvent(0.0, 120.0), TempoEvent(16.0, 90.0)),
    ))


SESSION = TapSession(unit=1.0, taps=(
    Tap(4.0, 3.50), Tap(5.0, 4.00), Tap(6.0, 4.50), Tap(7.0, 5.00)))


# -- tempo events -----------------------------------------------------------

def test_add_tempo_event(doc) -> None:
    out = AddTempoEvent(8.0, 100.0).apply(doc)
    assert out.timing.tempo_events == (
        TempoEvent(0.0, 120.0), TempoEvent(8.0, 100.0), TempoEvent(16.0, 90.0))
    assert doc.timing.tempo_events == (
        TempoEvent(0.0, 120.0), TempoEvent(16.0, 90.0))   # before untouched


def test_add_rejects_duplicate_position(doc) -> None:
    with pytest.raises(CommandError):
        AddTempoEvent(16.0, 100.0).apply(doc)


def test_add_rejects_bad_bpm(doc) -> None:
    with pytest.raises(CommandError):
        AddTempoEvent(8.0, 0.0).apply(doc)
    with pytest.raises(CommandError):
        AddTempoEvent(8.0, float("inf")).apply(doc)


def test_move_tempo_event(doc) -> None:
    out = MoveTempoEvent(16.0, 12.0, 95.0).apply(doc)
    assert out.timing.tempo_events == (
        TempoEvent(0.0, 120.0), TempoEvent(12.0, 95.0))


def test_move_missing_or_colliding(doc) -> None:
    with pytest.raises(CommandError):
        MoveTempoEvent(3.0, 4.0, 100.0).apply(doc)
    with pytest.raises(CommandError):
        MoveTempoEvent(16.0, 0.0, 100.0).apply(doc)       # collides


def test_remove_tempo_event(doc) -> None:
    out = RemoveTempoEvent(16.0).apply(doc)
    assert out.timing.tempo_events == (TempoEvent(0.0, 120.0),)
    with pytest.raises(CommandError):
        RemoveTempoEvent(16.0).apply(out)                 # already gone
    with pytest.raises(CommandError):
        RemoveTempoEvent(0.0).apply(out)                  # last one stays


def test_set_offset(doc) -> None:
    out = SetOffset(2.25).apply(doc)
    assert out.timing.offset_seconds == 2.25
    assert out.timing.tempo_events == doc.timing.tempo_events
    with pytest.raises(CommandError):
        SetOffset(float("nan")).apply(doc)


def test_import_tempo_setup_replaces_events_keeps_swing_and_taps(doc) -> None:
    doc = AddSwingRegion(SwingRegion((0.0, 8.0), 0.6)).apply(doc)
    doc = ApplyTaps(SESSION, (TempoEvent(4.0, 118.0),), (4.0, 8.0),
                    "derive").apply(doc)
    out = ImportTempoSetup(0.5, (TempoEvent(0.0, 110.0),),
                           "testscore.tempo").apply(doc)
    assert out.timing.offset_seconds == 0.5
    assert out.timing.tempo_events == (TempoEvent(0.0, 110.0),)
    assert out.timing.swing_regions == doc.timing.swing_regions
    assert out.timing.tap_sessions == doc.timing.tap_sessions
    with pytest.raises(CommandError):
        ImportTempoSetup(0.0, (), "x.tempo").apply(doc)


# -- taps --------------------------------------------------------------------

def test_apply_taps_splices_within_span_only(doc) -> None:
    derived = (TempoEvent(4.0, 118.0), TempoEvent(6.0, 122.0))
    out = ApplyTaps(SESSION, derived, (4.0, 8.0), "derive").apply(doc)
    # 0.0 (before span) and 16.0 (after span) preserved; derived spliced in
    assert out.timing.tempo_events == (
        TempoEvent(0.0, 120.0), TempoEvent(4.0, 118.0),
        TempoEvent(6.0, 122.0), TempoEvent(16.0, 90.0))
    assert out.timing.tap_sessions == (SESSION,)


def test_apply_taps_replaces_events_inside_span(doc) -> None:
    doc = AddTempoEvent(5.0, 200.0).apply(doc)            # inside the span
    out = ApplyTaps(SESSION, (TempoEvent(4.0, 118.0),), (4.0, 8.0),
                    "derive").apply(doc)
    positions = [e.position for e in out.timing.tempo_events]
    assert positions == [0.0, 4.0, 16.0]                  # 5.0 was replaced


def test_apply_taps_never_duplicates_a_session(doc) -> None:
    once = ApplyTaps(SESSION, (TempoEvent(4.0, 118.0),), (4.0, 8.0),
                     "derive").apply(doc)
    twice = ApplyTaps(SESSION, (TempoEvent(4.0, 119.0),), (4.0, 8.0),
                      "lock").apply(once)
    assert twice.timing.tap_sessions == (SESSION,)


def test_apply_taps_validation(doc) -> None:
    with pytest.raises(CommandError):
        ApplyTaps(SESSION, (), (4.0, 8.0), "derive").apply(doc)
    with pytest.raises(CommandError):                      # outside span
        ApplyTaps(SESSION, (TempoEvent(9.0, 118.0),), (4.0, 8.0),
                  "derive").apply(doc)
    with pytest.raises(CommandError):                      # reversed span
        ApplyTaps(SESSION, (TempoEvent(4.0, 118.0),), (8.0, 4.0),
                  "derive").apply(doc)


def test_remove_tap_session_keeps_derived_events(doc) -> None:
    doc = ApplyTaps(SESSION, (TempoEvent(4.0, 118.0),), (4.0, 8.0),
                    "derive").apply(doc)
    out = RemoveTapSession(0).apply(doc)
    assert out.timing.tap_sessions == ()
    assert out.timing.tempo_events == doc.timing.tempo_events
    with pytest.raises(CommandError):
        RemoveTapSession(0).apply(out)


# -- swing --------------------------------------------------------------------

def test_swing_add_edit_remove(doc) -> None:
    doc = AddSwingRegion(SwingRegion((0.0, 8.0), 0.6)).apply(doc)
    doc = AddSwingRegion(SwingRegion((8.0, 12.0), 0.667)).apply(doc)
    assert [r.span for r in doc.timing.swing_regions] == [(0.0, 8.0),
                                                          (8.0, 12.0)]
    doc = SetSwingRegion((0.0, 8.0), SwingRegion((0.0, 6.0), 0.55)).apply(doc)
    assert doc.timing.swing_regions[0] == SwingRegion((0.0, 6.0), 0.55)
    doc = RemoveSwingRegion((8.0, 12.0)).apply(doc)
    assert [r.span for r in doc.timing.swing_regions] == [(0.0, 6.0)]


def test_set_global_swing(doc) -> None:
    """v1 authoring surface (ruling 2026-07-11): one ratio, whole piece."""
    out = SetGlobalSwing(0.66, 76.0).apply(doc)
    assert out.timing.swing_regions == (SwingRegion((0.0, 76.0), 0.66),)
    # replaces whatever regions exist (collapses to one global)
    doc2 = AddSwingRegion(SwingRegion((0.0, 8.0), 0.6)).apply(doc)
    out2 = SetGlobalSwing(0.62, 76.0).apply(doc2)
    assert out2.timing.swing_regions == (SwingRegion((0.0, 76.0), 0.62),)
    # 0.5 = straight = no regions at all
    assert SetGlobalSwing(0.5, 76.0).apply(out).timing.swing_regions == ()
    # fractional score end is ceiled to a whole beat (validation rule)
    assert SetGlobalSwing(0.6, 75.5).apply(doc).timing.swing_regions[0] \
        .span == (0.0, 76.0)
    with pytest.raises(CommandError):
        SetGlobalSwing(0.4, 76.0).apply(doc)
    with pytest.raises(CommandError):
        SetGlobalSwing(0.6, 0.0).apply(doc)


def test_swing_validation(doc) -> None:
    with pytest.raises(CommandError):                      # overlap
        d = AddSwingRegion(SwingRegion((0.0, 8.0), 0.6)).apply(doc)
        AddSwingRegion(SwingRegion((4.0, 12.0), 0.6)).apply(d)
    with pytest.raises(CommandError):                      # bad ratio
        AddSwingRegion(SwingRegion((0.0, 4.0), 0.4)).apply(doc)
    with pytest.raises(CommandError):                      # fractional span
        AddSwingRegion(SwingRegion((0.5, 4.0), 0.6)).apply(doc)
    with pytest.raises(CommandError):                      # edit missing
        SetSwingRegion((1.0, 2.0), SwingRegion((1.0, 2.0), 0.6)).apply(doc)
    with pytest.raises(CommandError):                      # remove missing
        RemoveSwingRegion((1.0, 2.0)).apply(doc)


# -- style --------------------------------------------------------------------

def test_set_part_color_and_reset(doc) -> None:
    from scoreanim.core.animation import ElementStyle

    p3 = PartId("P3")
    out = SetPartColor(p3, "#cc2222").apply(doc)
    assert out.style.parts == {p3: ElementStyle(color="#cc2222")}
    assert doc.style.parts == {}
    back = SetPartColor(p3, None).apply(out)
    assert back.style.parts == {}                # empty rules are dropped
    with pytest.raises(CommandError):
        SetPartColor(p3, "red").apply(doc)


def test_part_color_and_effect_merge_fieldwise(doc) -> None:
    """Color and effect edits on one part update ONE rule; clearing one
    field keeps the other."""
    from scoreanim.core.animation import ElementStyle
    from scoreanim.core.project import SetPartEffect

    p1 = PartId("P1")
    out = SetPartColor(p1, "#cc2222").apply(doc)
    out = SetPartEffect(p1, "pop").apply(out)
    assert out.style.parts == {p1: ElementStyle(color="#cc2222",
                                                effect="pop")}
    out = SetPartColor(p1, None).apply(out)
    assert out.style.parts == {p1: ElementStyle(effect="pop")}
    out = SetPartEffect(p1, None).apply(out)
    assert out.style.parts == {}
    with pytest.raises(CommandError):
        SetPartEffect(p1, "  ").apply(doc)


def test_set_element_style_override(doc) -> None:
    from scoreanim.core.animation import ElementStyle
    from scoreanim.core.project import SetElementStyle
    from scoreanim.core.score.identity import ElementId

    eid = ElementId("P1:m3:s1:v1:note:0")
    style = ElementStyle(color="#00aa00", effect="pop")
    out = SetElementStyle(eid, style).apply(doc)
    assert out.style.elements == {eid: style}
    back = SetElementStyle(eid, None).apply(out)
    assert back.style.elements == {}
    with pytest.raises(CommandError):
        SetElementStyle(eid, ElementStyle(color="green")).apply(doc)


def test_set_reveal_mode(doc) -> None:
    from scoreanim.core.animation import RevealMode
    from scoreanim.core.project import SetRevealMode

    assert doc.style.reveal_mode is RevealMode.STEPPED
    out = SetRevealMode(RevealMode.CONTINUOUS).apply(doc)
    assert out.style.reveal_mode is RevealMode.CONTINUOUS
    assert doc.style.reveal_mode is RevealMode.STEPPED
    assert out.style.parts == doc.style.parts
    with pytest.raises(CommandError):
        SetRevealMode("continuous").apply(doc)   # type: ignore[arg-type]


def test_set_floor_opacity(doc) -> None:
    from scoreanim.core.project import SetFloorOpacity

    assert doc.style.floor_opacity == 0.3
    out = SetFloorOpacity(0.0).apply(doc)        # 0 is a value, not an error
    assert out.style.floor_opacity == 0.0
    assert doc.style.floor_opacity == 0.3        # source doc untouched
    assert SetFloorOpacity(1.0).apply(doc).style.floor_opacity == 1.0
    assert out.style.parts == doc.style.parts
    for bad in (-0.01, 1.01, float("nan"), float("inf")):
        with pytest.raises(CommandError):
            SetFloorOpacity(bad).apply(doc)


def test_set_presentation_mode(doc) -> None:
    from scoreanim.core.project import PresentationMode, SetPresentationMode

    assert doc.stage.mode is PresentationMode.PAGED
    out = SetPresentationMode(PresentationMode.SYSTEM).apply(doc)
    assert out.stage.mode is PresentationMode.SYSTEM
    assert out.stage.texts == doc.stage.texts    # texts untouched
    assert doc.stage.mode is PresentationMode.PAGED
    with pytest.raises(CommandError):
        SetPresentationMode("system").apply(doc)  # type: ignore[arg-type]
    stack = UndoStack()
    d1 = stack.execute(SetPresentationMode(PresentationMode.SYSTEM), doc)
    assert stack.undo() == doc
    assert stack.redo() == d1


def test_floor_opacity_undo_round_trip(doc) -> None:
    from scoreanim.core.project import SetFloorOpacity

    stack = UndoStack()
    d1 = stack.execute(SetFloorOpacity(0.0), doc)
    assert d1.style.floor_opacity == 0.0
    assert stack.undo() == doc
    assert stack.redo() == d1
    assert stack.undo_text() == "set floor opacity"


# -- undo stack ---------------------------------------------------------------

def test_stack_execute_undo_redo(doc) -> None:
    stack = UndoStack()
    d1 = stack.execute(AddTempoEvent(8.0, 100.0), doc)
    d2 = stack.execute(SetOffset(2.0), d1)
    assert stack.undo_text() == "set offset"
    assert stack.undo() == d1
    assert stack.undo() == doc
    assert not stack.can_undo
    assert stack.redo() == d1
    assert stack.redo_text() == "set offset"
    assert stack.redo() == d2
    assert not stack.can_redo


def test_stack_truncates_redo_tail(doc) -> None:
    stack = UndoStack()
    d1 = stack.execute(AddTempoEvent(8.0, 100.0), doc)
    stack.execute(SetOffset(2.0), d1)
    stack.undo()
    d2b = stack.execute(SetOffset(3.0), d1)
    assert not stack.can_redo
    assert stack.undo() == d1
    assert stack.redo() == d2b


def test_stack_failed_command_pushes_nothing(doc) -> None:
    stack = UndoStack()
    with pytest.raises(CommandError):
        stack.execute(AddTempoEvent(16.0, 100.0), doc)     # duplicate
    assert not stack.can_undo and not stack.can_redo


def test_dirty_tracking(doc) -> None:
    stack = UndoStack()
    assert not stack.is_dirty
    d1 = stack.execute(SetOffset(2.0), doc)
    assert stack.is_dirty
    stack.mark_saved()
    assert not stack.is_dirty
    stack.undo()
    assert stack.is_dirty
    stack.redo()
    assert not stack.is_dirty                              # back at saved
    stack.execute(SetOffset(3.0), d1)
    stack.undo()
    assert not stack.is_dirty


def test_dirty_when_saved_state_truncated(doc) -> None:
    stack = UndoStack()
    d1 = stack.execute(SetOffset(2.0), doc)
    stack.execute(SetOffset(3.0), d1)
    stack.mark_saved()                                     # saved at depth 2
    stack.undo()
    stack.execute(SetOffset(4.0), d1)                      # truncates saved
    stack.undo()                                           # depth 1 again
    assert stack.is_dirty                                  # saved state gone
