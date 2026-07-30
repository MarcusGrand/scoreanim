"""Commands + UndoStack (PHASES 4.5 groundwork, CLAUDE.md rule 8).

Every command: apply is pure (the before-doc is untouched), validation
raises CommandError, and the stack's undo/redo return exact document
values without re-running apply.
"""
from __future__ import annotations

import pytest

from scoreanim.core.project import (AddSwingRegion, AddTempoEvent, AlignBeat,
                                    ApplyTaps, SetBeatLock,
                                    CommandError, ImportTempoSetup,
                                    MoveTempoEvent, ProjectDoc,
                                    RemoveSwingRegion, RemoveTapSession,
                                    RemoveTempoEvent, SetDefaultEffect,
                                    SetEffectParam, SetGlobalSwing,
                                    SetOffset, SetPartColor, SetSwingRegion,
                                    TimingConfig, UndoStack)
from scoreanim.core.score.identity import PartId
from scoreanim.core.timing import (SwingRegion, Tap, TapSession, TempoEvent,
                                   TempoMap, swing_warp)


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


# -- align a grid line ------------------------------------------------------
#
# The maths is pinned in tests/test_retime.py; these pin the command's own
# two jobs — audio seconds minus the offset, and beats warped by the
# document's swing — plus rule 8.

def _at(doc, beat: float) -> float:
    """Audio seconds of a beat, the way the lane draws it."""
    return doc.timing.offset_seconds + TempoMap(
        list(doc.timing.tempo_events)).seconds_at(beat)


def test_align_beat_puts_the_beat_at_the_audio_second_and_locks_it(doc
                                                                  ) -> None:
    out = AlignBeat(8.0, _at(doc, 8.0) + 0.4).apply(doc)
    assert _at(out, 8.0) == pytest.approx(_at(doc, 8.0) + 0.4)
    assert out.timing.locked_beats == (8.0,)     # the drag pinned it
    assert out.timing.offset_seconds == doc.timing.offset_seconds
    assert doc.timing.tempo_events == (
        TempoEvent(0.0, 120.0), TempoEvent(16.0, 90.0))      # before untouched
    assert doc.timing.locked_beats == ()


def test_align_beat_evens_out_the_span_back_to_the_previous_lock(doc) -> None:
    doc = SetBeatLock(4.0, True).apply(doc)
    out = AlignBeat(12.0, _at(doc, 12.0) + 0.5).apply(doc)
    m = TempoMap(list(out.timing.tempo_events))
    steps = [round(m.seconds_at(b + 1.0) - m.seconds_at(b), 9)
             for b in range(4, 12)]
    assert len(set(steps)) == 1                  # 4 -> 12 evenly spaced
    assert _at(out, 4.0) == pytest.approx(_at(doc, 4.0))     # the lock holds
    assert out.timing.locked_beats == (4.0, 12.0)


def test_align_beat_leaves_the_tempo_after_it_alone(doc) -> None:
    """No lock after the dragged beat: the tail keeps its tempo and
    slides, so every later beat moves by the same amount."""
    out = AlignBeat(8.0, _at(doc, 8.0) + 0.4).apply(doc)
    for beat in (12.0, 20.0, 40.0):
        assert _at(out, beat) == pytest.approx(_at(doc, beat) + 0.4)


def test_a_lock_after_the_drag_pins_the_tail(doc) -> None:
    doc = SetBeatLock(16.0, True).apply(doc)
    out = AlignBeat(8.0, _at(doc, 8.0) + 0.4).apply(doc)
    assert _at(out, 16.0) == pytest.approx(_at(doc, 16.0))
    assert _at(out, 40.0) == pytest.approx(_at(doc, 40.0))


def test_align_beat_keep_shape_preserves_tempo_detail(doc) -> None:
    doc = AddTempoEvent(6.0, 60.0).apply(doc)    # detail inside the span
    flat = AlignBeat(12.0, _at(doc, 12.0) + 0.3).apply(doc)
    kept = AlignBeat(12.0, _at(doc, 12.0) + 0.3, flatten=False).apply(doc)
    assert 6.0 not in [e.position for e in flat.timing.tempo_events]
    assert 6.0 in [e.position for e in kept.timing.tempo_events]


def test_align_beat_warps_the_beat_through_swing(doc) -> None:
    """An off-beat inside a swing region does not sound where the tempo
    map alone would put it, so the command warps before retiming."""
    swung = AddSwingRegion(SwingRegion((0.0, 16.0), 0.62)).apply(doc)
    swung = SetBeatLock(4.0, True).apply(swung)
    swung = SetBeatLock(8.0, True).apply(swung)
    target = _at(swung, swing_warp(6.5, swung.timing.swing_regions)) + 0.2
    out = AlignBeat(6.5, target).apply(swung)
    warped = swing_warp(6.5, out.timing.swing_regions)
    assert _at(out, warped) == pytest.approx(target)
    assert _at(out, 4.0) == pytest.approx(_at(swung, 4.0))   # locks hold
    assert _at(out, 8.0) == pytest.approx(_at(swung, 8.0))


def test_align_beat_rejects_the_unreachable(doc) -> None:
    doc = SetBeatLock(4.0, True).apply(doc)
    for seconds in (float("nan"), _at(doc, 4.0) - 1.0, 1e6):
        with pytest.raises(CommandError):
            AlignBeat(8.0, seconds).apply(doc)
    with pytest.raises(CommandError):            # nothing to span at beat 0
        AlignBeat(0.0, 1.0).apply(doc)


