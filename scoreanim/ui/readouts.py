"""Pure readout helpers shared by the window and (M1) the inspector.

Qt-free on purpose: these are display/derivation functions over document
intent, headless-tested in tests/test_readouts.py. Commit handlers stay
with their widgets; only the pure reads live here.
"""

from __future__ import annotations

from scoreanim.core.project import ProjectDoc
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
