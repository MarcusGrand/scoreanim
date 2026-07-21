"""Cross-system stray-path re-homing (2026-07-21).

Under hide-empty-staves (the new-document default) Verovio's optimize
round-trip reuses one xml:id across element types and emits a LATER
system's tie/slur curve as a bare <path> INSIDE an EARLIER note's
<g class="stem|flag"> group whose id collides. The adapter used to
absorb that path into the stem element, which is attributed to the early
note's system/onset — so at the stem's reveal time the curve painted
down in the later system (a solid-black "tie" appearing many bars ahead
of the playhead once the ghost floor is 0).

The adapter now re-homes any path whose geometry lands in a different
system than its element (verovio_adapter._rehome_stray_paths): the ink
becomes its own element attributed by geometry to the system it occupies,
so it animates in place and never leaks. These tests pin both the core
invariant (no element's ink crosses a system band) and the observable
effect through the live applier (later-system ink stays dark-free at an
earlier-system cursor).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import (RevealMode,  # noqa: E402
                                      build_reveal_tracks,
                                      build_trigger_schedule)
from scoreanim.core.animation.reveal import REVEALED_KINDS  # noqa: E402
from scoreanim.core.animation.schedule import STATIC_KINDS  # noqa: E402
from scoreanim.core.animation.style import StyleRules  # noqa: E402
from scoreanim.core.engraving.svg_geom import path_bbox  # noqa: E402
from scoreanim.core.engraving.systems import system_bands  # noqa: E402
from scoreanim.core.score.identity import ElementKind  # noqa: E402
from scoreanim.core.score.join import join_notes  # noqa: E402
from scoreanim.core.score.model import build_score_model  # noqa: E402
from scoreanim.core.timing import TempoEvent, TempoMap  # noqa: E402
from scoreanim.render.animate import AnimationApplier  # noqa: E402
from scoreanim.render.scene import ScoreScenes  # noqa: E402

from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)

# never-animated page furniture the applier leaves fully painted
_ALWAYS_PAINTED = STATIC_KINDS | {ElementKind.TEXT}


def _system_partition(layout):
    """page -> ascending [(system, upper_y_bound)] splitting the page into
    per-system vertical strips at inter-system gap midpoints."""
    bands = {}
    for b in system_bands(layout):
        bands.setdefault(b.page, []).append((b.system, b.rect.y,
                                             b.rect.y + b.rect.h))
    part = {}
    for page, rows in bands.items():
        rows.sort(key=lambda t: t[1])
        cuts = []
        for i, (sysn, _lo, hi) in enumerate(rows):
            upper = (float("inf") if i == len(rows) - 1
                     else (hi + rows[i + 1][1]) / 2.0)
            cuts.append((sysn, upper))
        part[page] = cuts
    return part


def _system_at(part, page, y):
    for sysn, upper in part.get(page, ()):
        if y < upper:
            return sysn
    return None


def test_no_element_ink_crosses_a_system_band(engraved_bigband_hidden):
    """Every path of every system-attributed element sits within that
    element's own system strip — the invariant the reveal edge (keyed by
    system) depends on. Before the fix, tie curves nested in earlier
    stems violated it."""
    layout = engraved_bigband_hidden.layout
    part = _system_partition(layout)
    offenders = []
    for el in layout.elements:
        if el.system is None:
            continue
        for prim in el.glyph.paths:
            box = prim.transform.apply_rect(path_bbox(prim.d))
            sysn = _system_at(part, el.page, box.center.y)
            if sysn is not None and sysn != el.system:
                offenders.append((str(el.identity.element_id),
                                  el.system, sysn))
    assert offenders == [], f"paths crossing systems: {offenders[:5]}"


def test_stray_tie_curves_are_rehomed_as_reveal_ink(engraved_bigband_hidden):
    """The bigband1 tie/slur curves Verovio nested in earlier stems are
    re-emitted in the later system they occupy, as a REVEAL kind (TIE) —
    so they grow in with the playhead sweep at their own x rather than
    popping at the system downbeat (the cursor-in-m26 regression). Each
    resolves a part, so it rides that part's (system, part) reveal edge."""
    layout = engraved_bigband_hidden.layout
    warned = [w for w in engraved_bigband_hidden.warnings
              if w.code == "stray-path"]
    assert warned, "expected stray-path warnings on the bigband fixture"
    rehomed = [e for e in layout.elements
               if e.identity.kind is ElementKind.TIE
               and ":v0:tie:" in str(e.identity.element_id)
               and e.identity.onset is None]   # onset-less: edge-driven
    # the tie curves sit in later systems (8/9) with a resolved part so a
    # (system, part) reveal curve exists to clip them
    rehomed = [e for e in rehomed if e.system is not None and e.system >= 8
               and e.identity.part is not None]
    assert rehomed, "no re-homed reveal-ink ties found"


