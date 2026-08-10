"""Per-system staff hides (2026-08-10): the pure strip and the whole
pipeline. The mechanism is the region fill run backwards — an
overridden staff's non-sounding measures are blanked at the Verovio
seam so optimize hides it for exactly that system.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.engraving.verovio.system_hides import (
    strip_hidden_staves, system_spans)
from scoreanim.core.score.identity import ElementKind
from tests.conftest import TESTSCORE


# --- pure half -------------------------------------------------------------

def _score(*parts: str) -> str:
    ids = "".join(f'<score-part id="P{i+1}"/>' for i in range(len(parts)))
    body = "".join(f'<part id="P{i+1}">{p}</part>'
                   for i, p in enumerate(parts))
    return f"<score-partwise><part-list>{ids}</part-list>{body}</score-partwise>"


def _m(n: int, body: str, new_system: bool = False) -> str:
    pr = '<print new-system="yes"/>' if new_system else ""
    return f'<measure number="{n}">{pr}{body}</measure>'


NOTE = ('<note><pitch><step>C</step><octave>4</octave></pitch>'
        '<duration>16</duration><voice>1</voice></note>')
REST = ('<note><rest/><duration>16</duration><voice>1</voice></note>')
FWD = '<forward><duration>16</duration></forward>'
FILL = ('<note print-object="no" id="scoreanim-fill-P1-m2-0">'
        '<pitch><step>B</step><octave>4</octave></pitch>'
        '<duration>16</duration><voice>1</voice></note>')


def test_system_spans_read_the_first_parts_breaks() -> None:
    xml = _score(_m(1, NOTE) + _m(2, NOTE) + _m(3, NOTE, new_system=True)
                 + _m(4, NOTE))
    assert system_spans(ET.fromstring(xml)) == {1: (1, 3), 3: (3, 5)}


def test_strip_blanks_rests_and_forwards_but_never_notes() -> None:
    xml = _score(_m(1, REST) + _m(2, FWD) + _m(3, NOTE, new_system=True))
    out, report = strip_hidden_staves(xml, {1: frozenset({"P1"})})
    root = ET.fromstring(out)
    m1, m2, _ = root.find("part").findall("measure")
    assert m1.find("note") is None                # the rest is gone
    assert m1.findtext("forward/duration") == "16"   # duration held
    assert m2.findtext("forward/duration") == "16"
    assert report.stripped == (("P1", 1), ("P1", 2))
    assert report.kept == () and report.inert == ()


def test_strip_keeps_a_sounding_measure_and_reports_it() -> None:
    xml = _score(_m(1, REST) + _m(2, NOTE))
    out, report = strip_hidden_staves(xml, {1: frozenset({"P1"})})
    root = ET.fromstring(out)
    _, m2 = root.find("part").findall("measure")
    assert m2.find("note/pitch") is not None      # untouched
    assert report.kept == ((1, "P1"),)
    assert report.stripped == (("P1", 1),)


def test_a_region_fill_note_is_not_a_sounding_note() -> None:
    """The strip runs AFTER the fill, so the invisible keep-alive note
    must strip back out or a hidden slash staff could never hide."""
    xml = _score(_m(1, FILL))
    out, report = strip_hidden_staves(xml, {1: frozenset({"P1"})})
    assert ET.fromstring(out).find("part/measure/note") is None
    assert report.stripped == (("P1", 1),)


def test_an_ordinal_starting_no_system_is_inert() -> None:
    xml = _score(_m(1, REST) + _m(2, REST))
    out, report = strip_hidden_staves(xml, {2: frozenset({"P1"})})
    assert out is xml
    assert report.inert == (2,)


def test_attributes_prints_and_barlines_survive() -> None:
    body = ('<attributes><divisions>4</divisions></attributes>' + REST
            + '<barline location="right"><bar-style>light-light'
              '</bar-style></barline>')
    xml = _score(_m(1, body))
    out, _ = strip_hidden_staves(xml, {1: frozenset({"P1"})})
    m1 = ET.fromstring(out).find("part/measure")
    assert m1.find("attributes") is not None
    assert m1.find("barline") is not None


# --- pipeline half ---------------------------------------------------------

@pytest.fixture(scope="module")
def hidden_sys2():
    # system 2 of testscore is mm5-8, where P7 (Drum Set) is all
    # slashes — the exact staff Marcus wants to hide by hand
    return VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), hide_empty_staves=True, strict=False,
        system_staff_hides={5: frozenset({"P7"})})


def _parts_by_system(engraved) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for e in engraved.layout.elements:
        if e.identity.kind is ElementKind.STAFF_LINES:
            out.setdefault(e.system, set()).add(str(e.identity.part))
    return out


def test_the_staff_hides_in_that_system_only(hidden_sys2) -> None:
    by_system = _parts_by_system(hidden_sys2)
    assert "P7" not in by_system[2]
    assert "P7" in by_system[1] and "P7" in by_system[3]
    codes = {w.code for w in hidden_sys2.warnings}
    assert not codes & {"hide-unavailable", "staff-hide-inert",
                        "staff-hide-kept-notes"}


def test_the_hidden_systems_slashes_go_with_it(hidden_sys2) -> None:
    slash_systems = {e.system for e in hidden_sys2.layout.elements
                     if e.identity.kind is ElementKind.SLASH}
    assert 2 not in slash_systems
    assert {1, 3, 4, 5} <= slash_systems


def test_musical_content_is_untouched(engraved, hidden_sys2) -> None:
    assert sorted(str(r.element_id) for r in hidden_sys2.note_records) \
        == sorted(str(r.element_id) for r in engraved.note_records)


def test_a_sounding_staff_stays_and_warns() -> None:
    out = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), hide_empty_staves=True, strict=False,
        system_staff_hides={1: frozenset({"P1"})})
    assert "P1" in _parts_by_system(out)[1]
    warning = next(w for w in out.warnings
                   if w.code == "staff-hide-kept-notes")
    assert "P1" in warning.message


def test_a_stale_ordinal_warns_inert() -> None:
    out = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), hide_empty_staves=True, strict=False,
        system_staff_hides={999: frozenset({"P7"})})
    warning = next(w for w in out.warnings if w.code == "staff-hide-inert")
    assert "999" in warning.message


def test_hides_are_ignored_without_global_hiding() -> None:
    out = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), strict=False,
        system_staff_hides={5: frozenset({"P7"})})
    assert "P7" in _parts_by_system(out)[2]
    assert any(w.code == "staff-hide-ignored" for w in out.warnings)
