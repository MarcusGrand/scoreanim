"""Project JSON round-trip (PHASES 4.5): intent only, everything intact."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.project import (FileRef, LayoutOverride,
                                    PartTextOverride, PresentationMode,
                                    ProjectDoc, StaffGroup, StageConfig,
                                    StageTextElement, StyleRules,
                                    TimingConfig, check_ref, from_dict,
                                    load_project, save_project, sha256_of,
                                    to_dict)
from scoreanim.core.animation import ElementStyle, RevealMode
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
        style=StyleRules(
            reveal_mode=RevealMode.CONTINUOUS,
            # 0.0 on purpose: falsy — pins that no reader `or`s it away
            floor_opacity=0.0,
            parts={PartId("P1"): ElementStyle(color="#cc2222",
                                              effect="pop"),
                   PartId("P2"): ElementStyle(effect="appear")},
            elements={ElementId("P1:m3:s1:v1:note:0"):
                      ElementStyle(color="#00aa00")},
        ),
        stage=StageConfig(
            mode=PresentationMode.SYSTEM,
            texts=(
                StageTextElement(element_id="stage:title",
                                 content="Det var…",
                                 page=1, x=1049.0, y=80.0, anchor="middle",
                                 font_size=63.5),
                StageTextElement(element_id="stage:composer",
                                 content="Grieg",
                                 page=1, x=1900.0, y=150.0, anchor="end",
                                 font_size=35.0, color="#C0C0C0",
                                 italic=True),
                # a tempo-overlay replacement (Phase 9.2): just a stage
                # text whose id carries the engraved element's id
                StageTextElement(element_id="stage:overlay:"
                                            "P1:m1:s1:v0:text:0",
                                 content="Swing ♩ = 126",
                                 page=1, x=471.4, y=99.6, anchor="start",
                                 font_size=40.5, bold=True),
            ),
        ),
        staff_groups=(StaffGroup(parts=(PartId("P1"), PartId("P2"),
                                        PartId("P3")),
                                 symbol="bracket", join_barlines=True),),
        text_overrides={PartId("P2"): PartTextOverride(
            name="Tenor Sax", abbreviation="T. Sx.")},
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
    # identical to a fresh doc EXCEPT hide_empty_staves, which is
    # deliberately version-gated (v<=3 predates the option → OFF)
    assert doc == replace(ProjectDoc(), hide_empty_staves=False)
    assert doc.timing.tempo_events == (TempoEvent(0.0, 120.0),)
    assert doc.style.reveal_mode is RevealMode.STEPPED


def test_reveal_mode_round_trip_and_legacy_default() -> None:
    """Phase 4 files carry no reveal_mode → STEPPED; unknown values are
    an error, not a silent default."""
    doc = _full_doc("/s.musicxml", "/a.wav")
    assert to_dict(doc)["style"]["reveal_mode"] == "continuous"
    assert from_dict(to_dict(doc)).style.reveal_mode \
        is RevealMode.CONTINUOUS
    with pytest.raises(ValueError, match="reveal mode"):
        from_dict({"version": 2, "style": {"reveal_mode": "wobbly"}})


def test_v1_part_colors_fold_into_style_rules() -> None:
    """A Phase 4 project file (version 1, style.part_colors) loads with
    its tints intact as part color rules; version 6 is refused."""
    legacy = from_dict({"version": 1,
                        "style": {"part_colors": {"P1": "#cc2222",
                                                  "P4": "#1c4fd6"}}})
    assert legacy.style.parts == {
        PartId("P1"): ElementStyle(color="#cc2222"),
        PartId("P4"): ElementStyle(color="#1c4fd6"),
    }
    assert legacy.style.reveal_mode is RevealMode.STEPPED
    assert legacy.style.elements == {}
    # new files declare version 5; a build from the future is refused
    assert to_dict(ProjectDoc())["version"] == 5
    with pytest.raises(ValueError, match="version"):
        from_dict({"version": 6})


def test_v4_hide_empty_staves() -> None:
    """v4 (Phase 10R): hide_empty_staves round-trips; files saved at
    v<=3 predate the option and load OFF (their look is unchanged);
    new documents default ON."""
    assert ProjectDoc().hide_empty_staves is True
    off = ProjectDoc(hide_empty_staves=False)
    assert to_dict(off)["hide_empty_staves"] is False
    assert from_dict(to_dict(off)).hide_empty_staves is False
    assert from_dict(to_dict(ProjectDoc())).hide_empty_staves is True
    assert from_dict({"version": 3}).hide_empty_staves is False
    assert from_dict({"version": 2}).hide_empty_staves is False
    # a v4 file missing the key (hand-edited) gets the new-doc default
    assert from_dict({"version": 4}).hide_empty_staves is True


def test_v2_file_loads_with_v3_defaults() -> None:
    """A Phase 5/6 file (version 2 — no floor_opacity, mode,
    staff_groups, or text_overrides keys) loads with the v3 defaults;
    the strict gate stays strict for unknown mode values."""
    v2 = {"version": 2,
          "style": {"reveal_mode": "continuous",
                    "parts": {"P1": {"color": "#cc2222"}}},
          "stage": {"texts": []}}
    doc = from_dict(v2)
    assert doc.style.floor_opacity == 0.3
    assert doc.style.reveal_mode is RevealMode.CONTINUOUS   # untouched
    assert doc.stage.mode is PresentationMode.PAGED
    assert doc.staff_groups == ()
    assert doc.text_overrides == {}
    with pytest.raises(ValueError, match="presentation mode"):
        from_dict({"version": 3, "stage": {"mode": "scrolling"}})


def test_v3_fields_round_trip() -> None:
    """floor 0.0 (falsy!), SYSTEM mode, groups, and text overrides all
    survive the dict round-trip; sparse override fields stay sparse."""
    doc = _full_doc("/s.musicxml", "/a.wav")
    payload = to_dict(doc)
    assert payload["style"]["floor_opacity"] == 0.0
    assert payload["stage"]["mode"] == "system"
    assert payload["staff_groups"] == [
        {"parts": ["P1", "P2", "P3"], "symbol": "bracket",
         "join_barlines": True}]
    assert payload["text_overrides"] == {
        "P2": {"name": "Tenor Sax", "abbreviation": "T. Sx."}}
    back = from_dict(payload)
    assert back.style.floor_opacity == 0.0
    assert back == doc
    # None fields of an override are omitted on write, restored as None
    sparse = ProjectDoc(text_overrides={
        PartId("P1"): PartTextOverride(name="Flute")})
    assert to_dict(sparse)["text_overrides"] == {"P1": {"name": "Flute"}}
    assert from_dict(to_dict(sparse)) == sparse
    # "" is an explicit blank, not a missing field: the writer's
    # `is not None` and the reader's `.get` keep falsy strings intact
    blank = ProjectDoc(text_overrides={
        PartId("P1"): PartTextOverride(abbreviation="")})
    assert to_dict(blank)["text_overrides"] == {"P1": {"abbreviation": ""}}
    assert from_dict(to_dict(blank)) == blank


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
                            "layout_overrides", "timing", "style", "stage",
                            "staff_groups", "text_overrides",
                            "hide_empty_staves", "condense_groups"}
