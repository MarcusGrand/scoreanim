"""The region fill (2026-08-09): pure-function half. The pipeline half
— optimize keeps the staff, the guard stays quiet, note_records never
move — lives in test_hide_empty_staves.py and test_system_breaks.py.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from scoreanim.core.engraving.verovio.region_fill import (
    FILL_ID_PREFIX, _middle_line_pitches, fill_region_measures)
from scoreanim.core.score.musicxml_prep import SlashRegion


def _score(measures_xml: str) -> str:
    return (f'<score-partwise><part-list>'
            f'<score-part id="P1"/></part-list>'
            f'<part id="P1">{measures_xml}</part></score-partwise>')


def _measure(n: int, body: str = '<forward><duration>16</duration>'
                                '</forward>') -> str:
    return f'<measure number="{n}">{body}</measure>'


def test_no_regions_returns_the_input_object() -> None:
    xml = _score(_measure(1))
    assert fill_region_measures(xml, ()) is xml


def test_forwards_become_invisible_notes_of_the_same_duration() -> None:
    xml = _score(_measure(1) + _measure(2))
    out = fill_region_measures(xml, (SlashRegion("P1", 2, 3, 1.0),))
    root = ET.fromstring(out)
    m1, m2 = root.find("part").findall("measure")
    assert m1.find("forward") is not None          # outside the region
    assert m2.find("forward") is None
    note = m2.find("note")
    assert note.get("print-object") == "no"
    assert note.get("id") == f"{FILL_ID_PREFIX}P1-m2-0"
    assert note.findtext("duration") == "16"


def test_middle_line_follows_the_clef() -> None:
    """The fill pitch must sit ON the staff's middle line, or Verovio
    reserves vertical room for the invisible note and the whole system
    spreads (measured: 30 units on video_test's bass)."""
    def clef(sign, line=None, change=None):
        inner = f"<sign>{sign}</sign>"
        if line is not None:
            inner += f"<line>{line}</line>"
        if change is not None:
            inner += f"<clef-octave-change>{change}</clef-octave-change>"
        return f"<attributes><clef>{inner}</clef></attributes>"

    cases = [("G", 2, None, ("B", "4")),      # treble
             ("F", 4, None, ("D", "3")),      # bass
             ("C", 3, None, ("C", "4")),      # alto
             ("C", 4, None, ("A", "3")),      # tenor
             ("G", 2, -1, ("B", "3")),        # vocal tenor
             ("percussion", None, None, ("B", "4"))]
    for sign, line, change, expected in cases:
        root = ET.fromstring(_score(_measure(1, clef(sign, line, change))))
        measures = root.find("part").findall("measure")
        assert _middle_line_pitches(measures)[0] == expected, sign


def test_the_clef_in_force_carries_forward() -> None:
    bass = ("<attributes><clef><sign>F</sign><line>4</line></clef>"
            "</attributes>")
    root = ET.fromstring(_score(_measure(1, bass) + _measure(2)))
    measures = root.find("part").findall("measure")
    assert _middle_line_pitches(measures) == [("D", "3"), ("D", "3")]