def test_dragging_a_locked_line_moves_it_and_keeps_it_locked(doc) -> None:
    """A lock anchors its NEIGHBOURS; it never makes the line itself
    immovable, so there is no refusal path to explain."""
    doc = SetBeatLock(8.0, True).apply(doc)
    out = AlignBeat(8.0, _at(doc, 8.0) + 0.3).apply(doc)
    assert _at(out, 8.0) == pytest.approx(_at(doc, 8.0) + 0.3)
    assert out.timing.locked_beats == (8.0,)


def test_import_tempo_setup_clears_the_locks(doc) -> None:
    """A sidecar replaces every tempo event, so "this beat is where I put
    it" is no longer true of any of them."""
    doc = SetBeatLock(8.0, True).apply(doc)
    out = ImportTempoSetup(0.5, (TempoEvent(0.0, 110.0),), "x.tempo").apply(doc)
    assert out.timing.locked_beats == ()


def test_align_beat_is_one_undo_entry_covering_the_lock(doc) -> None:
    stack = UndoStack()
    out = stack.execute(AlignBeat(8.0, _at(doc, 8.0) + 0.4), doc)
    assert stack.undo_text() == "align beat"
    assert out.timing.tempo_events != doc.timing.tempo_events   # non-vacuous
    assert out.timing.locked_beats == (8.0,)
    back = stack.undo()
    assert back.timing.tempo_events == doc.timing.tempo_events
    assert back.timing.locked_beats == ()        # the lock went back too


def test_set_beat_lock_toggles(doc) -> None:
    locked = SetBeatLock(8.0, True).apply(doc)
    assert locked.timing.locked_beats == (8.0,)
    assert SetBeatLock(4.0, True).apply(locked).timing.locked_beats == (4.0,
                                                                        8.0)
    assert SetBeatLock(8.0, False).apply(locked).timing.locked_beats == ()
    assert SetBeatLock(99.0, False).apply(locked).timing.locked_beats == (8.0,)
    assert doc.timing.locked_beats == ()         # before untouched
    with pytest.raises(CommandError):
        SetBeatLock(float("inf"), True).apply(doc)
    assert SetBeatLock(8.0, True).describe() == "lock beat"
    assert SetBeatLock(8.0, False).describe() == "unlock beat"


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


def test_set_default_effect_and_clear(doc) -> None:
    out = SetDefaultEffect("pop").apply(doc)
    assert out.style.default_effect == "pop"
    assert doc.style.default_effect is None      # source doc untouched
    # a name from the future is intent, not an error (fail-soft later)
    assert SetDefaultEffect("shimmer").apply(doc).style.default_effect \
        == "shimmer"
    assert SetDefaultEffect(None).apply(out).style.default_effect is None
    with pytest.raises(CommandError):
        SetDefaultEffect("   ").apply(doc)


def test_set_effect_param_sparse_semantics(doc) -> None:
    d2 = SetEffectParam("pop", "scale", 2.0).apply(doc)
    assert d2.style.effect_params == {"pop": {"scale": 2.0}}
    d3 = SetEffectParam("pop", "note_value", True).apply(d2)
    assert d3.style.effect_params == {"pop": {"scale": 2.0,
                                              "note_value": True}}
    # None deletes the key; an emptied param dict drops entirely
    d4 = SetEffectParam("pop", "scale", None).apply(d3)
    assert d4.style.effect_params == {"pop": {"note_value": True}}
    d5 = SetEffectParam("pop", "note_value", None).apply(d4)
    assert d5.style.effect_params == {}
    # deleting an absent key is a no-op, not an error
    assert SetEffectParam("pop", "zzz", None).apply(doc) \
        .style.effect_params == {}
    # other presets' entries are untouched
    d6 = SetEffectParam("shimmer", "wobble", 1.5).apply(d3)
    assert d6.style.effect_params["pop"] == {"scale": 2.0,
                                             "note_value": True}


def test_set_effect_param_validates_type_and_finiteness_only(doc) -> None:
    for bad in (float("nan"), float("inf"), "big", (1, 2)):
        with pytest.raises(CommandError):
            SetEffectParam("pop", "scale", bad).apply(doc)  # type: ignore
    with pytest.raises(CommandError):
        SetEffectParam("", "scale", 1.0).apply(doc)
    with pytest.raises(CommandError):
        SetEffectParam("pop", "", 1.0).apply(doc)
    # no range policy here — clamps live at consumption (build_presets)
    assert SetEffectParam("pop", "scale", 99.0).apply(doc) \
        .style.effect_params["pop"]["scale"] == 99.0


def test_reset_effect_settings_one_step_keeps_foreign_presets(doc) -> None:
    from scoreanim.core.project import ResetEffectSettings, SetDefaultEffect

    stack = UndoStack()
    d = stack.execute(SetDefaultEffect("pop"), doc)
    d = stack.execute(SetEffectParam("pop", "scale", 2.0), d)
    d = stack.execute(SetEffectParam("pop", "note_value", True), d)
    d = stack.execute(SetEffectParam("shimmer", "wobble", 1.5), d)
    before_reset = d
    d = stack.execute(ResetEffectSettings(), d)
    # pre-M4 defaults reassert: no default, no pop params — but a
    # foreign preset's params survive (raw-round-trip guarantee)
    assert d.style.default_effect is None
    assert d.style.effect_params == {"shimmer": {"wobble": 1.5}}
    # ONE undo step restores every knob at once
    assert stack.undo() == before_reset
    assert before_reset.style.default_effect == "pop"
    assert before_reset.style.effect_params["pop"] == {"scale": 2.0,
                                                       "note_value": True}


