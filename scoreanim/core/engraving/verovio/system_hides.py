"""Hide one part's staff in ONE system (2026-08-10).

Verovio has no per-system staff switch — `staffDef@visible` is ignored
even in 6.2.1 (spikes/system_staff_visibility.py) — but its optimize
pass hides any staff that is EMPTY for a whole system, and that is a
lever we already hold from the other side: the region fill makes
staves look occupied, so this pass makes them look blank. For every
overridden (system, part), each measure in the system's span that
carries no sounding note is stripped to one whole-bar <forward>, and
optimize does the hiding.

Sounding notes are never stripped: a measure with real music is left
intact, the staff stays visible there, and the report says so — the
override degrades to a warning instead of eating notes (rule 5's
fail-soft). Region-fill notes are NOT sounding (their ids carry
FILL_ID_PREFIX), so a slash-region staff hides cleanly, which is the
use case this exists for.

Like the fill, this transform feeds VEROVIO ONLY — canonical bytes,
music21, note_records and the timemap never see it — and it runs
AFTER the fill, so the fill's invisible notes are stripped back out of
the overridden spans. It needs scoreDef@optimize, so it only runs
under hide_empty_staves; and Verovio never hides on system 1 without
condenseFirstPage, so a system-1 override needs hide_first_system too
(the menu grays both cases).

The override key is the ordinal of the measure that STARTS the system
(the break maps' convention). An ordinal that no longer starts one is
inert, reported, never repaired.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Mapping

from scoreanim.core.engraving.verovio.region_fill import FILL_ID_PREFIX

# Measure children stripped from a hidden staff. Attributes, prints and
# barlines stay: clef/key/meter changes and the break set must survive.
_STRIPPED_TAGS = frozenset({"note", "forward", "backup", "direction",
                            "harmony", "figured-bass", "sound"})


@dataclass(frozen=True)
class StripReport:
    stripped: tuple[tuple[str, int], ...]   # (part id, measure ordinal)
    kept: tuple[tuple[int, str], ...]       # (ordinal, part) with notes
    inert: tuple[int, ...]                  # ordinals starting no system


def system_spans(root: ET.Element) -> dict[int, tuple[int, int]]:
    """System-start ordinal → (start, stop) measure span, [start, stop),
    read off the FIRST part's <print> breaks — the part every break
    pass writes into."""
    parts = root.findall("part")
    if not parts:
        return {}
    measures = parts[0].findall("measure")
    starts = [1]
    for ordinal, measure in enumerate(measures, start=1):
        if ordinal == 1:
            continue
        pr = measure.find("print")
        if pr is not None and (pr.get("new-system") == "yes"
                               or pr.get("new-page") == "yes"):
            starts.append(ordinal)
    spans: dict[int, tuple[int, int]] = {}
    for i, start in enumerate(starts):
        stop = starts[i + 1] if i + 1 < len(starts) else len(measures) + 1
        spans[start] = (start, stop)
    return spans


def _sounds(measure: ET.Element) -> bool:
    """True when the measure carries a real note — pitched or unpitched
    ink the user can hear. Region-fill notes do not count."""
    for note in measure.findall("note"):
        if (note.get("id") or "").startswith(FILL_ID_PREFIX):
            continue
        if note.find("pitch") is not None \
                or note.find("unpitched") is not None:
            return True
    return False


def _bar_duration(measure: ET.Element) -> int:
    """Net timeline length of the measure's content (the _voice_cursor
    arithmetic: notes and forwards advance, backups retreat; chord
    members do not advance)."""
    cursor = 0
    for el in measure:
        if el.tag == "note":
            if el.find("chord") is not None or el.find("grace") is not None:
                continue
            cursor += int(el.findtext("duration") or 0)
        elif el.tag == "forward":
            cursor += int(el.findtext("duration") or 0)
        elif el.tag == "backup":
            cursor -= int(el.findtext("duration") or 0)
    return max(cursor, 0)


def strip_hidden_staves(xml: str,
                        hides: Mapping[int, frozenset]
                        ) -> tuple[str, StripReport]:
    """The XML with every overridden, non-sounding measure blanked to a
    whole-bar <forward>, plus the report of what happened. Pure and
    deterministic; returns the input unchanged when nothing applies."""
    if not hides:
        return xml, StripReport((), (), ())
    root = ET.fromstring(xml)
    spans = system_spans(root)
    parts = {p.get("id", ""): p for p in root.findall("part")}
    stripped: list[tuple[str, int]] = []
    kept: list[tuple[int, str]] = []
    inert = tuple(sorted(o for o in hides if o not in spans))
    for ordinal in sorted(o for o in hides if o in spans):
        start, stop = spans[ordinal]
        for pid in sorted(str(p) for p in hides[ordinal]):
            part = parts.get(pid)
            if part is None:            # hidden globally, or gone —
                continue                # the global machinery warns
            measures = part.findall("measure")
            for m in range(start, min(stop, len(measures) + 1)):
                measure = measures[m - 1]
                if _sounds(measure):
                    kept.append((ordinal, pid))
                    continue
                duration = _bar_duration(measure)
                for el in [e for e in measure
                           if e.tag in _STRIPPED_TAGS]:
                    measure.remove(el)
                if duration > 0:
                    fwd = ET.SubElement(measure, "forward")
                    ET.SubElement(fwd, "duration").text = str(duration)
                stripped.append((pid, m))
    if not stripped and not kept and not inert:
        return xml, StripReport((), (), ())
    report = StripReport(tuple(stripped), tuple(sorted(set(kept))), inert)
    return (ET.tostring(root, encoding="unicode") if stripped else xml,
            report)
