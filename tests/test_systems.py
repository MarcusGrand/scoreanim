"""System band geometry + current_system (Phase 7.3), headless on the
fixture: 5 systems on pages 1/2/2/3/3, full-width bands, containment,
the schedule's per-trigger system stamp, and centered_fit math."""
from __future__ import annotations

import pytest

from scoreanim.core.animation import StyleRules, build_trigger_schedule
from scoreanim.core.engraving.systems import (SystemBand, centered_fit,
                                              system_bands)
from scoreanim.core.engraving.types import Rect
from scoreanim.core.timing import TempoEvent, TempoMap

TEMPO = TempoMap([TempoEvent(0.0, 120.0)])


@pytest.fixture(scope="module")
def bands(engraved) -> tuple[SystemBand, ...]:
    return system_bands(engraved.layout)


@pytest.fixture(scope="module")
def schedule(engraved, join_mapping, score_model):
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures)


def test_fixture_bands_systems_and_pages(bands, engraved) -> None:
    assert [b.system for b in bands] == [1, 2, 3, 4, 5]
    assert [b.page for b in bands] == [1, 2, 2, 3, 3]
    for band in bands:
        geo = engraved.layout.pages[band.page - 1]
        assert band.rect.x == 0.0
        assert band.rect.w == geo.width


def test_every_element_bbox_inside_its_band(bands, engraved) -> None:
    by_system = {b.system: b for b in bands}
    checked = 0
    for el in engraved.layout.elements:
        if el.system is None:
            continue
        assert by_system[el.system].rect.contains(el.bbox), \
            el.identity.element_id
        checked += 1
    assert checked > 1000                     # the fixture is dense


def test_same_page_bands_in_vertical_order(bands) -> None:
    by_page: dict[int, list[SystemBand]] = {}
    for band in bands:
        by_page.setdefault(band.page, []).append(band)
    for page_bands in by_page.values():
        tops = [b.rect.y for b in page_bands]  # already system-sorted
        assert tops == sorted(tops)


def test_trigger_systems_walk_monotonically(schedule) -> None:
    """The per-trigger system stamp is non-decreasing 1→5 across the
    fixture (min-fresh rule, same as page) and consistent with each
    trigger's page."""
    systems = [t.system for t in schedule.triggers]
    assert systems == sorted(systems)
    assert systems[0] == 1
    assert systems[-1] == 5
    system_page = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3}
    for t in schedule.triggers:
        assert t.page == system_page[t.system]


def test_current_system_steps_through_the_score(engraved, schedule) -> None:
    """current_system() mirrors current_page(): stepping an applier
    through every trigger time visits systems 1..5 in order and matches
    each trigger's stamped system (Qt applier over the pure stamps —
    the exact walk export and live follow share)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from scoreanim.core.project.stage_config import (default_stage_config,
                                                     page_content_top)
    from scoreanim.render.animate import AnimationApplier
    from scoreanim.render.scene import ScoreScenes

    QApplication.instance() or QApplication([])
    scenes = ScoreScenes(engraved.layout, default_stage_config(
        engraved.prepared, page_content_top(engraved.layout)))
    applier = AnimationApplier(scenes.items, schedule, TEMPO, StyleRules())
    assert applier.current_system() == 1
    seen = [1]
    for trig in schedule.triggers:
        applier.apply_at(TEMPO.seconds_at(trig.beats))
        assert applier.current_system() == trig.system
        if trig.system != seen[-1]:
            seen.append(trig.system)
    assert seen == [1, 2, 3, 4, 5]
    applier.apply_at(-1.0)
    assert applier.current_system() == 1


def test_centered_fit_geometry() -> None:
    # wide band into a taller canvas: width-limited, vertical letterbox
    fit = centered_fit(200.0, 50.0, 100.0, 100.0)
    assert fit == Rect(0.0, 37.5, 100.0, 25.0)
    # tall content into a wide canvas: height-limited, side letterbox
    fit = centered_fit(50.0, 100.0, 200.0, 100.0)
    assert fit == Rect(75.0, 0.0, 50.0, 100.0)
    # exact aspect: fills the canvas
    assert centered_fit(20.0, 10.0, 200.0, 100.0) == Rect(0, 0, 200.0, 100.0)
    with pytest.raises(ValueError):
        centered_fit(0.0, 10.0, 100.0, 100.0)