def test_effect_param_undo_restores_the_prior_value(doc) -> None:
    stack = UndoStack()
    d1 = stack.execute(SetEffectParam("pop", "scale", 2.0), doc)
    d2 = stack.execute(SetEffectParam("pop", "scale", 3.0), d1)
    assert d2.style.effect_params["pop"]["scale"] == 3.0
    assert stack.undo() == d1
    assert d1.style.effect_params["pop"]["scale"] == 2.0
    assert stack.undo() == doc
    assert stack.redo() == d1


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


def test_set_hide_empty_staves(doc) -> None:
    from scoreanim.core.project import SetHideEmptyStaves

    assert doc.hide_empty_staves is True         # new-doc default
    out = SetHideEmptyStaves(False).apply(doc)
    assert out.hide_empty_staves is False
    assert doc.hide_empty_staves is True
    assert SetHideEmptyStaves(False).describe() == "show empty staves"
    assert SetHideEmptyStaves(True).describe() == "hide empty staves"
    with pytest.raises(CommandError):
        SetHideEmptyStaves("yes").apply(doc)  # type: ignore[arg-type]
    stack = UndoStack()
    d1 = stack.execute(SetHideEmptyStaves(False), doc)
    assert stack.undo() == doc
    assert stack.redo() == d1


def test_set_hide_first_system(doc) -> None:
    from scoreanim.core.project import SetHideFirstSystem

    assert doc.hide_first_system is False        # convention: first full
    out = SetHideFirstSystem(True).apply(doc)
    assert out.hide_first_system is True
    assert doc.hide_first_system is False
    assert SetHideFirstSystem(True).describe() \
        == "hide empty staves on first system"
    assert SetHideFirstSystem(False).describe() \
        == "show staves on first system"
    with pytest.raises(CommandError):
        SetHideFirstSystem("yes").apply(doc)  # type: ignore[arg-type]
    stack = UndoStack()
    d1 = stack.execute(SetHideFirstSystem(True), doc)
    assert stack.undo() == doc
    assert stack.redo() == d1


def test_set_system_break(doc) -> None:
    """M5.1: the sparse break delta. FORCE/SUPPRESS write an entry; a
    None mode POPS it, leaving the doc equal to the unedited one (the
    SetElementStyle idiom, so the gesture is perfectly reversible)."""
    from scoreanim.core.project import SetSystemBreak, SystemBreak

    assert doc.system_break_overrides == {}
    forced = SetSystemBreak(3, SystemBreak.FORCE).apply(doc)
    assert forced.system_break_overrides == {3: SystemBreak.FORCE}
    assert doc.system_break_overrides == {}          # apply is pure

    both = SetSystemBreak(9, SystemBreak.SUPPRESS).apply(forced)
    assert both.system_break_overrides == {3: SystemBreak.FORCE,
                                           9: SystemBreak.SUPPRESS}

    # a second toggle on the same ordinal REPLACES rather than accretes
    flipped = SetSystemBreak(3, SystemBreak.SUPPRESS).apply(both)
    assert flipped.system_break_overrides[3] is SystemBreak.SUPPRESS

    # None pops, and the doc goes back to being EQUAL to the unedited one
    cleared = SetSystemBreak(3, None).apply(forced)
    assert cleared.system_break_overrides == {}
    assert cleared == doc
    # popping an ordinal that was never set is a no-op, not an error
    assert SetSystemBreak(7, None).apply(doc) == doc

    assert SetSystemBreak(3, SystemBreak.FORCE).describe() \
        == "force system break"
    assert SetSystemBreak(3, SystemBreak.SUPPRESS).describe() \
        == "suppress system break"
    assert SetSystemBreak(3, None).describe() == "clear system break"


def test_set_system_break_rejects_non_ordinals(doc) -> None:
    """Ordinals are 1-based. The command deliberately does NOT know the
    engraved layout, so an ordinal PAST the end is stored and left inert
    (D5/D10) — only a non-ordinal is refused."""
    from scoreanim.core.project import SetSystemBreak, SystemBreak

    for bad in (0, -1):
        with pytest.raises(CommandError, match=">= 1"):
            SetSystemBreak(bad, SystemBreak.FORCE).apply(doc)
    past_the_end = SetSystemBreak(9999, SystemBreak.FORCE).apply(doc)
    assert past_the_end.system_break_overrides == {9999: SystemBreak.FORCE}


def test_system_break_undo_steps_through_each_toggle(doc) -> None:
    """Rule 8: ONE undo entry per toggle, each stepping individually."""
    from scoreanim.core.project import SetSystemBreak, SystemBreak

    stack = UndoStack()
    d1 = stack.execute(SetSystemBreak(3, SystemBreak.FORCE), doc)
    d2 = stack.execute(SetSystemBreak(9, SystemBreak.SUPPRESS), d1)
    d3 = stack.execute(SetSystemBreak(3, None), d2)          # toggle back
    assert d3.system_break_overrides == {9: SystemBreak.SUPPRESS}

    assert stack.undo() == d2
    assert stack.undo() == d1
    assert stack.undo() == doc
    assert stack.redo() == d1
    assert stack.redo() == d2
    assert stack.redo() == d3


