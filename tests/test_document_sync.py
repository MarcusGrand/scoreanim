"""Document→scene diff-sync (M1.7), headless with fake scenes: each
pass applies exactly the diff (never a rebuild), the applied caches
make repeat passes no-ops, overrides layer over part tints and re-apply
after a retint, and sync_stage reports when the window must refresh its
retained AnimationInputs.
"""
from __future__ import annotations

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import (FLOOR_OPACITY,  # noqa: E402
                                      ElementStyle, StyleRules)
from scoreanim.core.project import LayoutOverride, ProjectDoc  # noqa: E402
from scoreanim.core.score.identity import (ElementId,  # noqa: E402
                                           ElementIdentity, ElementKind,
                                           PartId)
from scoreanim.ui.document_sync import DocumentSync  # noqa: E402

P1 = PartId("P1")
E1 = ElementId("e1")


class FakeItem:
    def __init__(self, identity) -> None:
        self.identity = identity
        self.colors: list = []           # set_color history, as names

    def set_color(self, color) -> None:
        self.colors.append(color.name() if color is not None else None)


class FakeScenes:
    def __init__(self, items=None) -> None:
        self.items = items or {}
        self.calls: list = []

    def set_ghost_opacity(self, value) -> None:
        self.calls.append(("floor", value))

    def set_part_color(self, pid, color) -> None:
        self.calls.append(("part", pid,
                           color.name() if color is not None else None))

    def set_stage_texts(self, texts) -> None:
        self.calls.append(("stage", texts))

    def set_element_hidden(self, eid, flag) -> None:
        self.calls.append(("hidden", eid, flag))


class FakePartsMenu:
    def __init__(self, pids=(P1,)) -> None:
        self._pids = tuple(pids)
        self.synced: list = []

    def part_ids(self) -> tuple:
        return self._pids

    def sync_checks(self, pid, rule) -> None:
        self.synced.append((pid, rule))


def _identity() -> ElementIdentity:
    # OTHER-with-onset takes part color (style.py), so overrides apply
    return ElementIdentity(element_id=E1, kind=ElementKind.OTHER,
                           part=P1, part_name="Flute", staff=1, voice=1,
                           onset=1.0)


def _doc(**style_fields) -> ProjectDoc:
    doc = ProjectDoc()
    if style_fields:
        doc = replace(doc, style=replace(doc.style, **style_fields))
    return doc


@pytest.fixture(autouse=True, scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sync():
    scenes = FakeScenes({E1: FakeItem(_identity())})
    parts_menu = FakePartsMenu()
    ds = DocumentSync(parts_menu)
    ds.bind_scenes(scenes, ProjectDoc().stage.texts)
    return ds, scenes, parts_menu


def test_unbound_sync_is_a_noop() -> None:
    ds = DocumentSync(FakePartsMenu())
    ds.sync_styles(_doc())                         # no scenes yet: no crash
    assert ds.sync_stage(_doc()) is False
    ds.sync_hidden(_doc())


def test_floor_diff_applies_once(sync) -> None:
    ds, scenes, _ = sync
    ds.sync_styles(_doc(floor_opacity=0.1))
    ds.sync_styles(_doc(floor_opacity=0.1))        # cached: no second push
    assert scenes.calls.count(("floor", 0.1)) == 1
    ds.sync_styles(_doc(floor_opacity=FLOOR_OPACITY))   # back to default
    assert ("floor", FLOOR_OPACITY) in scenes.calls


def test_part_tint_diff_and_removal(sync) -> None:
    ds, scenes, parts_menu = sync
    tinted = _doc(parts={P1: ElementStyle(color="#112233")})
    ds.sync_styles(tinted)
    ds.sync_styles(tinted)                         # cached: one push only
    assert scenes.calls.count(("part", P1, "#112233")) == 1
    ds.sync_styles(_doc())                         # rule removed → untint
    assert ("part", P1, None) in scenes.calls
    assert parts_menu.synced                       # checkmarks rode along


def test_element_override_layers_over_part_tint(sync) -> None:
    ds, scenes, _ = sync
    item = scenes.items[E1]
    both = _doc(parts={P1: ElementStyle(color="#112233")},
                elements={E1: ElementStyle(color="#aabbcc")})
    ds.sync_styles(both)
    assert item.colors[-1] == "#aabbcc"            # override wins
    # part retint → override re-applies on top of the fresh tint
    retinted = _doc(parts={P1: ElementStyle(color="#445566")},
                    elements={E1: ElementStyle(color="#aabbcc")})
    ds.sync_styles(retinted)
    assert item.colors[-1] == "#aabbcc"
    # override removed → item falls back to the part color
    ds.sync_styles(_doc(parts={P1: ElementStyle(color="#445566")}))
    assert item.colors[-1] == "#445566"


def test_sync_stage_reports_refresh_need(sync) -> None:
    ds, scenes, _ = sync
    doc = replace(ProjectDoc(), stage=replace(ProjectDoc().stage,
                                              texts=("t",)))
    assert ds.sync_stage(doc) is True              # window refreshes inputs
    assert ("stage", ("t",)) in scenes.calls
    assert ds.sync_stage(doc) is False             # cached: no re-apply


def test_sync_hidden_applies_and_reverts(sync) -> None:
    ds, scenes, _ = sync
    hidden = replace(ProjectDoc(),
                     layout_overrides={E1: LayoutOverride(hidden=True)})
    ds.sync_hidden(hidden)
    ds.sync_hidden(hidden)                         # cached: one push
    assert scenes.calls.count(("hidden", E1, True)) == 1
    ds.sync_hidden(ProjectDoc())                   # override gone → unhide
    assert ("hidden", E1, False) in scenes.calls
