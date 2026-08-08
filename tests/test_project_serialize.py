"""Project JSON round-trip (PHASES 4.5): intent only, everything intact."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.project import (FileRef, LayoutOverride, PageBreak,
                                    PartTextOverride, PresentationMode,
                                    ProjectDoc, StaffGroup, StageConfig,
                                    StageTextElement, StyleRules,
                                    StemDirection, SystemBreak,
                                    TimingConfig, VideoCanvas, check_ref,
                                    from_dict, load_project, save_project,
                                    sha256_of, to_dict)
from scoreanim.core.animation import (ElementStyle, RevealMode, read_colors,
                                      read_pulse, read_volume)
from scoreanim.core.score.identity import ElementId, PartId
from scoreanim.core.timing import SwingRegion, Tap, TapSession, TempoEvent


def _full_doc(score_path: str, audio_path: str) -> ProjectDoc:
    """Every field populated — the round-trip must lose nothing."""
    return ProjectDoc(
        score=FileRef(path=score_path, sha256="ab" * 32),
        audio=FileRef(path=audio_path, sha256=None),
        engraving=EngravingParams(xml_id_seed=42, suppress_header=True,
                                  scale=1.3),
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
            # v7: document default + params, including a preset this
            # build doesn't know — the round-trip must lose nothing
            default_effect="pop",
            effect_params={"pop": {"scale": 2.0, "note_value": True},
                           "shimmer": {"wobble": [1, 2.5, "x"]}},
        ),
        stage=StageConfig(
            mode=PresentationMode.SYSTEM,
            canvas=VideoCanvas(width=1080, height=1920),
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
        # v8: both directions, and ordinals whose string sort differs
        # from their numeric one (the writer sorts numerically)
        system_break_overrides={3: SystemBreak.FORCE,
                                12: SystemBreak.SUPPRESS},
        # v9: the page twin, both directions, same numeric-sort trap
        page_break_overrides={5: PageBreak.SUPPRESS,
                              21: PageBreak.FORCE},
        # v11: hand-flipped stems, both directions
        stem_directions={
            ElementId("P1:m3:s1:v1:stem:0"): StemDirection.UP,
            ElementId("P4:m12:s1:v2:stem:3"): StemDirection.DOWN,
        },
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
    its tints intact as part color rules; a future version is refused."""
    legacy = from_dict({"version": 1,
                        "style": {"part_colors": {"P1": "#cc2222",
                                                  "P4": "#1c4fd6"}}})
    assert legacy.style.parts == {
        PartId("P1"): ElementStyle(color="#cc2222"),
        PartId("P4"): ElementStyle(color="#1c4fd6"),
    }
    assert legacy.style.reveal_mode is RevealMode.STEPPED
    assert legacy.style.elements == {}
    # new files declare version 12 (video canvas); a build from the
    # future is refused
    assert to_dict(ProjectDoc())["version"] == 12
    with pytest.raises(ValueError, match="version"):
        from_dict({"version": 13})


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


def test_v6_hide_first_system() -> None:
    """v6 (beta, 2026-07-24): hide_first_system round-trips; every
    older file (and a v6 file missing the key) loads OFF — the
    first-system-full look is unchanged."""
    assert ProjectDoc().hide_first_system is False
    on = ProjectDoc(hide_first_system=True)
    assert to_dict(on)["hide_first_system"] is True
    assert from_dict(to_dict(on)).hide_first_system is True
    assert from_dict(to_dict(ProjectDoc())).hide_first_system is False
    for version in (1, 2, 3, 4, 5, 6):
        assert from_dict({"version": version}).hide_first_system is False


def test_v7_default_effect_and_params() -> None:
    """v7 (M4): default_effect + effect_params round-trip; v5 and v6
    files (and any older) load with None/{} — unchanged look."""
    doc = ProjectDoc(style=StyleRules(
        default_effect="pop",
        effect_params={"pop": {"settle": 0.5}}))
    out = to_dict(doc)["style"]
    assert out["default_effect"] == "pop"
    assert out["effect_params"] == {"pop": {"settle": 0.5}}
    again = from_dict(to_dict(doc))
    assert again.style.default_effect == "pop"
    assert again.style.effect_params == {"pop": {"settle": 0.5}}
    for version in (1, 2, 3, 4, 5, 6):
        old = from_dict({"version": version,
                         "style": {"floor_opacity": 0.2}})
        assert old.style.default_effect is None
        assert old.style.effect_params == {}
        assert old.style.floor_opacity == 0.2