def test_set_system_break_also_writes_several_ordinals(doc) -> None:
    """M5.7/D12: the fat-apply widening. One gesture ("move to previous
    system") needs two breaks written, and rule 8 counts gestures — so
    `also` carries the extra entries into the same apply()."""
    from scoreanim.core.project import SetSystemBreak, SystemBreak

    move = SetSystemBreak(5, SystemBreak.SUPPRESS,
                          ((7, SystemBreak.FORCE),))
    assert move.entries == ((5, SystemBreak.SUPPRESS),
                            (7, SystemBreak.FORCE))
    moved = move.apply(doc)
    assert moved.system_break_overrides == {5: SystemBreak.SUPPRESS,
                                            7: SystemBreak.FORCE}
    assert doc.system_break_overrides == {}          # apply is pure

    # a clear travels in `also` too — the move-up policy prefers it
    mixed = SetSystemBreak(5, None, ((7, None),)).apply(moved)
    assert mixed == doc
    # and a bad ordinal anywhere in the set is refused, wholesale
    with pytest.raises(CommandError, match=">= 1"):
        SetSystemBreak(5, SystemBreak.SUPPRESS, ((0, None),)).apply(doc)


def test_set_page_break_writes_pops_and_describes(doc) -> None:
    """M6.1: SetSystemBreak's sibling, same sparse-delta contract."""
    from scoreanim.core.project import PageBreak, SetPageBreak

    assert doc.page_break_overrides == {}
    forced = SetPageBreak(3, PageBreak.FORCE).apply(doc)
    assert forced.page_break_overrides == {3: PageBreak.FORCE}
    assert doc.page_break_overrides == {}            # apply is pure
    # and it leaves the OTHER map alone
    assert forced.system_break_overrides == {}

    both = SetPageBreak(9, PageBreak.SUPPRESS).apply(forced)
    assert both.page_break_overrides == {3: PageBreak.FORCE,
                                         9: PageBreak.SUPPRESS}
    assert SetPageBreak(3, PageBreak.SUPPRESS).apply(both) \
        .page_break_overrides[3] is PageBreak.SUPPRESS

    cleared = SetPageBreak(3, None).apply(forced)
    assert cleared.page_break_overrides == {}
    assert cleared == doc
    assert SetPageBreak(7, None).apply(doc) == doc   # popping nothing

    assert SetPageBreak(3, PageBreak.FORCE).describe() == "force page break"
    assert SetPageBreak(3, PageBreak.SUPPRESS).describe() \
        == "suppress page break"
    assert SetPageBreak(3, None).describe() == "clear page break"

    for bad in (0, -1):
        with pytest.raises(CommandError, match=">= 1"):
            SetPageBreak(bad, PageBreak.FORCE).apply(doc)
    # past the end is STORED and left inert — the command does not know
    # the engraved layout (rule 5's staleness trade, D8's warning tells)
    assert SetPageBreak(9999, PageBreak.FORCE).apply(doc) \
        .page_break_overrides == {9999: PageBreak.FORCE}


def test_a_break_command_writes_both_maps_in_one_step(doc) -> None:
    """D3's prevention half: the one INCOHERENT pair the two maps admit
    is page FORCE + system SUPPRESS at one ordinal, and the toggle
    clears the contradiction in the SAME gesture rather than leaving the
    document arguing with itself. Rule 8 counts gestures — one entry."""
    from scoreanim.core.project import (PageBreak, SetPageBreak,
                                        SetSystemBreak, SystemBreak)

    stale = SetSystemBreak(9, SystemBreak.SUPPRESS).apply(doc)
    stack = UndoStack()
    fixed = stack.execute(
        SetPageBreak(9, PageBreak.FORCE, also_system=((9, None),)), stale)
    assert fixed.page_break_overrides == {9: PageBreak.FORCE}
    assert fixed.system_break_overrides == {}
    assert stack.undo_text() == "change breaks"
    assert stack.undo() == stale                     # ONE entry restores both

    # and the mirror: the system toggle clears a contradicting page FORCE
    stale_page = SetPageBreak(9, PageBreak.FORCE).apply(doc)
    back = SetSystemBreak(9, SystemBreak.SUPPRESS,
                          also_page=((9, None),)).apply(stale_page)
    assert back.system_break_overrides == {9: SystemBreak.SUPPRESS}
    assert back.page_break_overrides == {}
    assert SetSystemBreak(9, SystemBreak.SUPPRESS,
                          also_page=((9, None),)).describe() == "change breaks"


def test_page_break_also_carries_extra_page_ordinals(doc) -> None:
    from scoreanim.core.project import PageBreak, SetPageBreak

    fat = SetPageBreak(5, PageBreak.SUPPRESS, ((9, PageBreak.FORCE),))
    assert fat.entries == ((5, PageBreak.SUPPRESS), (9, PageBreak.FORCE))
    assert fat.apply(doc).page_break_overrides == {5: PageBreak.SUPPRESS,
                                                   9: PageBreak.FORCE}
    assert fat.describe() == "change page breaks"
    with pytest.raises(CommandError, match=">= 1"):
        SetPageBreak(5, PageBreak.SUPPRESS, ((0, None),)).apply(doc)


def test_system_break_undo_counts_the_gesture_not_the_ordinals(doc) -> None:
    """Rule 8 on the composed gesture: two ordinals, ONE undo entry."""
    from scoreanim.core.project import SetSystemBreak, SystemBreak

    stack = UndoStack()
    moved = stack.execute(SetSystemBreak(5, SystemBreak.SUPPRESS,
                                         ((7, SystemBreak.FORCE),)), doc)
    assert len(moved.system_break_overrides) == 2
    assert stack.undo_text() == "change system breaks"
    assert stack.undo() == doc
    assert not stack.can_undo
    assert stack.redo() == moved


