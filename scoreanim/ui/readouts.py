"""Pure readout helpers shared by the window and (M1) the inspector.

Qt-free on purpose: these are display/derivation functions over document
intent, headless-tested in tests/test_readouts.py. Commit handlers stay
with their widgets; only the pure reads live here.
"""

from __future__ import annotations

from typing import Sequence

from scoreanim.core.project import DEFAULT_BPM, ProjectDoc
from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing.retime import bpm_at
from scoreanim.core.timing.swing import swing_warp
from scoreanim.core.timing.tempo_map import TempoEvent


def format_time(s: float) -> str:
    """m:ss.d transport-clock text; negatives clamp to 0:00.0."""
    s = max(0.0, s)
    return f"{int(s // 60)}:{int(s % 60):02d}.{int(s * 10 % 10)}"


def initial_tempo_event(doc: ProjectDoc) -> TempoEvent | None:
    """The earliest tempo event — what the Tempo field shows and what
    _commit_bpm moves. None when the map is empty (display falls back
    to DEFAULT_BPM)."""
    events = doc.timing.tempo_events
    return min(events, key=lambda e: e.position) if events else None


def global_swing_ratio(doc: ProjectDoc) -> float:
    """v1 reads the single global region; a multi-region doc (from a
    later build or hand edit) shows its first ratio, and committing
    the spinbox collapses it to one global region."""
    regions = doc.timing.swing_regions
    return regions[0].ratio if regions else 0.5


def tempo_scope(doc: ProjectDoc, beat: float | None,
                measures: Sequence[MeasureInfo] = ()) -> tuple[str, float]:
    """What the Tempo field is editing, and the bpm it should show.

    With a grid line selected the field sets the tempo from THAT line on;
    with nothing selected it edits the initial tempo, as it always has.
    The label names the line so the two cannot be confused.
    """
    if beat is None:
        event = initial_tempo_event(doc)
        return "Tempo", event.bpm if event else DEFAULT_BPM
    number = next((m.number for m in measures
                   if abs(m.start - beat) < 1e-9), None)
    where = f"m{number}" if number is not None else f"beat {beat:g}"
    return f"Tempo from {where}", bpm_at(
        doc.timing.tempo_events, swing_warp(beat, doc.timing.swing_regions))