def test_later_system_ink_stays_hidden_at_earlier_cursor(
        engraved_bigband_hidden):
    """Live-path guard: build ScoreScenes + AnimationApplier at floor 0
    (ghosts invisible, so any leak is solid ink), seek to a cursor inside
    an early system, and assert no ink PHYSICALLY in a later system
    paints — the exact symptom (m26 ties black at the m21 cursor).

    Detection is by the item's rendered geometry, not its `system`
    attribute: the pre-fix bug was precisely that the leaking stem CLAIMS
    the cursor's own system while its ink is drawn a page down, so an
    attribute-based filter would miss it (and did)."""
    QApplication.instance() or QApplication([])
    eng = engraved_bigband_hidden
    stage = default_stage_config(eng.prepared, page_content_top(eng.layout))
    scenes = ScoreScenes(eng.layout, stage, ghost_opacity=0.0)
    model = build_score_model(eng.prepared)
    report = join_notes(model, eng.note_records)
    schedule = build_trigger_schedule(eng.layout, report.mapping,
                                      model.measures)
    score_end = max(m.start + m.quarter_length for m in model.measures)
    tracks = build_reveal_tracks(eng.layout, schedule, score_end)
    tempo = TempoMap([TempoEvent(0.0, 60.0)])   # seconds == beats
    style = StyleRules(floor_opacity=0.0)
    applier = AnimationApplier(scenes.items, schedule, tempo, style, tracks)

    # a cursor early in the piece; m21 in bigband1 is beat 80 (== seconds)
    applier.refresh(80.0)
    cursor_system = applier.current_system()
    assert cursor_system is not None

    # page -> [(system, band_rect)] for later systems, keyed by scene
    later_bands = {}
    for b in system_bands(eng.layout):
        if b.system > cursor_system:
            later_bands.setdefault(b.page, []).append(b.rect)
    page_of_item = {}
    for page_idx, scene in enumerate(scenes.scenes, start=1):
        for gi in scene.items():
            page_of_item[id(gi)] = page_idx

    def paints_in_later_system(item):
        if item.identity.kind in _ALWAYS_PAINTED:
            return False
        if item.identity.kind in REVEALED_KINDS and item.reveal_children:
            if all(c.hidden for c in item.reveal_children):
                return False
        elif not (item.isVisible()
                  and item.opacity() > style.floor_opacity + 1e-6):
            return False
        rects = later_bands.get(page_of_item.get(id(item)), ())
        r = item.sceneBoundingRect()
        return any(r.top() <= band.y + band.h and r.bottom() >= band.y
                   for band in rects)

    leaks = [it for it in scenes.items.values()
             if it.identity is not None and paints_in_later_system(it)]
    assert leaks == [], (
        "ink painting inside a later system at an earlier cursor: "
        + ", ".join(f"{it.identity.kind.name}(sys_attr={it.system},"
                    f"onset={it.identity.onset})" for it in leaks[:8]))
