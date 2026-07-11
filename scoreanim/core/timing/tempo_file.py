"""Hand-entered tempo sidecar files (Phase 3 authoring surface).

One directive per line; ``#`` starts a comment; blank lines ignored.

    offset 1.80          # seconds of audio before score beat 0
    m1 120               # <position> <bpm>
    m13+2 118            # position: <float beats> | m<n> | m<n>+<float beats>
    32 116

``m<n>`` resolves through the score's MeasureInfo table so the user
never does beat arithmetic across meter changes (the fixture's 2/4 bars
make raw quarter-note math error-prone). Parse errors raise ValueError
carrying the 1-based line number. Persistence in the project document is
Phase 4.5; this file format is the interim user-intent store.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from scoreanim.core.score.identity import Beats
from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing.tempo_map import TempoEvent


@dataclass(frozen=True)
class TempoSetup:
    offset_seconds: float                # audio seconds at score beat 0
    events: tuple[TempoEvent, ...]


def _parse_float(token: str, lineno: int, what: str) -> float:
    try:
        return float(token)
    except ValueError:
        raise ValueError(f"line {lineno}: bad {what} {token!r}") from None


def _parse_position(token: str, starts: Mapping[int, Beats],
                    lineno: int) -> Beats:
    if not token.startswith("m"):
        return _parse_float(token, lineno, "beat position")
    body, plus, extra = token[1:].partition("+")
    try:
        number = int(body)
    except ValueError:
        raise ValueError(f"line {lineno}: bad measure number {token!r}") from None
    if number not in starts:
        raise ValueError(f"line {lineno}: unknown measure m{number}")
    beats = starts[number]
    if plus:
        beats += _parse_float(extra, lineno, "beat offset")
    return beats


def parse_tempo_file(text: str, measures: Sequence[MeasureInfo]) -> TempoSetup:
    starts = {m.number: m.start for m in measures}
    offset: float | None = None
    events: list[TempoEvent] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if parts[0] == "offset":
            if offset is not None:
                raise ValueError(f"line {lineno}: offset given more than once")
            if len(parts) != 2:
                raise ValueError(f"line {lineno}: expected 'offset <seconds>'")
            offset = _parse_float(parts[1], lineno, "offset")
            continue
        if len(parts) != 2:
            raise ValueError(f"line {lineno}: expected '<position> <bpm>', "
                             f"got {line!r}")
        position = _parse_position(parts[0], starts, lineno)
        bpm = _parse_float(parts[1], lineno, "bpm")
        events.append(TempoEvent(position, bpm))
    if not events:
        raise ValueError("tempo file contains no tempo events")
    return TempoSetup(offset_seconds=offset if offset is not None else 0.0,
                      events=tuple(events))
