"""Never-clip repagination (Phase 10R, rule-7 amendment): when the
encoded page breaks cannot hold their systems, the adapter keeps the
encoded SYSTEM breaks, discards the encoded page breaks, and re-derives
page breaks from measured band heights — one extra engrave, flagged,
deterministic, never stored (rule 5). The video fixture's FLAT load is
the live case: Dorico's breaks assume hidden staves."""

from scoreanim.core.engraving.systems import SystemBand, plan_page_breaks
from scoreanim.core.engraving.types import Rect


def _band(system: int, page: int, y: float, h: float) -> SystemBand:
    return SystemBand(system=system, page=page, rect=Rect(0, y, 1000, h))


def test_planner_packs_greedily_with_measured_margins():
    # page 1 holds two systems (top 50, gap 30); page height 1000
    bands = (_band(1, 1, 50, 300), _band(2, 1, 630, 300),
             _band(3, 2, 50, 900), _band(4, 2, 1000, 900))  # overflows
    breaks = plan_page_breaks(bands, 1000.0, {1: 1, 2: 5, 3: 9, 4: 13})
    # 50+300+250(gap: 630-350=280 median)+300 = fits; sys3 900 doesn't
    # fit after sys2 → break at m9; sys4 doesn't fit after sys3 → m13
    assert breaks == (9, 13)


def test_planner_no_breaks_when_everything_fits():
    bands = (_band(1, 1, 50, 300), _band(2, 1, 400, 300))
    assert plan_page_breaks(bands, 1000.0, {1: 1, 2: 5}) == ()


def test_planner_oversized_single_system_never_loops():
    # a system taller than the page still gets placed (alone)
    bands = (_band(1, 1, 50, 300), _band(2, 1, 400, 2000))
    assert plan_page_breaks(bands, 1000.0, {1: 1, 2: 5}) == (5,)


def test_planner_empty():
    assert plan_page_breaks((), 1000.0, {}) == ()


def test_video_flat_repaginates_cleanly(engraved_video,
                                        engraved_video_hidden):
    from scoreanim.core.engraving.systems import system_bands

    page_h = engraved_video.layout.pages[0].height
    assert len(engraved_video.layout.pages) == 15    # one system per page
    for band in system_bands(engraved_video.layout):
        assert band.rect.y + band.rect.h <= page_h
    assert [w.code for w in engraved_video.warnings].count(
        "repaginated") == 1
    assert not [w for w in engraved_video.warnings
                if w.code == "system-overflow"]
    # musical content identical across pagination AND hiding
    assert engraved_video.note_records == engraved_video_hidden.note_records


def test_prior_fixtures_never_repaginate(engraved, engraved_spanners):
    for es in (engraved, engraved_spanners):
        assert not [w for w in es.warnings if w.code == "repaginated"]
