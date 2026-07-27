"""M2 exit criteria, pinned (M2.7), re-run against the tint (M2.8),
offscreen.

The roadmap's exit, as a test: on testscore AND complex3, clicking a
notehead, a slur, a hairpin, a barline and a part label each selects
that element, highlights it, and reports the right identity — and
playback keeps running with a live selection.

Clicks land where a user would aim: the interior of a solid glyph, a
point on the stroke for thin or hollow ink (a slur's bbox CENTRE is the
air under its arc — see spikes/hit_census.py finding C).

Two changes at M2.8, both because the highlight became a tint on the
element's own ink rather than a sibling outline item:

  - "highlights it" now means the element itself is lit, so the checks
    read the item's own state instead of a separate overlay's scene.
  - "playback continues undisturbed" INVERTS on the selected element:
    the tint deliberately changes it. The criterion sharpens into
    "undisturbed everywhere else, and different in exactly the two
    declared channels here" — and gains the non-vacuity guard the M2.7
    version turned out to need (see _late_notehead).

One criterion is added, at the same level as the five kinds: clicking
empty staff space deselects (ruling 2026-07-27).
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

# The five the roadmap names. A part label is engraved TEXT (identity-
# bearing, minted onset-less), so it selects and reports "—" for onset.
EXIT_KINDS = (ElementKind.NOTEHEAD, ElementKind.SLUR, ElementKind.HAIRPIN,
              ElementKind.BARLINE, ElementKind.TEXT)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _built(qapp, engraved):
    scenes = ScoreScenes(engraved.layout, StageConfig())
    state = AppState()
    controller = SelectionController(state)
    controller.bind_scenes(scenes)
    return scenes, state, controller


def _aim(item) -> QPointF:
    """Where a user would click: the interior of a solid glyph, else a
    point on the stroke."""
    centre = item.bbox.center()
    for child in item.childItems():
        if not child.isVisible() or not hasattr(child, "shape"):
            continue
        if child.shape().contains(child.mapFromScene(centre)):
            return centre
    best = None
    for child in item.childItems():
        if not hasattr(child, "path") or child.path().isEmpty():
            continue
        length = child.path().length()
        if best is None or length > best[0]:
            best = (length, child)
    if best is None:
        return centre
    return best[1].mapToScene(best[1].path().pointAtPercent(0.5))


def _exit_run(qapp, engraved, label: str) -> None:
    scenes, state, controller = _built(qapp, engraved)
    layout = engraved.layout
    checked = 0
    for kind in EXIT_KINDS:
        element = next((el for el in layout.elements
                        if el.identity.kind is kind), None)
        if element is None:
            continue                      # not every fixture has each kind
        item = scenes.items[element.identity.element_id]
        # the view is showing the page the element is on — that is what
        # "clicking it" means; the scene travels with the position
        controller.select_at(_aim(item), item.scene())
        selected = state.selected
        assert selected is not None, f"{label}: {kind.name} selected nothing"
        assert selected.element_id == element.identity.element_id, (
            f"{label}: clicking {kind.name} selected "
            f"{selected.kind.name} {selected.element_id}")
        assert selected.kind is kind
        # highlighted: the element itself carries the tint
        assert controller.highlighted is item
        assert item.selected is True
        checked += 1
    assert checked >= 4, f"{label}: only {checked} of the exit kinds present"


def test_exit_criteria_on_testscore(qapp, engraved) -> None:
    _exit_run(qapp, engraved, "testscore")


def test_exit_criteria_on_complex3(qapp, engraved_complex3_hidden) -> None:
    _exit_run(qapp, engraved_complex3_hidden, "complex3")


def test_part_label_selects_and_reports_no_onset(qapp, engraved) -> None:
    """A part label is page furniture: identity-bearing TEXT, minted
    onset-less, and its id carries no measure."""
    from scoreanim.core.selection import measure_ordinal_of

    scenes, state, controller = _built(qapp, engraved)
    label = next(el for el in engraved.layout.elements
                 if el.identity.kind is ElementKind.TEXT
                 and el.identity.onset is None)
    item = scenes.items[label.identity.element_id]
    controller.select_at(_aim(item), item.scene())
    assert state.selected is not None
    assert state.selected.element_id == label.identity.element_id
    assert state.selected.onset is None
    assert measure_ordinal_of(state.selected.element_id) is None


def _late_notehead(engraved):
    """A notehead whose trigger is NOT at t=0.

    The M2.7 version of the test below picked layout.elements' FIRST
    notehead, which triggers on the downbeat — so it sat at opacity 1.0
    at every sampled t and the comparison held whatever selection did to
    it. That vacuity is exactly what the M2.8 rework has to remove, so
    the element is chosen for a trigger the samples actually straddle.
    """
    notes = [el for el in engraved.layout.elements
             if el.identity.kind is ElementKind.NOTEHEAD
             and el.identity.onset]
    assert notes, "fixture has no notehead with a nonzero onset"
    return min(notes, key=lambda el: el.identity.onset)


def test_playback_is_undisturbed_by_a_live_selection(
        qapp, engraved, schedule_for_exit) -> None:
    """The exit criterion, re-pinned for the tint (M2.8).

    Under M2.4 the highlight was a sibling item, so "undisturbed" meant
    EVERY element's state was identical with and without a selection.
    The tint deliberately changes the selected element, so the criterion
    inverts into a sharper one: playback is undisturbed everywhere else,
    and on the selected element it differs in exactly the two declared
    channels — color and an opacity floor — with scale untouched."""
    from scoreanim.core.animation import StyleRules
    from scoreanim.core.selection.highlight import SELECTION_MIN_OPACITY
    from scoreanim.core.timing import TempoEvent, TempoMap
    from scoreanim.render.animate import AnimationApplier

    note = _late_notehead(engraved)
    eid = note.identity.element_id
    samples = (0.0, 0.5, 1.0, 2.0, 4.0)

    def run(select: bool):
        scenes, state, controller = _built(qapp, engraved)
        applier = AnimationApplier(scenes.items, schedule_for_exit,
                                   TempoMap([TempoEvent(0.0, 120.0)]),
                                   StyleRules(), ())
        if select:
            item = scenes.items[eid]
            controller.select_at(_aim(item), item.scene())
            assert state.selected is not None
            assert state.selected.element_id == eid
        out = []
        for t in samples:
            applier.apply_at(t)
            out.append({e: (i.opacity(), i.scale(),
                            i._tracked[0][0].brush().color().name()
                            if i._tracked else None)
                        for e, i in scenes.items.items()})
        return scenes, out

    live_scenes, lit = run(select=True)       # scenes retained: dropping
    _clean_scenes, clean = run(select=False)  # them deletes the C++ items

    for t, (a, b) in zip(samples, zip(lit, clean)):
        # everything else: byte-identical, playback genuinely undisturbed
        assert {k: v for k, v in a.items() if k != eid} == \
               {k: v for k, v in b.items() if k != eid}, f"at t={t}"

        sel_op, sel_scale, sel_color = a[eid]
        raw_op, raw_scale, raw_color = b[eid]
        assert sel_scale == raw_scale, f"scale disturbed at t={t}"
        assert sel_op == pytest.approx(
            max(raw_op, SELECTION_MIN_OPACITY)), f"at t={t}"
        assert sel_color != raw_color, f"tint missing at t={t}"

    # non-vacuity: the samples really do straddle the trigger, so the
    # floor was doing something at least once
    raw = [c[eid][0] for c in clean]
    assert min(raw) < SELECTION_MIN_OPACITY < max(raw), \
        f"vacuous: unselected opacity never below the floor ({raw})"


def test_empty_staff_space_deselects_on_both_fixtures(
        qapp, engraved, engraved_complex3_hidden) -> None:
    """M2.8's added exit behaviour, at the same level as the five kinds
    above: after selecting an object, a click on empty staff space
    clears rather than selecting the staff (see tests/
    test_backdrop_deselect.py for the census behind the ruling)."""
    for label, source in (("testscore", engraved),
                          ("complex3", engraved_complex3_hidden)):
        scenes, state, controller = _built(qapp, source)
        note = next(el for el in source.layout.elements
                    if el.identity.kind is ElementKind.NOTEHEAD)
        item = scenes.items[note.identity.element_id]
        controller.select_at(_aim(item), item.scene())
        assert state.selected is not None, label

        empty, scene = _empty_staff_point(source, scenes, controller)
        assert empty is not None, f"{label}: no empty staff point found"
        controller.select_at(empty, scene)
        assert state.selected is None, f"{label}: staff space selected it"
        assert controller.highlighted is None, label


def _empty_staff_point(source, scenes, controller):
    """A point INSIDE a staff whose only ink is the staff itself — i.e.
    what a user sees as empty staff space. Found by probing rather than
    assumed: a staff's bbox centre often lands on a real notehead, which
    is a legitimate selection and not what this is testing."""
    from scoreanim.core.selection import BACKDROP_KINDS

    for staff in (el for el in source.layout.elements
                  if el.identity.kind is ElementKind.STAFF_LINES):
        item = scenes.items[staff.identity.element_id]
        bb = staff.bbox
        for fx in (0.3, 0.45, 0.6, 0.75, 0.9):
            for fy in (0.2, 0.4, 0.6, 0.8):
                point = QPointF(bb.x + bb.w * fx, bb.y + bb.h * fy)
                cands = controller.candidates_at(point, item.scene())
                kinds = {c.kind for c in cands}
                if kinds and kinds <= BACKDROP_KINDS:
                    return point, item.scene()
    return None, None


@pytest.fixture(scope="module")
def schedule_for_exit(engraved, join_mapping, score_model):
    from scoreanim.core.animation import build_trigger_schedule
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures)
