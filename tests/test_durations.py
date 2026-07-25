"""M4.2: the duration-resolution seam (core/animation/durations.py).

Synthetic layouts pin the policy — noteheads keep their own engraved
entry, attachments inherit their rule-3 group's longest member, rests
and sigs and measure-attached objects are omitted, synthesized
slash/bar-repeat ink splits its measure span — and the real fixture
checks the same policy end to end.
"""
from __future__ import annotations

from scoreanim.core.animation import resolve_durations
from scoreanim.core.engraving.types import (Layout, PageGeometry, Point,
                                            Rect, RenderedElement,
                                            RenderPrimitive)
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)
from scoreanim.core.score.model import MeasureInfo, ScoreNote


def _el(eid: str, kind: ElementKind, onset: float | None,
        voice: int | None = 1) -> RenderedElement:
    ident = ElementIdentity(ElementId(eid), kind, PartId("P1"), "Part",
                            1, voice, onset)
    return RenderedElement(ident, 1, 0.0, 0.0, Rect(0, 0, 1, 1),
                           Point(0, 0), RenderPrimitive(paths=()))


def _note(onset: float, step: str, order: int) -> ScoreNote:
    return ScoreNote(part=PartId("P1"), measure=1, staff=1,
                     voice_label=None, onset=onset, grace=False,
                     pitch_step=step, pitch_alter=0.0, octave=4,
                     staff_loc=None, order=order)


_MEASURES = (MeasureInfo(number=1, start=0.0, quarter_length=4.0),
             MeasureInfo(number=2, start=4.0, quarter_length=3.0))


def _synthetic():
    layout = Layout(
        pages=(PageGeometry(1, 100.0, 100.0),),
        elements=(
            _el("c0", ElementKind.NOTEHEAD, 0.0),      # quarter
            _el("e0", ElementKind.NOTEHEAD, 0.0),      # half — the longest
            _el("s0", ElementKind.STEM, 0.0),          # shared chord stem
            _el("a0", ElementKind.ACCIDENTAL, 0.0),
            _el("r0", ElementKind.REST, 2.0),          # F6: omitted
            _el("k0", ElementKind.KEY_SIG, 0.0),       # sig kind: omitted
            _el("d0", ElementKind.DYNAMIC, 0.0, voice=None),  # group miss
            _el("t0", ElementKind.TEXT, None),         # onset-less: omitted
            _el("P1:m1:slash:0", ElementKind.SLASH, 0.0, voice=None),
            _el("P1:m1:slash:1", ElementKind.SLASH, 1.0, voice=None),
            _el("P1:m1:slash:2", ElementKind.SLASH, 2.0, voice=None),
            _el("P1:m1:slash:3", ElementKind.SLASH, 3.0, voice=None),
            _el("P1:m2:barrepeat", ElementKind.BAR_REPEAT, 4.0, voice=None),
        ))
    mapping = {ElementId("c0"): _note(0.0, "C", 0),
               ElementId("e0"): _note(0.0, "E", 1)}
    note_durations = {ElementId("c0"): 1.0, ElementId("e0"): 2.0,
                      ElementId("r0"): 2.0}
    return resolve_durations(layout, mapping, note_durations, _MEASURES)


def test_notehead_keeps_its_own_entry() -> None:
    durs = _synthetic()
    assert durs[ElementId("c0")] == 1.0
    assert durs[ElementId("e0")] == 2.0


def test_attachment_inherits_the_groups_longest_member() -> None:
    durs = _synthetic()
    assert durs[ElementId("s0")] == 2.0    # chord stem: max(1.0, 2.0)
    assert durs[ElementId("a0")] == 2.0


def test_rest_sig_and_measure_attached_are_omitted() -> None:
    durs = _synthetic()
    assert ElementId("r0") not in durs     # retrospective trigger (F6)
    assert ElementId("k0") not in durs     # bar-level sig glyph
    assert ElementId("d0") not in durs     # voice None: rule-3 group miss
    assert ElementId("t0") not in durs     # onset-less


def test_slash_splits_and_bar_repeat_takes_its_measure_span() -> None:
    durs = _synthetic()
    for k in range(4):
        assert durs[ElementId(f"P1:m1:slash:{k}")] == 1.0   # 4.0 span ÷ 4
    assert durs[ElementId("P1:m2:barrepeat")] == 3.0        # own (short) bar


def test_no_measures_means_no_synthesized_entries() -> None:
    layout = Layout(
        pages=(PageGeometry(1, 100.0, 100.0),),
        elements=(_el("P1:m1:slash:0", ElementKind.SLASH, 0.0, voice=None),))
    assert resolve_durations(layout, {}, {}) == {}


def test_schedule_carries_the_map_and_defaults_empty() -> None:
    from scoreanim.core.animation import build_trigger_schedule
    layout = Layout(pages=(PageGeometry(1, 100.0, 100.0),),
                    elements=(_el("c0", ElementKind.NOTEHEAD, 0.0),))
    mapping = {ElementId("c0"): _note(0.0, "C", 0)}
    bare = build_trigger_schedule(layout, mapping)
    assert bare.duration_by_element == {}
    carried = build_trigger_schedule(
        layout, mapping, (), {ElementId("c0"): 1.0})
    assert carried.duration_by_element == {ElementId("c0"): 1.0}
    assert carried.beats_by_element == bare.beats_by_element


def test_real_fixture_policy(engraved, join_mapping, score_model) -> None:
    durs = resolve_durations(engraved.layout, join_mapping,
                             engraved.note_durations, score_model.measures)
    # every mapped notehead keeps its own engraved entry
    for eid in join_mapping:
        assert durs[eid] == engraved.note_durations[eid]
    idents = [el.identity for el in engraved.layout.elements]
    # rests never stretch
    for ident in idents:
        if ident.kind in (ElementKind.REST, ElementKind.MREST):
            assert ident.element_id not in durs
    # every slash got its even split of an engraved bar
    slashes = [i for i in idents if i.kind is ElementKind.SLASH]
    assert len(slashes) == 52
    assert all(durs[i.element_id] > 0 for i in slashes)
    # stems resolved through their notehead group: each carries the max
    # engraved duration among the noteheads sharing its rule-3 key
    from scoreanim.core.animation import quantize_beats
    ident_by_id = {i.element_id: i for i in idents}
    group_max: dict[tuple, float] = {}
    for eid in join_mapping:
        ident = ident_by_id[eid]
        key = (ident.part, ident.staff, ident.voice,
               quantize_beats(ident.onset))
        group_max[key] = max(group_max.get(key, 0.0),
                             engraved.note_durations[eid])
    stems = [i for i in idents if i.kind is ElementKind.STEM
             and i.element_id in durs]
    assert stems
    for ident in stems:
        key = (ident.part, ident.staff, ident.voice,
               quantize_beats(ident.onset))
        assert durs[ident.element_id] == group_max[key]
