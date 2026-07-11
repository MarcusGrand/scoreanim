"""Project JSON round-trip (PHASES 4.5): intent only, everything intact."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.project import (FileRef, LayoutOverride, ProjectDoc,
                                    StageConfig, StageTextElement,
                                    StyleConfig, TimingConfig, check_ref,
                                    from_dict, load_project, save_project,
                                    sha256_of, to_dict)
from scoreanim.core.animation import RevealMode
from scoreanim.core.score.identity import ElementId, PartId
from scoreanim.core.timing import SwingRegion, Tap, TapSession, TempoEvent


def _full_doc(score_path: str, audio_path: str) -> ProjectDoc:
    """Every field populated — the round-trip must lose nothing."""
    return ProjectDoc(
        score=FileRef(path=score_path, sha256="ab" * 32),
        audio=FileRef(path=audio_path, sha256=None),
        engraving=EngravingParams(xml_id_seed=42, suppress_header=True),
        layout_overrides={
            ElementId("P1:m3:s1:v1:note:0"): LayoutOverride(dx=2.5, dy=-1.0),
            ElementId("P2:m4:s1:v1:stem:1"): LayoutOverride(hidden=True),
        },
        timing=TimingConfig(
            offset_seconds=1.8,
            tempo_events=(TempoEvent(0.0, 118.0), TempoEvent(16.0, 92.5)),
            swing_regions=(SwingRegion((16.0, 32.0), 0.62),),
            tap_sessions=(TapSession(unit=1.0, taps=(
                Tap(24.0, 13.412), Tap(25.0, 13.955), Tap(26.0, 14.508))),),
        ),
        style=StyleConfig(part_colors={PartId("P1"): "#cc2222"},
                          reveal_mode=RevealMode.CONTINUOUS),
        stage=StageConfig(texts=(
            StageTextElement(element_id="stage:title", content="Det var…",
                             page=1, x=1049.0, y=80.0, anchor="middle",
                             font_size=63.5),
            StageTextElement(element_id="stage:composer", content="Grieg",
                             page=1, x=1900.0, y=150.0, anchor="end",
                             font_size=35.0, color="#C0C0C0", italic=True),
        )),
    )


def test_dict_round_trip_is_identity() -> None:
    doc = _full_doc("/scores/test.musicxml", "/audio/take3.wav")
    assert from_dict(to_dict(doc)) == doc


def test_file_round_trip_with_relative_paths(tmp_path: Path) -> None:
    score = tmp_path / "test.musicxml"
    audio = tmp_path / "audio" / "take3.wav"
    audio.parent.mkdir()
    score.write_text("<score/>")
    audio.write_bytes(b"RIFF")
    doc = _full_doc(str(score), str(audio))
    project = tmp_path / "sync.scoreanim"
    save_project(doc, project)

    data = json.loads(project.read_text())
    assert data["score"]["path"] == "test.musicxml"       # relativized
    assert data["audio"]["path"] == str(Path("audio") / "take3.wav")

    loaded = load_project(project)
    assert loaded == doc                                  # paths absolute again


def test_defaults_for_absent_optional_fields() -> None:
    doc = from_dict({"version": 1})
    assert doc == ProjectDoc()
    assert doc.timing.tempo_events == (TempoEvent(0.0, 120.0),)
    assert doc.style.reveal_mode is RevealMode.STEPPED


def test_reveal_mode_round_trip_and_legacy_default() -> None:
    """Phase 4 files carry no reveal_mode → STEPPED; unknown values are
    an error, not a silent default."""
    doc = _full_doc("/s.musicxml", "/a.wav")
    assert to_dict(doc)["style"]["reveal_mode"] == "continuous"
    assert from_dict(to_dict(doc)).style.reveal_mode \
        is RevealMode.CONTINUOUS
    legacy = from_dict({"version": 1,
                        "style": {"part_colors": {"P1": "#cc2222"}}})
    assert legacy.style.reveal_mode is RevealMode.STEPPED
    with pytest.raises(ValueError, match="reveal mode"):
        from_dict({"version": 1, "style": {"reveal_mode": "wobbly"}})


def test_version_guard() -> None:
    with pytest.raises(ValueError, match="version"):
        from_dict({"version": 99})
    with pytest.raises(ValueError, match="version"):
        from_dict({})


def test_malformed_data_raises_value_error() -> None:
    with pytest.raises(ValueError, match="malformed"):
        from_dict({"version": 1,
                   "timing": {"tempo_events": [{"position": 0.0}]}})


def test_load_rejects_non_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.scoreanim"
    bad.write_text("not json {")
    with pytest.raises(ValueError, match="JSON"):
        load_project(bad)


def test_check_ref(tmp_path: Path) -> None:
    f = tmp_path / "take.wav"
    f.write_bytes(b"RIFF1234")
    good = FileRef(path=str(f), sha256=sha256_of(f))
    assert check_ref(good) is None
    assert check_ref(FileRef(path=str(f), sha256=None)) is None  # no hash: ok
    f.write_bytes(b"RIFF5678")
    assert "changed" in check_ref(good)
    assert "missing" in check_ref(FileRef(path=str(tmp_path / "gone.wav"),
                                          sha256=None))


def test_never_persists_derived_data() -> None:
    """The schema has no slot for layouts, timemaps, or peaks (rule 5)."""
    payload = to_dict(_full_doc("/s.musicxml", "/a.wav"))
    assert set(payload) == {"version", "score", "audio", "engraving",
                            "layout_overrides", "timing", "style", "stage"}
