"""Smoke tests for core types: construction, immutability, geometry math."""

import dataclasses

import pytest

from scoreanim.core.engraving.types import Affine, Point, Rect
from scoreanim.core.score.identity import (ElementId, ElementIdentity,
                                           ElementKind, PartId)


def test_identity_is_frozen() -> None:
    ident = ElementIdentity(
        element_id=ElementId("P1:m1:s1:v1:note:0"),
        kind=ElementKind.NOTEHEAD,
        part=PartId("P1"), part_name="Sop. Alto Ten. 1",
        staff=1, voice=1, onset=1.0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ident.onset = 2.0  # type: ignore[misc]


def test_rect_union_and_contains() -> None:
    a = Rect(0, 0, 10, 10)
    b = Rect(5, 5, 10, 10)
    u = a.union(b)
    assert (u.x, u.y, u.w, u.h) == (0, 0, 15, 15)
    assert u.contains(a) and u.contains(b)
    assert not a.contains(b)
    assert a.center == Point(5, 5)


def test_affine_compose_translate_then_scale() -> None:
    scale = Affine(a=2, d=3)
    translate = Affine(e=10, f=20)
    # translate ∘ scale: scale the point first, then translate
    m = translate.compose(scale)
    assert m.apply(1, 1) == (12, 23)
    # scale ∘ translate: translate first, then scale
    m2 = scale.compose(translate)
    assert m2.apply(1, 1) == (22, 63)


def test_affine_rect_mapping_handles_negative_scale() -> None:
    flip = Affine(d=-1)                        # SMuFL glyphs use scale(1,-1)
    r = flip.apply_rect(Rect(0, 10, 5, 5))
    assert (r.x, r.y, r.w, r.h) == (0, -15, 5, 5)


def test_affine_rect_mapping_corner_maps_90_degree_rotation() -> None:
    # 90-degree rotation is exact via corner mapping (Phase 11): a 10x2
    # rect becomes 2x10 (Verovio's vertical text)
    rot = Affine(a=0, b=1, c=-1, d=0)          # rotate(90)
    r = rot.apply_rect(Rect(0, 0, 10, 2))
    assert (round(r.w, 6), round(r.h, 6)) == (2.0, 10.0)
