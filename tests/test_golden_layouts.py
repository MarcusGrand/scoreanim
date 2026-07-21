"""Golden-layout suite (Phase R.0): every fixture load must reproduce its
committed baseline BYTE-IDENTICALLY.

Captured before the adapter package split; the refactor's mechanical
moves (R.1) must keep every baseline unchanged, and R.4 behavior fixes
re-capture the affected baselines in the fixing commit. Permanent: the
baselines stay as the standing regression net for adapter work.

To re-capture after a DELIBERATE behavior change:
    SCOREANIM_UPDATE_GOLDENS=1 python -m pytest tests/test_golden_layouts.py
then commit the diff alongside the change that caused it.

The 12 loads reuse the session fixtures (conftest) and deliberately cover
the retry/option branches where a botched move would hide: video_test
flat AND hidden, bigband1 hidden (stray-path re-homing, strict=False),
complex3 hidden (skip-if-absent), condense_min flat AND condensed,
tall_system_min (scale-to-fit). complex2 stays out (~20 s; the
score-doctor is its check).
"""

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

from .golden import dumps, golden_text, snapshot

GOLDEN_DIR = Path(__file__).resolve().parent / "goldens"

# golden file name → conftest session fixture holding the load
GOLDEN_LOADS = {
    "testscore": "engraved",
    "broken_hairpin_and_slur_test": "engraved_spanners",
    "video_test_flat": "engraved_video",
    "video_test_hidden": "engraved_video_hidden",
    "complex1": "engraved_complex1",
    "bigband1_hidden": "engraved_bigband_hidden",
    "complex3_hidden": "engraved_complex3_hidden",
    "pickup_min": "engraved_pickup",
    "bar_repeat_min": "engraved_bar_repeat",
    "condense_min_flat": "engraved_condense_flat",
    "condense_min_condensed": "engraved_condense_grouped",
    "tall_system_min": "engraved_tall_system",
}


@pytest.mark.parametrize("name", sorted(GOLDEN_LOADS))
def test_golden(name: str, request: pytest.FixtureRequest) -> None:
    engraved = request.getfixturevalue(GOLDEN_LOADS[name])
    text = golden_text(engraved)
    path = GOLDEN_DIR / f"{name}.json"
    if os.environ.get("SCOREANIM_UPDATE_GOLDENS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    if not path.exists():
        pytest.fail(f"no baseline {path.name} — capture it with "
                    f"SCOREANIM_UPDATE_GOLDENS=1")
    assert text == path.read_text(), (
        f"{path.name} differs from the committed baseline. If this change "
        f"is DELIBERATE, re-capture with SCOREANIM_UPDATE_GOLDENS=1 and "
        f"commit the diff with the change that caused it.")


# --- comparator sensitivity (R.0 check): the serializer must not be able
# --- to swallow a removed element, a nudged float, or changed glyph ink.

def test_removed_element_changes_text(engraved_pickup) -> None:
    snap = snapshot(engraved_pickup)
    mutated = copy.deepcopy(snap)
    del mutated["elements"][3]
    assert dumps(mutated) != dumps(snap)


def test_mutated_float_changes_text(engraved_pickup) -> None:
    snap = snapshot(engraved_pickup)
    mutated = copy.deepcopy(snap)
    mutated["elements"][0]["x"] += 0.5
    assert dumps(mutated) != dumps(snap)


def test_changed_glyph_hash_changes_text(engraved_pickup) -> None:
    snap = snapshot(engraved_pickup)
    mutated = copy.deepcopy(snap)
    mutated["elements"][0]["glyph_sha256"] = "0" * 64
    assert dumps(mutated) != dumps(snap)


def test_fresh_capture_is_byte_identical(engraved_pickup) -> None:
    """Determinism pin: a second independent load serializes to the same
    bytes (fixed xmlIdSeed — the property the whole suite rests on)."""
    from scoreanim.core.engraving.types import EngravingParams
    from scoreanim.core.engraving.verovio_adapter import \
        VerovioEngravingProvider
    from .conftest import PICKUP_SCORE
    again = VerovioEngravingProvider().load_detailed(PICKUP_SCORE,
                                                     EngravingParams())
    assert golden_text(again) == golden_text(engraved_pickup)