def test_v7_keys_omitted_at_defaults() -> None:
    """None default / empty params leave the saved style block exactly
    key-free (a param deleted down to nothing disappears from the
    JSON, and a default doc's style block matches the v6 shape)."""
    style = to_dict(ProjectDoc())["style"]
    assert "default_effect" not in style
    assert "effect_params" not in style


def test_unknown_effect_params_round_trip_byte_for_byte(tmp_path) -> None:
    """A preset/key this build doesn't consume is written back
    verbatim: two save cycles produce identical bytes."""
    doc = ProjectDoc(style=StyleRules(
        effect_params={"shimmer": {"wobble": [1, 2.5, "x"], "n": 3}}))
    p1, p2 = tmp_path / "a.scoreanim", tmp_path / "b.scoreanim"
    save_project(doc, p1)
    save_project(load_project(p1), p2)
    assert p1.read_bytes() == p2.read_bytes()
    assert load_project(p2).style.effect_params == \
        {"shimmer": {"wobble": [1, 2.5, "x"], "n": 3}}


def test_the_glows_old_strength_folds_in_on_read() -> None:
    """The one effect param this build consumes rather than round-trips.
    Strength multiplied the envelope's two levels and nothing else, so a
    project tuned to 0.6 opens with those levels at 0.6 and the key
    gone — the same light, one knob fewer, and it can never fold twice
    because there is nothing left to fold."""
    doc = from_dict({"version": 11,
                     "style": {"effect_params": {"glow": {"strength": 0.6,
                                                          "radius": 30.0}}}})
    entry = doc.style.effect_params["glow"]
    assert "strength" not in entry
    assert entry["sustain"] == pytest.approx(0.6)
    assert entry["swell_level"] == pytest.approx(0.6)
    assert entry["radius"] == 30.0          # the rest is untouched
    # and it stays folded across a save
    assert from_dict(to_dict(doc)).style.effect_params["glow"] == entry


def test_a_glow_without_a_strength_is_untouched() -> None:
    """Non-vacuity for the fold: everything else about the entry, and
    every other preset, goes through exactly as it always did."""
    raw = {"glow": {"radius": 30.0, "sustain": 0.5}, "pop": {"settle": 0.5}}
    doc = from_dict({"version": 11, "style": {"effect_params": raw}})
    assert doc.style.effect_params == raw


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


def test_v8_system_break_overrides() -> None:
    """v8 (M5, 2026-07-28): the sparse break delta round-trips; every
    older file loads with {} — the pre-option look, so no read gate."""
    assert ProjectDoc().system_break_overrides == {}
    doc = ProjectDoc(system_break_overrides={3: SystemBreak.FORCE,
                                             12: SystemBreak.SUPPRESS})
    payload = to_dict(doc)
    # JSON object keys are strings, and the ordinals are sorted
    # NUMERICALLY (a string sort would put "12" before "3")
    assert payload["system_break_overrides"] == {"3": "force",
                                                 "12": "suppress"}
    assert list(payload["system_break_overrides"]) == ["3", "12"]
    assert from_dict(payload) == doc
    assert from_dict(to_dict(ProjectDoc())).system_break_overrides == {}
    for version in (1, 2, 3, 4, 5, 6, 7):
        assert from_dict({"version": version}).system_break_overrides == {}


def test_v11_stem_directions() -> None:
    """v11 (2026-08-03): the sparse flip map round-trips, and every
    older file loads with {} — which is the automatic rule alone, so no
    read gate. The automatic half stores nothing at all, so an old
    project re-engraves with corrected stems either way."""
    assert ProjectDoc().stem_directions == {}
    doc = ProjectDoc(stem_directions={
        ElementId("P1:m3:s1:v1:stem:0"): StemDirection.UP,
        ElementId("P4:m12:s1:v2:stem:3"): StemDirection.DOWN})
    payload = to_dict(doc)
    assert payload["stem_directions"] == {"P1:m3:s1:v1:stem:0": "up",
                                          "P4:m12:s1:v2:stem:3": "down"}
    assert from_dict(payload) == doc
    assert from_dict(to_dict(ProjectDoc())).stem_directions == {}
    for version in range(1, 12):
        assert from_dict({"version": version}).stem_directions == {}


def test_v11_rejects_unknown_stem_direction() -> None:
    with pytest.raises(ValueError, match="stem direction"):
        from_dict({"version": 11,
                   "stem_directions": {"P1:m1:s1:v1:stem:0": "sideways"}})


def test_v8_rejects_unknown_break_mode() -> None:
    with pytest.raises(ValueError, match="system break"):
        from_dict({"version": 8, "system_break_overrides": {"3": "maybe"}})