def test_system_break_phrase_is_true_for_every_caller(doc) -> None:
    """The M3.5 rule: describe() names what the mechanism wrote, never
    the gesture that happened to call it. The menu action's own label
    says "Move to Previous System"; the Edit menu says what changed."""
    from scoreanim.core.project import SetSystemBreak, SystemBreak

    assert SetSystemBreak(5, SystemBreak.SUPPRESS).describe() \
        == "suppress system break"
    assert SetSystemBreak(5, SystemBreak.SUPPRESS,
                          ((7, SystemBreak.FORCE),)).describe() \
        == "change system breaks"


def test_score_setup_carries_hide_first_system(doc) -> None:
    from scoreanim.core.project import ApplyScoreSetup

    out = ApplyScoreSetup((), (), True, (), True).apply(doc)
    assert out.hide_first_system is True
    assert ApplyScoreSetup((), (), True, ()).apply(doc) \
        .hide_first_system is False              # default: convention kept


def test_floor_opacity_undo_round_trip(doc) -> None:
    from scoreanim.core.project import SetFloorOpacity

    stack = UndoStack()
    d1 = stack.execute(SetFloorOpacity(0.0), doc)
    assert d1.style.floor_opacity == 0.0
    assert stack.undo() == doc
    assert stack.redo() == d1
    assert stack.undo_text() == "set floor opacity"


# -- stage texts (Phase 9.1) --------------------------------------------------

def _stext(element_id: str, y: float = 60.0, font_size: float = 40.0,
           page: int = 1, content: str | None = None,
           **kw) -> "StageTextElement":
    from scoreanim.core.project import StageTextElement
    return StageTextElement(element_id=element_id,
                            content=content or element_id, page=page,
                            x=100.0, y=y, anchor="start",
                            font_size=font_size, **kw)


@pytest.fixture
def stage_doc() -> ProjectDoc:
    from scoreanim.core.project import StageConfig
    return ProjectDoc(stage=StageConfig(texts=(
        _stext("stage:title", y=115.0, font_size=100.0),
        _stext("stage:composer", y=215.0, font_size=50.0),
    )))


def test_edit_stage_text_replaces_content_position_style(stage_doc) -> None:
    from scoreanim.core.project import EditStageText
    new = _stext("stage:title", y=90.0, font_size=80.0, content="New Title",
                 bold=True, color="#336699")
    out = EditStageText("stage:title", new).apply(stage_doc)
    assert out.stage.texts == (new, stage_doc.stage.texts[1])
    assert stage_doc.stage.texts[0].content == "stage:title"   # before untouched


def test_edit_stage_text_validation(stage_doc) -> None:
    from dataclasses import replace as rep

    from scoreanim.core.project import EditStageText
    ok = _stext("stage:title")
    with pytest.raises(CommandError, match="no stage text"):
        EditStageText("stage:nope", _stext("stage:nope")).apply(stage_doc)
    with pytest.raises(CommandError, match="id cannot change"):
        EditStageText("stage:title", _stext("stage:renamed")).apply(stage_doc)
    with pytest.raises(CommandError, match="page cannot change"):
        EditStageText("stage:title", rep(ok, page=2)).apply(stage_doc)
    with pytest.raises(CommandError, match="blank"):
        EditStageText("stage:title", rep(ok, content="  ")).apply(stage_doc)
    with pytest.raises(CommandError, match="bad anchor"):
        EditStageText("stage:title", rep(ok, anchor="left")).apply(stage_doc)
    with pytest.raises(CommandError, match="bad font size"):
        EditStageText("stage:title", rep(ok, font_size=0.0)).apply(stage_doc)
    with pytest.raises(CommandError, match="bad color"):
        EditStageText("stage:title", rep(ok, color="red")).apply(stage_doc)
    with pytest.raises(CommandError, match="not finite"):
        EditStageText("stage:title",
                      rep(ok, y=float("nan"))).apply(stage_doc)
    with pytest.raises(CommandError, match="bad band"):
        EditStageText("stage:title", ok, band=float("inf")).apply(stage_doc)


def test_edit_stage_text_refits_whole_header_block(stage_doc) -> None:
    from scoreanim.core.project import EditStageText
    # dragging the title down past the band re-fits BOTH header texts in
    # the same resulting doc — one command, one undo step
    edited = _stext("stage:title", y=400.0, font_size=100.0)
    out = EditStageText("stage:title", edited, band=300.0).apply(stage_doc)
    title, composer = out.stage.texts
    s = (0.9 * 300.0 - 15.0) / ((400.0 + 0.25 * 100.0) - 15.0)
    assert title.y == pytest.approx(15.0 + (400.0 - 15.0) * s)
    assert title.font_size == pytest.approx(100.0 * s)
    assert composer.y == pytest.approx(15.0 + (215.0 - 15.0) * s)
    assert composer.font_size == pytest.approx(50.0 * s)
    assert stage_doc.stage.texts[1].font_size == 50.0    # before untouched


def test_edit_stage_text_skips_overlay_texts_in_refit(stage_doc) -> None:
    from dataclasses import replace as rep

    from scoreanim.core.project import OVERLAY_PREFIX, EditStageText
    overlay = _stext(OVERLAY_PREFIX + "P1:m1:s1:v0:text:0",
                     y=500.0, font_size=40.0)
    doc = rep(stage_doc, stage=rep(stage_doc.stage,
                                   texts=stage_doc.stage.texts + (overlay,)))
    edited = _stext("stage:title", y=400.0, font_size=100.0)
    out = EditStageText("stage:title", edited, band=300.0).apply(doc)
    assert out.stage.texts[2] == overlay     # untouched, position and all
    assert out.stage.texts[1].font_size < 50.0   # header sibling refitted


