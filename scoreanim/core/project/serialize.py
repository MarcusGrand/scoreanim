"""Project document ⇄ versioned JSON (.scoreanim files).

Only intent is persisted (rule 5): file refs (relative paths + content
hashes), engraving params, layout override deltas, tempo events, swing
regions, RAW tap sessions, part colors, stage texts. Never layouts,
timemaps, peaks, or any derived geometry.

Because the document is one immutable value and commands are the only
way it changes, saving is just "serialize the current value"; commands
themselves are never serialized.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.project.document import (CondenseGroup, FileRef,
                                             LayoutOverride, PageBreak,
                                             PartTextOverride, ProjectDoc,
                                             StaffGroup, StemDirection,
                                             SystemBreak, TimingConfig)
from scoreanim.core.project.serialize_style import style_out, style_rules_in
from scoreanim.core.project.stage_config import (PresentationMode,
                                                 StageConfig,
                                                 StageTextElement,
                                                 VideoCanvas)
from scoreanim.core.score.identity import ElementId, PartId
from scoreanim.core.timing.swing import SwingRegion
from scoreanim.core.timing.taps import Tap, TapSession
from scoreanim.core.timing.tempo_map import TempoEvent

# 2 (Phase 5.3): "style" became the StyleRules shape (reveal_mode, parts,
# elements) — a version bump, not a tolerated-unknown-key change, so a
# Phase 4 build REFUSES a v2 file instead of silently dropping styling
# and destroying it on the next save. v1 files still load: part_colors
# folds into part color rules below.
# 3 (Phase 7.1): ONE bump carrying every planned v2 field — style
# floor_opacity, stage mode, staff_groups (consumed Phase 8),
# text_overrides (consumed Phase 9) — designed once, no per-phase
# bumps. v1/v2 files load with defaults for every new field.
# 4 (Phase 10R): hide_empty_staves. Deliberately version-gated on read:
# files saved at v<=3 predate the option and load OFF so their look is
# unchanged; new documents default ON (document.py).
# 5 (Phase 12.3): condense_groups. No read gate needed — a missing key
# defaults to () (no condensing), the correct look for older files.
# 6 (beta, 2026-07-24): hide_first_system — hide empty staves on the
# first system too. No read gate: missing key → False, the pre-option
# look. The bump keeps the frozen alpha refusing beta files instead of
# silently dropping the flag on a resave (the v2 rationale; ROADMAP's
# "M4 → v6" plan shifts by one).
# 7 (M4 Effects, 2026-07-25): style.default_effect (omitted when None)
# + style.effect_params (sparse {preset: {key: value}}, round-tripped
# raw — presets/keys this build doesn't consume survive a save/load
# cycle untouched). No read gate: v5/v6 files load with
# default_effect=None and effect_params={} — unchanged look. The bump
# keeps v0.2-beta.1 (a TAGGED v6 reader) refusing loudly instead of
# silently dropping both keys on a resave. M5's ROADMAP "v7" shifts
# to v8.
# 8 (M5 Breaks, 2026-07-28): system_break_overrides — a sparse
# {measure ordinal: "force"|"suppress"} delta on the score's encoded
# break set, written as an object because JSON keys are strings. No read
# gate: a missing key defaults to {}, which is "no overrides", which is
# exactly the pre-option look for every v<=7 file. The bump keeps
# v0.2-beta.3 (a TAGGED v7 reader) refusing loudly instead of silently
# dropping the user's breaks on a resave — the v2 rationale.
# 9 (M6 Pages, 2026-07-28): page_break_overrides — the twin of v8's map,
# same sparse {measure ordinal: "force"|"suppress"} shape, same
# stringified-and-numerically-sorted keys. No read gate, for the identical
# reason: a missing key defaults to {}, which is "no overrides", which is
# exactly the pre-option look for every v<=8 file. The bump keeps
# v0.2-beta.4 (a TAGGED v8 reader) refusing loudly instead of silently
# dropping the user's page breaks on a resave.
# 10 (grid alignment, 2026-07-30): timing.locked_beats — the beats the
# user has pinned in the timeline lane, which anchor every grid drag.
# No read gate: a missing key defaults to (), which is "nothing locked",
# which is exactly the pre-option behaviour for every v<=9 file. The bump
# keeps v0.2-beta.6 (a TAGGED v9 reader) refusing loudly instead of
# silently dropping the user's locks on a resave — the v2 rationale.
# 11 (volume response, 2026-08-01): style.volume — the sparse
# {key: value} map over "amount", "quiet" and "loud" that says how much
# the recording's loudness changes how strongly a note animates.
# Round-tripped raw, like effect_params, so a key this build doesn't
# consume survives a save/load cycle. No read gate: a missing key
# defaults to {}, which reads as amount 0, which is gain 1 everywhere —
# exactly the pre-option look for every v<=10 file. The bump keeps a
# v10 reader refusing loudly instead of silently dropping the user's
# settings on a resave — the v2 rationale.
#   Also v11 (system pulse, 2026-08-02): style.pulse — the sparse
#   {key: value} map over "amount" that says how much the whole page
#   swells with the recording. Same shape, same raw round-trip, same
#   "missing key means off" reading, so it rides this version rather
#   than taking one of its own: no build has ever shipped reading v11,
#   so a second number would protect nothing (the v3 precedent — ONE
#   bump carrying every planned field).
#   Also v11 (page colours, 2026-08-02): style.colors — the sparse
#   {key: value} map over "background" and "ink". Third entry of the
#   same shape and it rides v11 for the same reason: v11 is still
#   untagged, so no shipped build can be surprised by it, and a missing
#   key means the default look (white paper, black ink), which needs no
#   read gate. Values are validated where they are consumed
#   (animation.page_colors.read_colors), not here.
#   Also v11 (stem directions, 2026-08-03): stem_directions — the
#   sparse {stem ElementId: "up"|"down"} map of stems the user flipped
#   by hand. Fourth entry to ride v11, and the same argument: v11 is
#   still untagged, so no shipped build can be surprised, and a missing
#   key means an empty map, which is the automatic rule alone and needs
#   no read gate. Note the AUTOMATIC half of the feature stores nothing
#   at all — dropping <stem> on single-voice staves is unconditional
#   (rule 5: intent only, and there is no intent to record) — so an old
#   project opened here re-engraves with corrected stems whether or not
#   it carries this key. Values ARE validated on read: unlike a style
#   number, a bad direction has no sensible fallback.
#   Also v11 (glow strength retired, 2026-08-05): NO new key — one goes
#   away. effect_params["glow"]["strength"] was a second multiplier on
#   the brightness the glow's envelope already sets, so it folds into
#   that envelope's two levels on read and is never written again. No
#   bump, for the reason the shape/peak fold needed none: the entry is
#   sparse and round-trips raw, an older build reading a folded file
#   just sees a strength of 1 with the levels already turned down, and
#   the look is the same either way. This is the ONE key we consume
#   rather than round-trip, and it is the second legacy fold in this
#   file after v1's part_colors.
# 12 (video canvas, 2026-08-06): stage.canvas — {width, height, scale},
# the user's video frame and the score's size inside it, previewed live
# and used verbatim as the export size. Omitted when unset. No read
# gate: a missing key means no canvas, the page-aspect frame every
# older file has always had. The bump keeps a v11 reader refusing
# loudly instead of silently dropping the user's framing on a resave —
# the v2 rationale. (Marcus approved this bump 2026-08-06.)
PROJECT_VERSION = 12
_READABLE_VERSIONS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
SUFFIX = ".scoreanim"


# ---------------------------------------------------------------------------
# to_dict / from_dict
# ---------------------------------------------------------------------------

def to_dict(doc: ProjectDoc, base_dir: Path | None = None) -> dict[str, Any]:
    return {
        "version": PROJECT_VERSION,
        "score": _ref_out(doc.score, base_dir),
        "audio": _ref_out(doc.audio, base_dir),
        "engraving": {
            "xml_id_seed": doc.engraving.xml_id_seed,
            "suppress_header": doc.engraving.suppress_header,
        },
        "layout_overrides": [
            {"element_id": str(eid), "dx": o.dx, "dy": o.dy,
             "hidden": o.hidden}
            for eid, o in sorted(doc.layout_overrides.items())
        ],
        "timing": {
            "offset_seconds": doc.timing.offset_seconds,
            "tempo_events": [
                {"position": e.position, "bpm": e.bpm}
                for e in doc.timing.tempo_events
            ],
            "swing_regions": [
                {"start": r.span[0], "end": r.span[1], "ratio": r.ratio}
                for r in doc.timing.swing_regions
            ],
            "tap_sessions": [
                {"unit": s.unit,
                 "taps": [{"beat": t.beat, "seconds": t.seconds}
                          for t in s.taps]}
                for s in doc.timing.tap_sessions
            ],
            "locked_beats": list(doc.timing.locked_beats),
        },
        # the style sub-shape lives with its reader in serialize_style.py
        "style": style_out(doc.style),
        "stage": {
            "mode": doc.stage.mode.name.lower(),
            # v12: the video canvas, omitted when unset (sparse — a
            # canvas-free document is byte-identical to v11's shape)
            **({"canvas": {"width": doc.stage.canvas.width,
                           "height": doc.stage.canvas.height,
                           "scale": doc.stage.canvas.scale}}
               if doc.stage.canvas is not None else {}),
            "texts": [
                {"element_id": t.element_id, "content": t.content,
                 "page": t.page, "x": t.x, "y": t.y, "anchor": t.anchor,
                 "font_size": t.font_size, "color": t.color,
                 "bold": t.bold, "italic": t.italic}
                for t in doc.stage.texts
            ],
        },
        "staff_groups": [
            {"parts": [str(p) for p in g.parts], "symbol": g.symbol,
             "join_barlines": g.join_barlines}
            for g in doc.staff_groups
        ],
        "text_overrides": {
            str(p): _text_override_out(o)
            for p, o in sorted(doc.text_overrides.items())
        },
        "hide_empty_staves": doc.hide_empty_staves,
        "hide_first_system": doc.hide_first_system,
        "condense_groups": [
            {"parts": [str(p) for p in g.parts], "name": g.name,
             "abbreviation": g.abbreviation}
            for g in doc.condense_groups
        ],
        # v8: sparse break delta. JSON object keys are strings, so the
        # ordinal is stringified; sorted NUMERICALLY so a saved file is
        # deterministic and reads in score order (not "10" before "2").
        "system_break_overrides": {
            str(ordinal): mode.value
            for ordinal, mode in sorted(doc.system_break_overrides.items())
        },
        # v9: the page twin, written exactly the same way
        "page_break_overrides": {
            str(ordinal): mode.value
            for ordinal, mode in sorted(doc.page_break_overrides.items())
        },
        # v11: hand-flipped stems, keyed by minted stem ElementId and
        # sorted so a saved file is deterministic
        "stem_directions": {
            str(eid): direction.value
            for eid, direction in sorted(doc.stem_directions.items())
        },
    }


def from_dict(data: dict[str, Any],
              base_dir: Path | None = None) -> ProjectDoc:
    version = data.get("version")
    if version not in _READABLE_VERSIONS:
        raise ValueError(f"unsupported project version {version!r} "
                         f"(this build reads versions "
                         f"{_READABLE_VERSIONS})")
    try:
        timing = data.get("timing", {})
        default_timing = TimingConfig()
        return ProjectDoc(
            score=_ref_in(data.get("score"), base_dir),
            audio=_ref_in(data.get("audio"), base_dir),
            engraving=EngravingParams(
                xml_id_seed=data.get("engraving", {}).get("xml_id_seed", 42),
                suppress_header=data.get("engraving", {})
                .get("suppress_header", True),
            ),
            layout_overrides={
                ElementId(o["element_id"]): LayoutOverride(
                    dx=o.get("dx", 0.0), dy=o.get("dy", 0.0),
                    hidden=o.get("hidden", False))
                for o in data.get("layout_overrides", [])
            },
            timing=TimingConfig(
                offset_seconds=timing.get("offset_seconds", 0.0),
                tempo_events=tuple(
                    TempoEvent(e["position"], e["bpm"])
                    for e in timing["tempo_events"]
                ) if timing.get("tempo_events")
                else default_timing.tempo_events,
                swing_regions=tuple(
                    SwingRegion((r["start"], r["end"]), r["ratio"])
                    for r in timing.get("swing_regions", [])
                ),
                tap_sessions=tuple(
                    TapSession(unit=s["unit"], taps=tuple(
                        Tap(t["beat"], t["seconds"]) for t in s["taps"]))
                    for s in timing.get("tap_sessions", [])
                ),
                locked_beats=tuple(sorted(timing.get("locked_beats", ()))),
            ),
            style=style_rules_in(data.get("style") or {}),
            stage=StageConfig(
                mode=_presentation_mode_in(
                    data.get("stage", {}).get("mode")),
                # v12: missing key → None → the page-aspect frame,
                # which is the look every older file has always had
                canvas=_canvas_in(data.get("stage", {}).get("canvas")),
                texts=tuple(
                    StageTextElement(
                        element_id=t["element_id"], content=t["content"],
                        page=t["page"], x=t["x"], y=t["y"],
                        anchor=t["anchor"], font_size=t["font_size"],
                        color=t.get("color"), bold=t.get("bold", False),
                        italic=t.get("italic", False))
                    for t in data.get("stage", {}).get("texts", [])
                ),
            ),
            staff_groups=tuple(
                StaffGroup(parts=tuple(PartId(p) for p in g["parts"]),
                           symbol=g.get("symbol", "bracket"),
                           join_barlines=g.get("join_barlines", True))
                for g in data.get("staff_groups", [])
            ),
            text_overrides={
                PartId(p): PartTextOverride(
                    name=o.get("name"),
                    abbreviation=o.get("abbreviation"))
                for p, o in data.get("text_overrides", {}).items()
            },
            # v<=3 predates the option: load OFF so the file's look is
            # unchanged; a v4 file missing the key gets the new default
            hide_empty_staves=data.get("hide_empty_staves", version >= 4),
            # v6: missing key → False (first system full), the pre-option
            # look for every older file
            hide_first_system=data.get("hide_first_system", False),
            condense_groups=tuple(
                CondenseGroup(parts=tuple(PartId(p) for p in g["parts"]),
                              name=g.get("name", ""),
                              abbreviation=g.get("abbreviation", ""))
                for g in data.get("condense_groups", [])
            ),
            # v8: missing key → {} (no overrides), the pre-option look for
            # every older file — so no read gate (§1.4)
            system_break_overrides={
                int(ordinal): _system_break_in(mode)
                for ordinal, mode in
                data.get("system_break_overrides", {}).items()
            },
            # v9: missing key → {} again, so no read gate (D6)
            page_break_overrides={
                int(ordinal): _page_break_in(mode)
                for ordinal, mode in
                data.get("page_break_overrides", {}).items()
            },
            # v11: missing key → {}, which is the automatic rule alone
            stem_directions={
                ElementId(str(eid)): _stem_direction_in(value)
                for eid, value in data.get("stem_directions", {}).items()
            },
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"malformed project data: {exc!r}") from exc


def _canvas_in(data: dict[str, Any] | None) -> VideoCanvas | None:
    if data is None:
        return None
    return VideoCanvas(width=int(data["width"]), height=int(data["height"]),
                       scale=float(data.get("scale", 1.0)))


def _presentation_mode_in(value: Any) -> PresentationMode:
    if value is None:                      # v1/v2 files: no "mode" key
        return PresentationMode.PAGED
    try:
        return PresentationMode[str(value).upper()]
    except KeyError as exc:
        raise ValueError(f"unknown presentation mode {value!r}") from exc


def _system_break_in(value: Any) -> SystemBreak:
    try:
        return SystemBreak(str(value))
    except ValueError as exc:
        raise ValueError(f"unknown system break mode {value!r}") from exc


def _page_break_in(value: Any) -> PageBreak:
    try:
        return PageBreak(str(value))
    except ValueError as exc:
        raise ValueError(f"unknown page break mode {value!r}") from exc


def _stem_direction_in(value: Any) -> StemDirection:
    try:
        return StemDirection(str(value))
    except ValueError as exc:
        raise ValueError(f"unknown stem direction {value!r}") from exc


def _text_override_out(override: PartTextOverride) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if override.name is not None:
        out["name"] = override.name
    if override.abbreviation is not None:
        out["abbreviation"] = override.abbreviation
    return out


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------

def save_project(doc: ProjectDoc, path: Path) -> None:
    payload = to_dict(doc, base_dir=path.parent)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_project(path: Path) -> ProjectDoc:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: not a project object")
    return from_dict(data, base_dir=path.parent)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def check_ref(ref: FileRef) -> str | None:
    """None if the referenced file looks right; otherwise a warning
    string (missing / changed since save). Never raises — the caller
    decides whether a warning blocks."""
    path = Path(ref.path)
    if not path.is_file():
        return f"missing file: {ref.path}"
    if ref.sha256 is not None and sha256_of(path) != ref.sha256:
        return f"{path.name} has changed since the project was saved"
    return None


def _ref_out(ref: FileRef | None,
             base_dir: Path | None) -> dict[str, Any] | None:
    if ref is None:
        return None
    path = ref.path
    if base_dir is not None and os.path.isabs(path):
        try:
            path = os.path.relpath(path, base_dir)
        except ValueError:           # e.g. different drive on Windows
            pass
    return {"path": path, "sha256": ref.sha256}


def _ref_in(data: dict[str, Any] | None,
            base_dir: Path | None) -> FileRef | None:
    if data is None:
        return None
    path = data["path"]
    if base_dir is not None and not os.path.isabs(path):
        path = os.path.normpath(base_dir / path)
    return FileRef(path=str(path), sha256=data.get("sha256"))