def test_v9_page_break_overrides() -> None:
    """v9 (M6, 2026-07-28): the page delta round-trips exactly as the
    system one does; every older file loads with {} — the pre-option
    look, so no read gate (D6)."""
    assert ProjectDoc().page_break_overrides == {}
    doc = ProjectDoc(page_break_overrides={5: PageBreak.SUPPRESS,
                                           21: PageBreak.FORCE})
    payload = to_dict(doc)
    assert payload["page_break_overrides"] == {"5": "suppress",
                                               "21": "force"}
    # numeric sort, not string: "21" must not precede "5"
    assert list(payload["page_break_overrides"]) == ["5", "21"]
    assert from_dict(payload) == doc
    assert from_dict(to_dict(ProjectDoc())).page_break_overrides == {}
    for version in (1, 2, 3, 4, 5, 6, 7, 8):
        assert from_dict({"version": version}).page_break_overrides == {}


def test_v9_rejects_unknown_page_break_mode() -> None:
    with pytest.raises(ValueError, match="page break"):
        from_dict({"version": 9, "page_break_overrides": {"3": "maybe"}})


def test_the_two_break_maps_are_independent() -> None:
    """Same key shape, same JSON encoding — so the round trip must keep
    them apart rather than folding one onto the other."""
    doc = ProjectDoc(system_break_overrides={4: SystemBreak.SUPPRESS},
                     page_break_overrides={4: PageBreak.FORCE})
    out = from_dict(to_dict(doc))
    assert out.system_break_overrides == {4: SystemBreak.SUPPRESS}
    assert out.page_break_overrides == {4: PageBreak.FORCE}
    assert out == doc


def test_v9_file_is_refused_by_a_v8_reader() -> None:
    """The gate's own test, per D6: a tagged v8 build (v0.2-beta.4) must
    REFUSE a v9 file rather than silently drop the page breaks and
    destroy them on the next save (the v2 rationale). This is the whole
    point of bumping, since the field itself needs no read gate."""
    import scoreanim.core.project.serialize as ser

    payload = to_dict(ProjectDoc(
        page_break_overrides={3: PageBreak.FORCE}))
    original = ser._READABLE_VERSIONS
    ser._READABLE_VERSIONS = tuple(v for v in original if v <= 8)
    try:
        with pytest.raises(ValueError, match="version"):
            ser.from_dict(payload)
    finally:
        ser._READABLE_VERSIONS = original


def test_v8_file_is_refused_by_a_v7_reader() -> None:
    """The gate's own test: the strict-by-version rule is the point of
    bumping at all — a tagged v7 build (v0.2-beta.3) must REFUSE a v8
    file rather than silently drop the breaks and destroy them on the
    next save (the v2 rationale)."""
    import scoreanim.core.project.serialize as ser

    payload = to_dict(ProjectDoc(
        system_break_overrides={3: SystemBreak.FORCE}))
    old = tuple(v for v in ser._READABLE_VERSIONS if v <= 7)
    original = ser._READABLE_VERSIONS
    ser._READABLE_VERSIONS = old
    try:
        with pytest.raises(ValueError, match="version"):
            ser.from_dict(payload)
    finally:
        ser._READABLE_VERSIONS = original


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
                            "hide_empty_staves", "hide_first_system",
                            "condense_groups", "system_break_overrides",
                            "page_break_overrides", "stem_directions"}


def test_v10_locked_beats_round_trip_and_older_files_have_none() -> None:
    """Locks are user intent, so they persist. A missing key means
    nothing is locked, which is exactly right for every v<=9 file — no
    read gate needed."""
    doc = ProjectDoc(timing=TimingConfig(locked_beats=(0.0, 4.0, 12.5)))
    assert from_dict(to_dict(doc)).timing.locked_beats == (0.0, 4.0, 12.5)
    old = from_dict({"version": 9, "timing": {"offset_seconds": 1.0}})
    assert old.timing.locked_beats == ()


def test_v10_file_is_refused_by_a_v9_reader() -> None:
    """The gate's own test, per D6: a tagged v9 build (v0.2-beta.6) must
    REFUSE a v10 file rather than silently drop the locks and destroy
    them on the next save (the v2 rationale)."""
    import scoreanim.core.project.serialize as ser

    payload = to_dict(ProjectDoc(timing=TimingConfig(locked_beats=(4.0,))))
    original = ser._READABLE_VERSIONS
    ser._READABLE_VERSIONS = tuple(v for v in original if v <= 9)
    try:
        with pytest.raises(ValueError, match="version"):
            ser.from_dict(payload)
    finally:
        ser._READABLE_VERSIONS = original