def test_edit_stage_text_no_refit_without_band(stage_doc) -> None:
    from scoreanim.core.project import EditStageText
    edited = _stext("stage:title", y=400.0, font_size=100.0)
    out = EditStageText("stage:title", edited).apply(stage_doc)
    assert out.stage.texts == (edited, stage_doc.stage.texts[1])
    big = EditStageText("stage:title", edited, band=5000.0).apply(stage_doc)
    assert big.stage.texts == (edited, stage_doc.stage.texts[1])


def test_edit_stage_text_undo_round_trip(stage_doc) -> None:
    from scoreanim.core.project import EditStageText
    stack = UndoStack()
    cmd = EditStageText("stage:title",
                        _stext("stage:title", y=400.0, font_size=100.0),
                        band=300.0)
    d1 = stack.execute(cmd, stage_doc)
    assert stack.undo_text() == "edit stage text"
    assert stack.undo() == stage_doc
    assert stack.redo() == d1


# -- tempo overlay (Phase 9.2) ------------------------------------------------

TEMPO_EID = "P1:m1:s1:v0:text:0"        # the fixture's tempo mark


def _overlay_text(content: str = "Swing ♩ = 126",
                  **kw) -> "StageTextElement":
    from scoreanim.core.project import OVERLAY_PREFIX
    return _stext(OVERLAY_PREFIX + TEMPO_EID, y=99.6, font_size=40.5,
                  content=content, **kw)


def test_add_tempo_overlay_hides_and_adds_in_one_apply(stage_doc) -> None:
    from scoreanim.core.project import AddTempoOverlay
    from scoreanim.core.score.identity import ElementId
    text = _overlay_text()
    out = AddTempoOverlay(ElementId(TEMPO_EID), text).apply(stage_doc)
    assert out.layout_overrides[ElementId(TEMPO_EID)].hidden is True
    assert out.stage.texts == stage_doc.stage.texts + (text,)
    assert stage_doc.layout_overrides == {}          # before untouched
    assert len(stage_doc.stage.texts) == 2


def test_add_tempo_overlay_preserves_existing_dx_dy(stage_doc) -> None:
    from dataclasses import replace as rep

    from scoreanim.core.project import AddTempoOverlay, LayoutOverride
    from scoreanim.core.score.identity import ElementId
    eid = ElementId(TEMPO_EID)
    doc = rep(stage_doc,
              layout_overrides={eid: LayoutOverride(dx=3.0, dy=-2.0)})
    out = AddTempoOverlay(eid, _overlay_text()).apply(doc)
    assert out.layout_overrides[eid] == LayoutOverride(dx=3.0, dy=-2.0,
                                                       hidden=True)


def test_add_tempo_overlay_validation(stage_doc) -> None:
    from scoreanim.core.project import AddTempoOverlay
    from scoreanim.core.score.identity import ElementId
    eid = ElementId(TEMPO_EID)
    with pytest.raises(CommandError, match="must be"):
        AddTempoOverlay(eid, _stext("stage:overlay:wrong")).apply(stage_doc)
    with pytest.raises(CommandError, match="blank"):
        AddTempoOverlay(eid, _overlay_text(content=" ")).apply(stage_doc)
    once = AddTempoOverlay(eid, _overlay_text()).apply(stage_doc)
    with pytest.raises(CommandError, match="already overlaid"):
        AddTempoOverlay(eid, _overlay_text()).apply(once)


def test_remove_tempo_overlay_restores_and_drops_empty_entry(stage_doc) -> None:
    from dataclasses import replace as rep

    from scoreanim.core.project import (AddTempoOverlay, LayoutOverride,
                                        RemoveTempoOverlay)
    from scoreanim.core.score.identity import ElementId
    eid = ElementId(TEMPO_EID)
    overlaid = AddTempoOverlay(eid, _overlay_text()).apply(stage_doc)
    out = RemoveTempoOverlay(eid).apply(overlaid)
    assert out == stage_doc                  # default entry dropped entirely

    with_delta = rep(stage_doc,
                     layout_overrides={eid: LayoutOverride(dx=3.0)})
    overlaid = AddTempoOverlay(eid, _overlay_text()).apply(with_delta)
    out = RemoveTempoOverlay(eid).apply(overlaid)
    assert out.layout_overrides[eid] == LayoutOverride(dx=3.0)   # dx kept

    with pytest.raises(CommandError, match="not overlaid"):
        RemoveTempoOverlay(eid).apply(stage_doc)


def test_tempo_overlay_undo_is_one_step(stage_doc) -> None:
    from scoreanim.core.project import AddTempoOverlay
    from scoreanim.core.score.identity import ElementId
    stack = UndoStack()
    d1 = stack.execute(AddTempoOverlay(ElementId(TEMPO_EID),
                                       _overlay_text()), stage_doc)
    assert stack.undo_text() == "replace text"
    restored = stack.undo()                  # ONE undo restores BOTH halves
    assert restored == stage_doc
    assert restored.layout_overrides == {}
    assert stack.redo() == d1


