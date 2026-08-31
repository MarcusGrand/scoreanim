"""The region fill (2026-08-09): pure-function half. The pipeline half
— optimize keeps the staff, the guard stays quiet, note_records never
move — lives in test_hide_empty_staves.py and test_system_breaks.py.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from scoreanim.core.engraving.verovio.region_fill import (
    FILL_ID_PREFIX, _middle_line_pitches, fill_region_measures,
    slash_fill_id)
from scoreanim.core.score.musicxml_prep import RepeatRegion, SlashRegion


def _score(measures_xml: str) -> str:
    return (f'<score-partwise><part-list>'
            f'<score-part id="P1"/></part-list>'
            f'<part id="P1">{measures_xml}</part></score-partwise>')


# divisions=4, so a 4/4 bar is duration 16 and a quarter is 4
_DIVISIONS = '<attributes><divisions>4</divisions></attributes>'


def _measure(n: int, body: str = '<forward><duration>16</duration>'
                                '</forward>') -> str:
    return f'<measure number="{n}">{body}</measure>'


def test_no_regions_returns_the_input_object() -> None:
    xml = _score(_measure(1))
    assert fill_region_measures(xml, (), ()) is xml


def test_a_slash_bar_gets_one_invisible_note_per_slash_unit() -> None:
    """The point of the fill since 2026-08-31: Verovio spaces these
    notes by its own rules, and synthesis stands a slash on each one,
    so a slash lands exactly where a quarter note would."""
    xml = _score(_measure(1, _DIVISIONS + '<forward><duration>16</duration>'
                                          '</forward>') + _measure(2))
    out = fill_region_measures(xml, (SlashRegion("P1", 1, 2, 1.0),))
    root = ET.fromstring(out)
    m1, m2 = root.find("part").findall("measure")
    assert m1.find("forward") is None
    assert m2.find("forward") is not None          # outside the region
    notes = m1.findall("note")
    assert len(notes) == 4
    for k, note in enumerate(notes):
        assert note.get("print-object") == "no"
        assert note.get("id") == slash_fill_id("P1", 1, k)
        assert note.findtext("duration") == "4"    # a quarter each


def test_the_measure_duration_is_untouched_by_the_split() -> None:
    xml = _score(_measure(1, _DIVISIONS + '<forward><duration>16</duration>'
                                          '</forward>'))
    out = fill_region_measures(xml, (SlashRegion("P1", 1, 2, 1.0),))
    m1 = ET.fromstring(out).find("part").find("measure")
    total = sum(int(n.findtext("duration")) for n in m1.findall("note"))
    assert total == 16


def test_a_half_note_slash_unit_gives_two_notes() -> None:
    xml = _score(_measure(1, _DIVISIONS + '<forward><duration>16</duration>'
                                          '</forward>'))
    out = fill_region_measures(xml, (SlashRegion("P1", 1, 2, 2.0),))
    notes = ET.fromstring(out).find("part").find("measure").findall("note")
    assert [n.findtext("duration") for n in notes] == ["8", "8"]


def test_a_bar_that_does_not_divide_evenly_keeps_one_whole_bar_note() -> None:
    """7 duration units against a quarter of 4 — synthesis falls back to
    spreading that measure rather than standing on notes that are not
    there."""
    xml = _score(_measure(1, _DIVISIONS + '<forward><duration>7</duration>'
                                          '</forward>'))
    out = fill_region_measures(xml, (SlashRegion("P1", 1, 2, 1.0),))
    notes = ET.fromstring(out).find("part").find("measure").findall("note")
    assert len(notes) == 1
    assert notes[0].get("id") == f"{FILL_ID_PREFIX}P1-m1-0"
    assert notes[0].findtext("duration") == "7"


def test_a_bar_repeat_region_is_still_filled_whole_bar() -> None:
    """A % is centred in its bar, so it needs the keep-alive note and
    nothing more — splitting it would only change the spacing."""
    xml = _score(_measure(1, _DIVISIONS + '<forward><duration>16</duration>'
                                          '</forward>'))
    out = fill_region_measures(xml, (), (RepeatRegion("P1", 1, 2),))
    notes = ET.fromstring(out).find("part").find("measure").findall("note")
    assert len(notes) == 1
    assert notes[0].get("id") == f"{FILL_ID_PREFIX}P1-m1-0"
    assert notes[0].findtext("duration") == "16"


def test_divisions_carry_forward_into_a_later_region_measure() -> None:
    """<divisions> is stated once, usually in bar 1, and a region bar
    further on does not restate it — reading it per measure would make
    the split silently wrong there."""
    xml = _score(_measure(1, _DIVISIONS) + _measure(2))
    out = fill_region_measures(xml, (SlashRegion("P1", 2, 3, 1.0),))
    m2 = ET.fromstring(out).find("part").findall("measure")[1]
    assert [n.findtext("duration") for n in m2.findall("note")] == \
        ["4", "4", "4", "4"]


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


def test_a_one_beat_bar_still_gets_the_slash_name() -> None:
    """A 1/4 bar splits into exactly one note. It must still carry the
    slash name, or synthesis would not find it and would fall back to
    centring the single slash in the bar."""
    xml = _score(_measure(1, _DIVISIONS + '<forward><duration>4</duration>'
                                          '</forward>'))
    out = fill_region_measures(xml, (SlashRegion("P1", 1, 2, 1.0),))
    notes = ET.fromstring(out).find("part").find("measure").findall("note")
    assert len(notes) == 1
    assert notes[0].get("id") == slash_fill_id("P1", 1, 0)
