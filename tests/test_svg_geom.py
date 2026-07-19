"""svg_geom unit tests against hand-computed geometry."""

import pytest

from scoreanim.core.engraving.svg_geom import (ClosePath, CubicTo, LineTo,
                                               MoveTo, QuadTo, ellipse_path,
                                               parse_transform, path_bbox,
                                               path_segments, polygon_path,
                                               rect_path)


def test_parse_translate_then_scale_applies_right_to_left() -> None:
    m = parse_transform("translate(10, 20) scale(2)")
    # point is scaled first, then translated
    assert m.apply(3, 4) == (16, 28)


def test_parse_scale_single_arg_is_uniform() -> None:
    m = parse_transform("scale(0.54)")
    assert m.apply(100, 100) == (54, 54)


def test_parse_rotate_about_origin() -> None:
    # rotate(-90) maps (x, y) -> (y, -x): the +x axis swings to +y
    # (Phase 11 — Verovio's vertical text)
    m = parse_transform("rotate(-90)")
    x, y = m.apply(10, 0)
    assert (round(x, 6), round(y, 6)) == (0.0, -10.0)


def test_parse_rotate_about_point() -> None:
    # rotate(-90 5 5) leaves the pivot (5, 5) fixed
    m = parse_transform("rotate(-90 5 5)")
    x, y = m.apply(5, 5)
    assert (round(x, 6), round(y, 6)) == (5.0, 5.0)


def test_parse_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_transform("not a transform")


def test_path_bbox_line_and_close() -> None:
    r = path_bbox("M0 0 L10 5 L10 -5 Z")
    assert (r.x, r.y, r.w, r.h) == (0, -5, 10, 10)


def test_path_bbox_cubic_extremum_beats_endpoints() -> None:
    # symmetric cubic arch peaking at t=0.5, y = -7.5
    r = path_bbox("M0 0 C0 -10 10 -10 10 0")
    assert (r.x, r.y, r.w, r.h) == pytest.approx((0, -7.5, 10, 7.5))


def test_path_bbox_control_points_do_not_inflate_bbox() -> None:
    # control points at x=-100/110 pull the curve, but extrema stay inside
    r = path_bbox("M0 0 C-100 0 110 10 10 10")
    assert r.x > -100 and r.x2 < 110
    assert r.y == 0 and r.y2 == 10


def test_path_bbox_relative_and_hv() -> None:
    r = path_bbox("m5 5 l10 0 v10 h-10 z")
    assert (r.x, r.y, r.w, r.h) == (5, 5, 10, 10)


def test_path_bbox_quadratic() -> None:
    # quad peak at t=0.5: y = 0.5*0 + ... = -5
    r = path_bbox("M0 0 Q5 -10 10 0")
    assert (r.x, r.y, r.w, r.h) == pytest.approx((0, -5, 10, 5))


def test_path_bbox_implicit_lineto_after_moveto() -> None:
    r = path_bbox("M0 0 10 10 20 0")
    assert (r.x, r.y, r.w, r.h) == (0, 0, 20, 10)


def test_path_bbox_rejects_arcs() -> None:
    with pytest.raises(ValueError):
        path_bbox("M0 0 A5 5 0 0 1 10 10")


def test_ellipse_path_bbox_is_tight() -> None:
    r = path_bbox(ellipse_path(50, 60, 10, 5))
    assert (r.x, r.y, r.w, r.h) == pytest.approx((40, 55, 20, 10), abs=1e-6)


def test_polygon_and_rect_paths() -> None:
    r = path_bbox(polygon_path("0,0 10,2 10,8 0,6"))
    assert (r.x, r.y, r.w, r.h) == (0, 0, 10, 8)
    r2 = path_bbox(rect_path(1, 2, 3, 4))
    assert (r2.x, r2.y, r2.w, r2.h) == (1, 2, 3, 4)


# --- path_segments: the parser consumed by both path_bbox and render/ -------


def test_segments_absolute_basic() -> None:
    assert path_segments("M0 0 L10 5 Z") == (
        MoveTo(0, 0), LineTo(10, 5), ClosePath())


def test_segments_relative_and_hv_resolve_to_absolute_lines() -> None:
    assert path_segments("m5 5 l10 0 v10 h-10 z") == (
        MoveTo(5, 5), LineTo(15, 5), LineTo(15, 15), LineTo(5, 15),
        ClosePath())


def test_segments_implicit_lineto_after_moveto() -> None:
    assert path_segments("M0 0 10 10 20 0") == (
        MoveTo(0, 0), LineTo(10, 10), LineTo(20, 0))


def test_segments_relative_moveto_after_close_uses_subpath_start() -> None:
    # after Z the current point is the subpath start (2, 3)
    assert path_segments("M2 3 L10 3 Z m1 1")[-1] == MoveTo(3, 4)


def test_segments_smooth_cubic_reflects_previous_control() -> None:
    segs = path_segments("M0 0 C0 -10 10 -10 10 0 S20 10 20 0")
    # reflection of (10, -10) about (10, 0) is (10, 10)
    assert segs[2] == CubicTo(10, 10, 20, 10, 20, 0)


def test_segments_smooth_cubic_without_predecessor_uses_current_point() -> None:
    segs = path_segments("M5 5 S10 10 20 5")
    assert segs[1] == CubicTo(5, 5, 10, 10, 20, 5)


def test_segments_smooth_quad_reflects_previous_control() -> None:
    segs = path_segments("M0 0 Q5 -10 10 0 T20 0")
    # reflection of (5, -10) about (10, 0) is (15, 10)
    assert segs[2] == QuadTo(15, 10, 20, 0)


def test_segments_relative_cubic() -> None:
    segs = path_segments("M10 10 c1 2 3 4 5 6")
    assert segs[1] == CubicTo(11, 12, 13, 14, 15, 16)


def test_segments_reject_arcs_and_leading_numbers() -> None:
    with pytest.raises(ValueError):
        path_segments("M0 0 A5 5 0 0 1 10 10")
    with pytest.raises(ValueError):
        path_segments("10 10 L20 20")