def test_edit_overlay_text_never_refits_header(stage_doc) -> None:
    from dataclasses import replace as rep

    from scoreanim.core.project import AddTempoOverlay, EditStageText
    from scoreanim.core.score.identity import ElementId
    overlaid = AddTempoOverlay(ElementId(TEMPO_EID),
                               _overlay_text()).apply(stage_doc)
    moved = rep(_overlay_text(), y=5000.0)   # far past any band
    out = EditStageText(moved.element_id, moved, band=300.0).apply(overlaid)
    assert out.stage.texts[:2] == overlaid.stage.texts[:2]   # header intact
    assert out.stage.texts[2].y == 5000.0


# -- part texts (Phase 9.3) ---------------------------------------------------

def test_set_part_text_sets_and_replaces(doc) -> None:
    from scoreanim.core.project import PartTextOverride, SetPartText
    order = tuple(PartId(f"P{i}") for i in range(1, 8))
    out = SetPartText(PartId("P4"), "Trombones", "Trb.", order).apply(doc)
    assert out.text_overrides == {
        PartId("P4"): PartTextOverride(name="Trombones",
                                       abbreviation="Trb.")}
    assert doc.text_overrides == {}                    # before untouched
    again = SetPartText(PartId("P4"), "Bones", None, order).apply(out)
    assert again.text_overrides[PartId("P4")] == \
        PartTextOverride(name="Bones", abbreviation=None)


def test_set_part_text_none_none_drops_entry(doc) -> None:
    from scoreanim.core.project import SetPartText
    order = (PartId("P1"), PartId("P2"))
    once = SetPartText(PartId("P1"), "Saxes", None, order).apply(doc)
    cleared = SetPartText(PartId("P1"), None, None, order).apply(once)
    assert cleared.text_overrides == {}                # sparse again
    # clearing an absent entry is a no-op, not an error
    assert SetPartText(PartId("P2"), None, None,
                       order).apply(doc).text_overrides == {}


def test_set_part_text_unknown_part_raises(doc) -> None:
    from scoreanim.core.project import SetPartText
    with pytest.raises(CommandError, match="unknown part"):
        SetPartText(PartId("P99"), "X", None,
                    (PartId("P1"),)).apply(doc)


def test_set_part_text_empty_string_survives(doc) -> None:
    """"" is an explicit blank (suppresses the label), not a clear."""
    from scoreanim.core.project import PartTextOverride, SetPartText
    out = SetPartText(PartId("P1"), "", None, (PartId("P1"),)).apply(doc)
    assert out.text_overrides[PartId("P1")] == \
        PartTextOverride(name="", abbreviation=None)


def test_set_part_text_undo_round_trip(doc) -> None:
    from scoreanim.core.project import SetPartText
    stack = UndoStack()
    d1 = stack.execute(SetPartText(PartId("P4"), "Trombones", "Trb.",
                                   (PartId("P4"),)), doc)
    assert stack.undo_text() == "set part name"
    assert stack.undo() == doc
    assert stack.redo() == d1


# -- staff groups (Phase 8) ---------------------------------------------------

PART_ORDER = tuple(PartId(f"P{i}") for i in range(1, 8))   # the fixture's 7


def _grp(*parts: str, symbol: str = "bracket",
         join: bool = True) -> "StaffGroup":
    from scoreanim.core.project import StaffGroup
    return StaffGroup(parts=tuple(PartId(p) for p in parts),
                      symbol=symbol, join_barlines=join)


def test_add_staff_group(doc) -> None:
    from scoreanim.core.project import AddStaffGroup

    out = AddStaffGroup(_grp("P1", "P2"), PART_ORDER).apply(doc)
    assert out.staff_groups == (_grp("P1", "P2"),)
    assert doc.staff_groups == ()                    # apply is pure


def test_add_staff_group_sorts_by_score_order(doc) -> None:
    from scoreanim.core.project import AddStaffGroup

    d1 = AddStaffGroup(_grp("P4", "P5"), PART_ORDER).apply(doc)
    d2 = AddStaffGroup(_grp("P1", "P2"), PART_ORDER).apply(d1)
    assert d2.staff_groups == (_grp("P1", "P2"), _grp("P4", "P5"))


def test_add_staff_group_validation(doc) -> None:
    from scoreanim.core.project import AddStaffGroup

    with pytest.raises(CommandError, match="no parts"):
        AddStaffGroup(_grp(), PART_ORDER).apply(doc)
    with pytest.raises(CommandError, match="contiguous"):
        AddStaffGroup(_grp("P1", "P3"), PART_ORDER).apply(doc)
    with pytest.raises(CommandError, match="contiguous"):
        AddStaffGroup(_grp("P2", "P1"), PART_ORDER).apply(doc)
    with pytest.raises(CommandError, match="unknown part"):
        AddStaffGroup(_grp("P1", "P99"), PART_ORDER).apply(doc)
    with pytest.raises(CommandError, match="duplicate part"):
        AddStaffGroup(_grp("P1", "P1"), PART_ORDER).apply(doc)
    with pytest.raises(CommandError, match="bad group symbol"):
        AddStaffGroup(_grp("P1", "P2", symbol="curly"), PART_ORDER).apply(doc)


def test_add_staff_group_rejects_overlap(doc) -> None:
    from scoreanim.core.project import AddStaffGroup

    d1 = AddStaffGroup(_grp("P1", "P2"), PART_ORDER).apply(doc)
    with pytest.raises(CommandError, match="already in another"):
        AddStaffGroup(_grp("P2", "P3"), PART_ORDER).apply(d1)


