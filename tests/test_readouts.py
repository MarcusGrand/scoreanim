"""ui/readouts.py — pure readout helpers (M1.1). Headless: the module
is Qt-free, so these run with plain pytest, no display server."""

from scoreanim.core.project import DEFAULT_BPM, ProjectDoc
from scoreanim.core.project.document import TimingConfig
from scoreanim.core.timing import TempoEvent
from scoreanim.core.timing.swing import SwingRegion
from scoreanim.core.project import MoveTempoEvent, SetTempoFrom
from scoreanim.ui.readouts import (format_time, global_swing_ratio,
                                   initial_tempo_event, tempo_command)


def _doc(**timing_kwargs) -> ProjectDoc:
    return ProjectDoc(timing=TimingConfig(**timing_kwargs))


# -- format_time ---------------------------------------------------------------

def test_format_time_zero():
    assert format_time(0.0) == "0:00.0"


def test_format_time_negative_clamps_to_zero():
    assert format_time(-3.7) == "0:00.0"


def test_format_time_typical():
    assert format_time(83.25) == "1:23.2"


def test_format_time_hourish_stays_minutes():
    # no h:mm:ss rollover — minutes keep counting (61:05.0)
    assert format_time(3665.04) == "61:05.0"


# -- initial_tempo_event -------------------------------------------------------

def test_initial_tempo_event_empty_is_none():
    assert initial_tempo_event(_doc(tempo_events=())) is None
    # the window's display falls back to DEFAULT_BPM in that case
    assert DEFAULT_BPM == 120.0


def test_initial_tempo_event_picks_earliest_position():
    events = (TempoEvent(8.0, 90.0), TempoEvent(0.0, 120.0),
              TempoEvent(4.0, 140.0))
    first = initial_tempo_event(_doc(tempo_events=events))
    assert first == TempoEvent(0.0, 120.0)


def test_initial_tempo_event_default_doc():
    first = initial_tempo_event(ProjectDoc())
    assert first is not None and first.bpm == DEFAULT_BPM


# -- global_swing_ratio --------------------------------------------------------

def test_swing_no_regions_is_straight():
    assert global_swing_ratio(_doc(swing_regions=())) == 0.5


def test_swing_multi_region_shows_first_ratio():
    regions = (SwingRegion(span=(0.0, 8.0), ratio=0.667),
               SwingRegion(span=(8.0, 16.0), ratio=0.55))
    assert global_swing_ratio(_doc(swing_regions=regions)) == 0.667


# -- tempo_command -------------------------------------------------------------
#
# What the Tempo field MEANS by a bpm, as opposed to what tempo_scope says
# it is showing. The field previews with this and commits with it, so the
# two calls cannot ask for different edits.

def test_tempo_command_with_no_selection_moves_the_first_event():
    events = (TempoEvent(0.0, 120.0), TempoEvent(8.0, 90.0))
    command = tempo_command(_doc(tempo_events=events), None, 96.0)
    # in place: only the bpm changes, so a later event survives
    assert command == MoveTempoEvent(0.0, 0.0, 96.0)


def test_tempo_command_with_a_selected_line_sets_from_there():
    command = tempo_command(ProjectDoc(), 8.0, 90.0)
    assert command == SetTempoFrom(8.0, 90.0)


def test_tempo_command_empty_map_has_nothing_to_edit():
    assert tempo_command(_doc(tempo_events=()), None, 96.0) is None
    # a selected line still does — SetTempoFrom writes its own event
    assert tempo_command(_doc(tempo_events=()), 8.0, 90.0) is not None
