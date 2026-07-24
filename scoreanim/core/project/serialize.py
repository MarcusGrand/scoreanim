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

from scoreanim.core.animation.reveal import RevealMode
from scoreanim.core.animation.style import ElementStyle, StyleRules
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.project.document import (CondenseGroup, FileRef,
                                             LayoutOverride, PartTextOverride,
                                             ProjectDoc, StaffGroup,
                                             TimingConfig)
from scoreanim.core.project.stage_config import (PresentationMode,
                                                 StageConfig,
                                                 StageTextElement)
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
PROJECT_VERSION = 6
_READABLE_VERSIONS = (1, 2, 3, 4, 5, 6)
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
        },
        "style": {
            "reveal_mode": doc.style.reveal_mode.name.lower(),
            "floor_opacity": doc.style.floor_opacity,
            "parts": {str(p): _style_out(s)
                      for p, s in sorted(doc.style.parts.items())},
            "elements": {str(e): _style_out(s)
                         for e, s in sorted(doc.style.elements.items())},
        },
        "stage": {
            "mode": doc.stage.mode.name.lower(),
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
            ),
            style=_style_rules_in(data.get("style") or {}),
            stage=StageConfig(
                mode=_presentation_mode_in(
                    data.get("stage", {}).get("mode")),
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
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"malformed project data: {exc!r}") from exc


def _reveal_mode_in(value: Any) -> RevealMode:
    if value is None:
        return RevealMode.STEPPED
    try:
        return RevealMode[str(value).upper()]
    except KeyError as exc:
        raise ValueError(f"unknown reveal mode {value!r}") from exc


def _presentation_mode_in(value: Any) -> PresentationMode:
    if value is None:                      # v1/v2 files: no "mode" key
        return PresentationMode.PAGED
    try:
        return PresentationMode[str(value).upper()]
    except KeyError as exc:
        raise ValueError(f"unknown presentation mode {value!r}") from exc


def _text_override_out(override: PartTextOverride) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if override.name is not None:
        out["name"] = override.name
    if override.abbreviation is not None:
        out["abbreviation"] = override.abbreviation
    return out


def _style_out(style: ElementStyle) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if style.color is not None:
        out["color"] = style.color
    if style.effect is not None:
        out["effect"] = style.effect
    return out


def _style_in(data: dict[str, Any]) -> ElementStyle:
    return ElementStyle(color=data.get("color"), effect=data.get("effect"))


def _style_rules_in(style: dict[str, Any]) -> StyleRules:
    parts = {PartId(p): _style_in(s)
             for p, s in style.get("parts", {}).items()}
    # v1 legacy: {"part_colors": {pid: "#rrggbb"}} folds into part color
    # rules (explicit "parts" entries win if both are present)
    for p, c in style.get("part_colors", {}).items():
        parts.setdefault(PartId(p), ElementStyle(color=c))
    return StyleRules(
        reveal_mode=_reveal_mode_in(style.get("reveal_mode")),
        # .get, never `or`: a saved floor of 0.0 is falsy and must load
        floor_opacity=style.get("floor_opacity", 0.3),
        parts=parts,
        elements={ElementId(e): _style_in(s)
                  for e, s in style.get("elements", {}).items()},
    )


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