# -- v11: the volume response ---------------------------------------------

def test_v11_volume_round_trips_raw() -> None:
    """The sparse volume map survives a save/load cycle, including a key
    this build does not consume — the effect_params guarantee, so a
    project written by a newer build is not damaged by an older one."""
    doc = ProjectDoc(style=StyleRules(
        volume={"amount": 0.8, "quiet": 0.25, "loud": 2.0,
                "curve": "perceptual"}))
    out = from_dict(to_dict(doc))
    assert out.style.volume == {"amount": 0.8, "quiet": 0.25, "loud": 2.0,
                                "curve": "perceptual"}
    assert out == doc
    # sparse: nothing stored writes no key at all
    assert "volume" not in to_dict(ProjectDoc())["style"]


def test_older_files_load_with_the_response_off() -> None:
    """No read gate: a missing key means {} for every older version,
    which reads as amount 0, which is gain 1 everywhere — exactly the
    look those files have always had."""
    for version in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
        assert from_dict({"version": version}).style.volume == {}
    assert read_volume(from_dict({"version": 10}).style.volume).is_off


def test_v11_file_is_refused_by_a_v10_reader() -> None:
    """The gate's own test: a tagged v10 build must REFUSE a v11 file
    rather than silently drop the volume settings and destroy them on
    the next save (the v2 rationale). This is the whole point of
    bumping, since the field itself needs no read gate."""
    import scoreanim.core.project.serialize as ser

    payload = to_dict(ProjectDoc(style=StyleRules(volume={"amount": 1.0})))
    assert payload["version"] == 12              # v12 since the canvas
    original = ser._READABLE_VERSIONS
    ser._READABLE_VERSIONS = tuple(v for v in original if v <= 10)
    try:
        with pytest.raises(ValueError, match="version"):
            ser.from_dict(payload)
    finally:
        ser._READABLE_VERSIONS = original


# -- v11: the system pulse, riding the same version -----------------------

def test_v11_pulse_round_trips_raw() -> None:
    """The volume map's twin: same sparse shape, same raw round-trip,
    same version. A key this build does not consume survives."""
    doc = ProjectDoc(style=StyleRules(
        pulse={"amount": 0.12, "shape": "square"}))
    out = from_dict(to_dict(doc))
    assert out.style.pulse == {"amount": 0.12, "shape": "square"}
    assert out == doc
    # sparse: nothing stored writes no key at all
    assert "pulse" not in to_dict(ProjectDoc())["style"]


def test_v11_color_mode_round_trips_raw() -> None:
    """The third entry of the same shape: sparse, raw, same version. A
    key this build does not consume survives, like effect_params — which
    is what leaves room for per-colour fine-tuning later."""
    doc = ProjectDoc(style=StyleRules(
        colors={"mode": "dark", "background": "#101014"}))
    out = from_dict(to_dict(doc))
    assert out.style.colors == {"mode": "dark", "background": "#101014"}
    assert out == doc


def test_an_untouched_document_writes_no_colors_key_at_all() -> None:
    """The bit-for-bit promise, from the document side: a project that
    never touches the mode is byte-identical to one written before it
    existed."""
    assert "colors" not in to_dict(ProjectDoc())["style"]


def test_older_files_load_in_light_mode() -> None:
    """No read gate: a missing key means {} for every older version,
    which reads as light — exactly the look those files have always
    had."""
    for version in range(1, 12):
        style = from_dict({"version": version}).style
        assert style.colors == {}
        assert read_colors(style.colors).is_default


def test_dark_mode_round_trips_through_a_real_file(tmp_path) -> None:
    path = tmp_path / "dark.scoreanim"
    save_project(ProjectDoc(style=StyleRules(colors={"mode": "dark"})), path)
    out = load_project(path)
    assert out.style.colors == {"mode": "dark"}
    assert read_colors(out.style.colors).is_dark


def test_the_pop_settings_ride_the_same_entry() -> None:
    """The second mode is more keys in the map the first one already
    has, which is what keeps it clear of a schema bump."""
    doc = ProjectDoc(style=StyleRules(
        pulse={"amount": 0.05, "pop_amount": 0.1, "notes_for_full": 8,
               "settle": 0.4}))
    out = from_dict(to_dict(doc))
    assert out.style.pulse == doc.style.pulse
    pulse = read_pulse(out.style.pulse)
    assert (pulse.amount, pulse.pop_amount) == (0.05, 0.1)
    assert (pulse.notes_for_full, pulse.settle) == (8, 0.4)


