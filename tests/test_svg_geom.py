"""svg_geom unit tests against hand-computed geometry."""

import pytest

from scoreanim.core.engraving.svg_geom import (ellipse_path, parse_transform,
                                               path_bbox, polygon_path,
                                               rect_path)


def test_parse_translate_then_scale_applies_right_to_left() -> None:
    m = parse_transform("translate(10, 20) scale(2)")
    # point is scaled first, then translated
    assert m.apply(3, 4) == (16, 28)


def test_parse_scale_single_arg_is_uniform() -> None:
    m = parse_transform("scale(0.54)")
    assert m.apply(100, 100) == (54, 54)


def test_parse_rejects_rotate() -> None:
    with pytest.raises(ValueError):
        parse_transform("rotate(45)")


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
