"""Golden-snapshot serializer: EngravedScore → canonical JSON text (Phase R.0).

The refactor safety net. A fixed xmlIdSeed makes adapter loads fully
deterministic, so a serialized EngravedScore is a stable fingerprint: the
mechanical split (R.1) must reproduce every committed baseline
BYTE-IDENTICALLY, and after the refactor the baselines stay in the suite
as the standing regression net for adapter work.

What is pinned, per element in LAYOUT ORDER (accumulator order over
membership-only sets — deterministic, and order is downstream-visible):
identity fields, page/system placement, exact float geometry (json floats
round-trip via repr), path/text counts, and a sha256 glyph hash over the
exact reprs of every PathPrimitive and TextPrimitive/TextRun — counts
alone would let the styling branches (fill-opacity→none, currentColor
defaults, bold/italic mapping, _RunAttrs inheritance) regress undetected.
Plus all AdapterNoteRecord fields, all (code, message) warning pairs,
page geometries, a sha256 of prepared.canonical_xml, and the engraved
MeasureTimeline (the app-wide beat authority since the FINDING-1 fix,
2026-07-22: per-ordinal starts/durations + score_end).

Pure data in, text out — no fixtures, no I/O, no pytest imports here.
"""

from __future__ import annotations

import hashlib
import json

from scoreanim.core.engraving.types import RenderedElement, RenderPrimitive
from scoreanim.core.engraving.verovio import (AdapterNoteRecord,
                                              EngravedScore)


def _glyph_sha256(glyph: RenderPrimitive) -> str:
    """Hash the exact reprs of every primitive. Dataclass reprs spell out
    every field with exact float reprs and are independent of the defining
    module, so they survive the package split unchanged."""
    h = hashlib.sha256()
    for p in glyph.paths:
        h.update(repr(p).encode())
        h.update(b"\n")
    for t in glyph.texts:
        h.update(repr(t).encode())
        h.update(b"\n")
    return h.hexdigest()


def _element_row(el: RenderedElement) -> dict:
    idn = el.identity
    return {
        "element_id": str(idn.element_id),
        "kind": idn.kind.name,
        "page": el.page,
        "system": el.system,
        "part": idn.part,
        "part_name": idn.part_name,
        "staff": idn.staff,
        "voice": idn.voice,
        "onset": idn.onset,
        "extent": list(idn.extent) if idn.extent is not None else None,
        "text_class": el.text_class,
        "x": el.x,
        "y": el.y,
        "bbox": [el.bbox.x, el.bbox.y, el.bbox.w, el.bbox.h],
        "anchor": [el.anchor.x, el.anchor.y],
        "n_paths": len(el.glyph.paths),
        "n_texts": len(el.glyph.texts),
        "glyph_sha256": _glyph_sha256(el.glyph),
    }


def _note_row(n: AdapterNoteRecord) -> dict:
    return {
        "element_id": str(n.element_id),
        "part": str(n.part),
        "measure": n.measure,
        "staff": n.staff,
        "voice": n.voice,
        "onset": n.onset,
        "grace": n.grace,
        "pitch_step": n.pitch_step,
        "pitch_alter": n.pitch_alter,
        "octave": n.octave,
        "staff_loc": n.staff_loc,
        "chord_group": n.chord_group,
        "order_in_voice": n.order_in_voice,
    }


def snapshot(engraved: EngravedScore) -> dict:
    """EngravedScore → plain-data snapshot dict, all sequences in their
    native (deterministic) order."""
    return {
        "canonical_xml_sha256": hashlib.sha256(
            engraved.prepared.canonical_xml.encode()).hexdigest(),
        "pages": [{"number": p.number, "width": p.width, "height": p.height}
                  for p in engraved.layout.pages],
        "elements": [_element_row(el) for el in engraved.layout.elements],
        "note_records": [_note_row(n) for n in engraved.note_records],
        "warnings": [{"code": w.code, "message": w.message}
                     for w in engraved.warnings],
        "measure_timeline": [
            {"ordinal": n,
             "start": engraved.timeline.starts[n],
             "duration": engraved.timeline.durations[n]}
            for n in sorted(engraved.timeline.starts)
        ] + [{"score_end": engraved.timeline.score_end}],
    }


def dumps(snap: dict) -> str:
    """Snapshot dict → canonical JSON text: one line per list row, so
    baseline diffs read per-element. json floats serialize via repr
    (shortest exact round-trip); allow_nan guards against silent NaNs."""
    parts: list[str] = ["{"]
    parts.append('"canonical_xml_sha256": '
                 + json.dumps(snap["canonical_xml_sha256"]) + ",")
    keys = ("pages", "elements", "note_records", "warnings",
            "measure_timeline")
    for key in keys:
        rows = snap[key]
        parts.append(f'"{key}": [')
        for i, row in enumerate(rows):
            tail = "," if i < len(rows) - 1 else ""
            parts.append(json.dumps(row, allow_nan=False) + tail)
        parts.append("]," if key != keys[-1] else "]")
    parts.append("}")
    return "\n".join(parts) + "\n"


def golden_text(engraved: EngravedScore) -> str:
    return dumps(snapshot(engraved))
