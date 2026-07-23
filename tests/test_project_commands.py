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
    assert stack.undo_text() == "replace tempo mark"
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
