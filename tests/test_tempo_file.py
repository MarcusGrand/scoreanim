"""Tempo sidecar parsing: position forms, defaults, line-numbered errors."""
from __future__ import annotations

import pytest

from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing.tempo_file import parse_tempo_file

MEASURES = (
    MeasureInfo(number=1, start=0.0, quarter_length=4.0),
    MeasureInfo(number=2, start=4.0, quarter_length=4.0),
    MeasureInfo(number=3, start=8.0, quarter_length=2.0),   # a 2/4 bar
    MeasureInfo(number=4, start=10.0, quarter_length=4.0),
)


def test_happy_path_all_position_forms() -> None:
    setup = parse_tempo_file(
        """
        # comment line
        offset 1.80   # trailing comment
        m1 120
        m3+1.5 118
        10 116
        """,
        MEASURES,
    )
    assert setup.offset_seconds == 1.80
    assert [(e.position, e.bpm) for e in setup.events] == [
        (0.0, 120.0), (9.5, 118.0), (10.0, 116.0)]


def test_offset_defaults_to_zero() -> None:
    assert parse_tempo_file("m1 120", MEASURES).offset_seconds == 0.0


def test_fixture_measure_resolution(score_model) -> None:
    setup = parse_tempo_file("m5 119", score_model.measures)
    assert setup.events[0].position == 16.0     # mm 1-4 are 4/4


@pytest.mark.parametrize("text, lineno", [
    ("m99 120", 1),                       # unknown measure
    ("m1 fast", 1),                       # bad bpm
    ("mx 120", 1),                        # bad measure number
    ("m1+x 120", 1),                      # bad beat offset
    ("abc 120", 1),                       # bad beat position
    ("m1 120\noffset 1\noffset 2", 3),    # multiple offsets
    ("offset", 1),                        # malformed offset
    ("m1 120 extra", 1),                  # too many tokens
])
def test_errors_carry_line_number(text: str, lineno: int) -> None:
    with pytest.raises(ValueError, match=f"line {lineno}"):
        parse_tempo_file(text, MEASURES)


def test_no_events_raises() -> None:
    with pytest.raises(ValueError, match="no tempo events"):
        parse_tempo_file("offset 1.0\n# nothing else", MEASURES)
