"""seed_overlay_text (Phase 9.2): the tempo-mark replacement stage text,
seeded from the engraved element. Pure core — no Qt."""

import pytest

from scoreanim.core.project import from_dict, to_dict
from scoreanim.core.project.document import ProjectDoc
from scoreanim.core.project.stage_config import (OVERLAY_PREFIX, StageConfig,
                                                 seed_overlay_text)


@pytest.fixture(scope="module")
def tempo_element(engraved):
    (el,) = [e for e in engraved.layout.elements if e.text_class == "tempo"]
    return el


def test_seed_from_fixture_tempo_mark(tempo_element) -> None:
    seed = seed_overlay_text(tempo_element)
    assert seed.element_id == OVERLAY_PREFIX + "P1:m1:s1:v0:text:0"
    # the doubled metronome codepoint (BACKLOG 3's tofu) collapses and
    # maps to ♩; \xa0 normalizes to plain spaces
    assert seed.content == "Swing ♩ = 120"
    assert seed.page == 1
    assert seed.bold and not seed.italic
    assert seed.anchor == "start"
    # seeded at the engraved position/size: anchor point inside the
    # element's bbox, font size = the 405px text run in page units
    bbox = tempo_element.bbox
    assert bbox.x <= seed.x <= bbox.x + bbox.w
    assert bbox.y <= seed.y <= bbox.y + bbox.h
    assert seed.font_size == pytest.approx(40.5)


def test_seed_round_trips_through_serialization(tempo_element) -> None:
    seed = seed_overlay_text(tempo_element)
    doc = ProjectDoc(stage=StageConfig(texts=(seed,)))
    assert from_dict(to_dict(doc)).stage.texts == (seed,)
