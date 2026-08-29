"""The constant systems-mode frame (2026-08-30, docs/SYSTEMS_MODE_REWORK.md
stage 1) — pure, no Qt.

Systems mode is a fixed piece of glass the systems are placed into. That
frame is computed once per load from the bands, and everything the stage
does with it rests on these two properties: it is the SAME frame for
every system, and every band is centred inside it.
"""
from __future__ import annotations

import pytest

from scoreanim.core.engraving.systems import (SYSTEM_FRAME_PAD,
                                              SystemBand, SystemsFrame,
                                              neighbour_bounds,
                                              system_bands, systems_frame)
from scoreanim.core.engraving.types import Rect


def _band(system: int, y: float, h: float, w: float = 1000.0,
          page: int = 1) -> SystemBand:
    return SystemBand(system=system, page=page, rect=Rect(0.0, y, w, h))


def test_frame_is_page_width_by_tallest_band_plus_even_padding() -> None:
    frame = systems_frame((_band(1, 0.0, 400.0), _band(2, 500.0, 600.0)))
    assert frame.width == 1000.0                      # the page's width
    assert frame.height == pytest.approx(600.0 * (1.0 + 2.0 * 0.06))
    # the padding really is even: the tallest band gets the same air
    # above and below
    placed = frame.rect_for(Rect(0.0, 500.0, 1000.0, 600.0))
    assert placed.y2 - 1100.0 == pytest.approx(500.0 - placed.y)
    assert placed.y2 - 1100.0 == pytest.approx(600.0 * 0.06)


def test_every_band_is_centred_and_fits() -> None:
    """The whole point of one frame: a system with fewer staves gets
    more air, not a smaller frame."""
    bands = (_band(1, 0.0, 400.0), _band(2, 500.0, 600.0),
             _band(3, 2000.0, 550.0))
    frame = systems_frame(bands)
    for band in bands:
        placed = frame.rect_for(band.rect)
        assert placed.center.y == pytest.approx(band.rect.center.y)
        assert placed.h == frame.height and placed.w == frame.width
        assert placed.contains(band.rect, slack=1e-9)


def test_the_frame_does_not_depend_on_which_system_is_showing() -> None:
    bands = (_band(1, 0.0, 400.0), _band(2, 500.0, 600.0))
    frame = systems_frame(bands)
    sizes = {(frame.rect_for(b.rect).w, frame.rect_for(b.rect).h)
             for b in bands}
    assert len(sizes) == 1


def test_x_is_the_pages_own_left_edge() -> None:
    """Horizontal position is untouched — systems keep the margins they
    were engraved with, so they stay left-aligned with each other."""
    frame = systems_frame((_band(1, 0.0, 400.0),))
    assert frame.rect_for(Rect(0.0, 0.0, 1000.0, 400.0)).x == 0.0


def test_padding_is_a_fraction_so_it_scales_with_the_page() -> None:
    """A big orchestral page gets proportionally the same air as a
    two-staff one — the reason the padding is not a fixed number of
    page units."""
    small = systems_frame((_band(1, 0.0, 400.0),))
    big = systems_frame((_band(1, 0.0, 4000.0, w=10000.0),))
    assert (big.height - 4000.0) / 4000.0 == pytest.approx(
        (small.height - 400.0) / 400.0)
    assert SYSTEM_FRAME_PAD == 0.06          # Marcus's call, 2026-08-30


def test_no_systems_means_no_frame() -> None:
    assert systems_frame(()) is None


def test_on_the_real_fixture(engraved) -> None:
    """testscore: 5 systems whose bands differ by 300 page units."""
    bands = system_bands(engraved.layout)
    frame = systems_frame(bands)
    assert isinstance(frame, SystemsFrame)
    page = engraved.layout.pages[0]
    assert frame.width == pytest.approx(page.width)
    tallest = max(b.rect.h for b in bands)
    assert frame.height == pytest.approx(tallest * 1.12)
    assert frame.height < page.height          # the point of the rework
    for band in bands:
        placed = frame.rect_for(band.rect)
        assert placed.center.y == pytest.approx(band.rect.center.y)
        assert placed.contains(band.rect, slack=1e-9)


# -- how far a system may show -------------------------------------------

def test_a_system_is_bounded_only_by_its_neighbours() -> None:
    """The mask exists to hide the OTHER systems on the page. So a
    system stops at a neighbour's edge, and where there is no neighbour
    it is open — which is what stopped system mode slicing the page's
    title block (Marcus, 2026-08-30)."""
    bounds = neighbour_bounds((_band(1, 40.0, 200.0),
                               _band(2, 300.0, 200.0),
                               _band(3, 600.0, 200.0)))
    assert bounds[1] == (None, 300.0)      # first on the page: open above
    assert bounds[2] == (240.0, 600.0)     # boxed in by both
    assert bounds[3] == (500.0, None)      # last on the page: open below


def test_a_system_alone_on_its_page_is_open_both_ways() -> None:
    bounds = neighbour_bounds((_band(1, 40.0, 200.0),
                               _band(2, 40.0, 200.0, page=2)))
    assert bounds[1] == (None, None)
    assert bounds[2] == (None, None)


def test_neighbours_are_per_page_not_per_index() -> None:
    """Consecutive systems on DIFFERENT pages are not neighbours: the
    page flip already separates them."""
    bounds = neighbour_bounds((_band(1, 40.0, 200.0),
                               _band(2, 300.0, 200.0),
                               _band(3, 40.0, 200.0, page=2)))
    assert bounds[2] == (240.0, None)      # nothing below it on page 1
    assert bounds[3] == (None, None)


def test_bounds_read_the_page_top_to_bottom(engraved) -> None:
    """On the real fixture every band is inside the span it is given,
    and no two systems on a page claim the same paper."""
    bands = system_bands(engraved.layout)
    bounds = neighbour_bounds(bands)
    for band in bands:
        above, below = bounds[band.system]
        assert above is None or above <= band.rect.y
        assert below is None or below >= band.rect.y2