def test_the_two_v11_maps_are_stored_apart() -> None:
    """One setting each, never sharing a map: turning the page's pulse
    up must not touch how hard a single note pops."""
    doc = ProjectDoc(style=StyleRules(volume={"amount": 0.4},
                                      pulse={"amount": 0.1}))
    out = from_dict(to_dict(doc))
    assert out.style.volume == {"amount": 0.4}
    assert out.style.pulse == {"amount": 0.1}


def test_older_files_load_with_the_pulse_off() -> None:
    """No read gate, for the identical reason: a missing key means {},
    which reads as amount 0, which never touches a system — exactly the
    look those files have always had."""
    for version in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
        assert from_dict({"version": version}).style.pulse == {}
    assert read_pulse(from_dict({"version": 10}).style.pulse).is_off


# -- v12: the video canvas ---------------------------------------------------

def test_v12_canvas_round_trips() -> None:
    doc = ProjectDoc(stage=StageConfig(
        canvas=VideoCanvas(width=1080, height=1920)))
    out = from_dict(to_dict(doc))
    assert out.stage.canvas == VideoCanvas(1080, 1920)


def test_v12_score_scale_round_trips_and_is_sparse() -> None:
    """The score's size rides engraving (it is an engraving input);
    the default 1.0 writes no key at all, so an untouched document
    keeps its byte shape."""
    scaled = ProjectDoc(engraving=EngravingParams(scale=1.3))
    payload = to_dict(scaled)
    assert payload["engraving"]["scale"] == 1.3
    assert from_dict(payload).engraving.scale == 1.3
    assert "scale" not in to_dict(ProjectDoc())["engraving"]
    for version in (1, 7, 11):
        assert from_dict({"version": version}).engraving.scale == 1.0


def test_a_pre_release_crop_scale_in_the_canvas_is_ignored() -> None:
    """One same-day build wrote stage.canvas.scale meaning a CROP;
    that number must not leak into the engraving scale, and the canvas
    itself still loads."""
    doc = from_dict({"version": 12,
                     "stage": {"canvas": {"width": 1080, "height": 1920,
                                          "scale": 1.5}}})
    assert doc.stage.canvas == VideoCanvas(1080, 1920)
    assert doc.engraving.scale == 1.0


def test_no_canvas_writes_no_key_at_all() -> None:
    """Sparse: a canvas-free document's stage shape is byte-identical
    to what v11 wrote (plus the version number)."""
    payload = to_dict(ProjectDoc())
    assert "canvas" not in payload["stage"]


def test_older_files_load_with_no_canvas() -> None:
    """No read gate: a missing key means None, the page-aspect frame
    every older file has always had."""
    for version in (1, 4, 7, 10, 11):
        assert from_dict({"version": version}).stage.canvas is None


def test_a_v11_reader_refuses_a_v12_file() -> None:
    """The bump's whole point: refuse loudly instead of silently
    dropping the user's framing on a resave."""
    from scoreanim.core.project import serialize as ser

    payload = to_dict(ProjectDoc(stage=StageConfig(
        canvas=VideoCanvas(1080, 1920))))
    assert payload["version"] == 12
    original = ser._READABLE_VERSIONS
    ser._READABLE_VERSIONS = tuple(v for v in original if v <= 11)
    try:
        with pytest.raises(ValueError, match="version"):
            ser.from_dict(payload)
    finally:
        ser._READABLE_VERSIONS = original


def test_v12_lyrics_size_round_trips_and_is_sparse() -> None:
    sized = ProjectDoc(engraving=EngravingParams(lyric_size=0.7))
    payload = to_dict(sized)
    assert payload["engraving"]["lyric_size"] == 0.7
    assert from_dict(payload).engraving.lyric_size == 0.7
    assert "lyric_size" not in to_dict(ProjectDoc())["engraving"]
    for version in (1, 7, 11):
        assert from_dict({"version": version}).engraving.lyric_size == 1.0


def test_v12_staff_line_width_round_trips_and_is_sparse() -> None:
    sized = ProjectDoc(engraving=EngravingParams(staff_line_width=1.5))
    payload = to_dict(sized)
    assert payload["engraving"]["staff_line_width"] == 1.5
    assert from_dict(payload).engraving.staff_line_width == 1.5
    assert "staff_line_width" not in to_dict(ProjectDoc())["engraving"]
    for version in (1, 7, 11):
        assert from_dict({"version": version}) \
            .engraving.staff_line_width == 1.0