def test_edit_staff_group(doc) -> None:
    from scoreanim.core.project import AddStaffGroup, EditStaffGroup

    d1 = AddStaffGroup(_grp("P1", "P2"), PART_ORDER).apply(doc)
    # overlap with ITSELF is fine — editing symbol/span in place
    d2 = EditStaffGroup(0, _grp("P1", "P2", symbol="brace", join=False),
                        PART_ORDER).apply(d1)
    assert d2.staff_groups == (_grp("P1", "P2", symbol="brace", join=False),)
    with pytest.raises(CommandError, match="no staff group #3"):
        EditStaffGroup(3, _grp("P1", "P2"), PART_ORDER).apply(d1)


def test_edit_staff_group_rejects_overlap_with_others(doc) -> None:
    from scoreanim.core.project import AddStaffGroup, EditStaffGroup

    d1 = AddStaffGroup(_grp("P1", "P2"), PART_ORDER).apply(doc)
    d2 = AddStaffGroup(_grp("P4", "P5"), PART_ORDER).apply(d1)
    with pytest.raises(CommandError, match="already in another"):
        EditStaffGroup(1, _grp("P2", "P3"), PART_ORDER).apply(d2)


def test_remove_staff_group(doc) -> None:
    from scoreanim.core.project import AddStaffGroup, RemoveStaffGroup

    d1 = AddStaffGroup(_grp("P1", "P2"), PART_ORDER).apply(doc)
    assert RemoveStaffGroup(0).apply(d1).staff_groups == ()
    with pytest.raises(CommandError, match="no staff group #1"):
        RemoveStaffGroup(1).apply(d1)


def test_staff_group_undo_round_trip(doc) -> None:
    from scoreanim.core.project import AddStaffGroup

    stack = UndoStack()
    d1 = stack.execute(AddStaffGroup(_grp("P1", "P2"), PART_ORDER), doc)
    assert d1.staff_groups == (_grp("P1", "P2"),)
    assert stack.undo_text() == "add staff group"
    assert stack.undo() == doc
    assert stack.redo() == d1


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


# -- delete / restore elements ------------------------------------------------

HAIRPIN = "P1:m4:s1:v1:hairpin:0"
HAIRPIN_SEG = "P1:m4:s1:v1:hairpin:0:seg1"
DYNAMIC = "P2:m9:s1:v1:dynamic:0"


def _hide(*eids: str, hidden: bool = True):
    from scoreanim.core.project import SetElementsHidden
    from scoreanim.core.score.identity import ElementId
    return SetElementsHidden(tuple(ElementId(e) for e in eids), hidden)


def test_delete_hides_and_leaves_the_before_doc_alone(doc) -> None:
    from scoreanim.core.score.identity import ElementId
    out = _hide(HAIRPIN).apply(doc)
    assert out.layout_overrides[ElementId(HAIRPIN)].hidden is True
    assert doc.layout_overrides == {}                     # before untouched


def test_a_broken_spanner_hides_as_one_family(doc) -> None:
    """One gesture, one command, one undo entry (rule 8) — hiding half a
    hairpin is never what anybody meant."""
    from scoreanim.core.score.identity import ElementId
    stack = UndoStack()
    out = stack.execute(_hide(HAIRPIN, HAIRPIN_SEG), doc)
    assert all(out.layout_overrides[ElementId(e)].hidden
               for e in (HAIRPIN, HAIRPIN_SEG))
    assert stack.undo_text() == "delete element"
    assert stack.undo() == doc                            # ONE entry


def test_restore_drops_the_entry_when_nothing_else_is_set(doc) -> None:
    deleted = _hide(HAIRPIN).apply(doc)
    back = _hide(HAIRPIN, hidden=False).apply(deleted)
    assert back.layout_overrides == {}                    # sparse doc
    assert back == doc


def test_a_nudge_survives_a_delete_and_a_restore(doc) -> None:
    from dataclasses import replace as rep

    from scoreanim.core.project import LayoutOverride
    from scoreanim.core.score.identity import ElementId
    eid = ElementId(DYNAMIC)
    nudged = rep(doc, layout_overrides={eid: LayoutOverride(dx=4.0, dy=-2.0)})
    deleted = _hide(DYNAMIC).apply(nudged)
    assert deleted.layout_overrides[eid] == LayoutOverride(dx=4.0, dy=-2.0,
                                                           hidden=True)
    back = _hide(DYNAMIC, hidden=False).apply(deleted)
    assert back.layout_overrides[eid] == LayoutOverride(dx=4.0, dy=-2.0)


def test_delete_of_nothing_is_refused(doc) -> None:
    with pytest.raises(CommandError, match="no elements"):
        _hide().apply(doc)


def test_describe_says_what_it_wrote(doc) -> None:
    assert _hide(HAIRPIN).describe() == "delete element"
    assert _hide(HAIRPIN, HAIRPIN_SEG).describe() == "delete element"
    # one broken spanner is one object, however many ids it takes
    assert _hide(HAIRPIN, HAIRPIN_SEG,
                 hidden=False).describe() == "restore element"
    assert _hide(HAIRPIN, DYNAMIC,
                 hidden=False).describe() == "restore elements"


def test_restore_all_is_one_undo_entry(doc) -> None:
    stack = UndoStack()
    deleted = stack.execute(_hide(HAIRPIN, HAIRPIN_SEG), doc)
    deleted = stack.execute(_hide(DYNAMIC), deleted)
    back = stack.execute(_hide(HAIRPIN, HAIRPIN_SEG, DYNAMIC, hidden=False),
                         deleted)
    assert back.layout_overrides == {}
    assert stack.undo_text() == "restore elements"
    assert stack.undo() == deleted
