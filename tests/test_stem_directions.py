"""Stem directions at the prep seam (2026-08-03).

Dorico exports the WRITTEN score's stem directions; we engrave concert
pitch (rule 9), so a transposing part arrives with stems on the wrong
side of its noteheads. `_normalize_stem_directions` drops `<stem>` on
single-voice staves and lets Verovio decide from the pitch it draws;
`_apply_stem_directions` writes the user's own flips back on top.

`spikes/stem_dirs.py` is the measurement behind both.
"""

import xml.etree.ElementTree as ET

import pytest

from scoreanim.core.animation.scale_groups import (group_key, heads_by_group,
                                                   stem_is_up)
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_prep import SystemBreak, prepare
from scoreanim.core.score.musicxml_stems import (StemDirection,
                                                 _apply_stem_directions,
                                                 _draws_a_stem, _note_events,
                                                 _normalize_stem_directions)

from .conftest import CONDENSE_SCORE, TALL_SYSTEM_SCORE, TESTSCORE


def _root(xml_text: str) -> ET.Element:
    return ET.fromstring(xml_text)


def _stems(root: ET.Element) -> list[str | None]:
    return [n.findtext("stem") for n in root.iter("note")]


def _measure(*notes: str) -> ET.Element:
    """A one-part score whose single measure holds the given notes,
    each spelled "voice/staff/type[/stem]"."""
    root = ET.fromstring('<score-partwise><part id="P1">'
                         '<measure number="1"/></part></score-partwise>')
    measure = root.find("part/measure")
    for spec in notes:
        bits = spec.split("/")
        note = ET.SubElement(measure, "note")
        if bits[2] == "rest":
            ET.SubElement(note, "rest")
        else:
            pitch = ET.SubElement(note, "pitch")
            ET.SubElement(pitch, "step").text = "C"
            ET.SubElement(pitch, "octave").text = "4"
            ET.SubElement(note, "type").text = bits[2]
        ET.SubElement(note, "voice").text = bits[0]
        ET.SubElement(note, "staff").text = bits[1]
        if len(bits) > 3:
            ET.SubElement(note, "stem").text = bits[3]
    return root


# --- the normalize pass ----------------------------------------------------

def test_a_single_voice_staff_loses_its_encoded_stems():
    root = _measure("1/1/quarter/down", "1/1/quarter/down")
    assert _normalize_stem_directions(root) == 2
    assert _stems(root) == [None, None]


def test_a_two_voice_staff_is_left_exactly_as_encoded():
    """Marcus's call: Dorico generally gets these right, and forcing a
    direction here would overrule real divisi."""
    root = _measure("1/1/quarter/up", "2/1/quarter/up")
    assert _normalize_stem_directions(root) == 0
    assert _stems(root) == ["up", "up"]


def test_each_staff_of_a_part_is_judged_on_its_own():
    """A grand staff with one voice on top and two below: the top staff
    is normalized, the bottom is not."""
    root = _measure("1/1/quarter/down",
                    "2/2/quarter/up", "3/2/quarter/down")
    assert _normalize_stem_directions(root) == 1
    assert _stems(root) == [None, "up", "down"]


def test_rests_do_not_make_a_staff_multi_voice():
    """A voice that only rests in this measure is not a second voice on
    the page — the staff still reads as one."""
    root = _measure("1/1/quarter/down", "2/1/rest")
    assert _normalize_stem_directions(root) == 1
    assert _stems(root) == [None, None]


def test_stem_none_survives_the_strip():
    """`<stem>none</stem>` is not a direction, it is "this note has no
    stem". Stripping it would grow a stem the score says is not there."""
    root = _measure("1/1/quarter/none", "1/1/quarter/down")
    assert _normalize_stem_directions(root) == 1
    assert _stems(root) == ["none", None]


def test_the_pass_runs_in_prepare_over_a_real_fixture():
    prepared = prepare(TESTSCORE)
    root = _root(prepared.canonical_xml)
    raw = _root(TESTSCORE.read_bytes().decode())
    assert sum(1 for _ in raw.iter("stem")) == 500        # as Dorico wrote it
    # most are gone; what survives is the multi-voice staves and <stem>none
    survivors = [s.text for s in root.iter("stem")]
    assert len(survivors) < 200
    assert set(survivors) <= {"up", "down", "none"}


# --- the convention actually holds afterwards ------------------------------

def _wrong_way_stems(engraved) -> tuple[int, int]:
    """(stems checked, stems pointing the wrong way), over exactly the
    population the pass claims to fix: unbeamed, non-grace notes on a
    staff carrying one voice in that measure. `spikes/stem_dirs.py` is
    where this oracle comes from, and where it is calibrated.

    Beamed groups are out because the GROUP owns the direction, so a
    member legitimately sits the wrong side of the line. Multi-voice
    staves are out because we deliberately leave those as encoded.

    Purely geometric — y grows downward, so a head BELOW the middle
    line wants an up stem. No pitch, clef or transposition arithmetic.
    """
    root = _root(engraved.prepared.canonical_xml)

    # which (part, measure, staff) carry one voice, and which events are
    # beamed — both read off the same XML the engrave saw
    voices: dict[tuple, set] = {}
    plain: dict[tuple, list[bool]] = {}
    for part in root.findall("part"):
        pid = part.get("id", "")
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            for event in _note_events(measure):
                lead = event[0]
                staff = int(lead.findtext("staff", "1"))
                voice = int(lead.findtext("voice", "1"))
                voices.setdefault((pid, ordinal, staff), set()).add(voice)
                if _draws_a_stem(event):
                    plain.setdefault((pid, ordinal, staff, voice), []).append(
                        not any(n.find("beam") is not None
                                or n.find("grace") is not None
                                for n in event))

    heads = heads_by_group(engraved.layout)
    middles = {}
    for el in engraved.layout.elements:
        i = el.identity
        if i.kind is ElementKind.STAFF_LINES and i.part is not None:
            middles[(i.part, i.staff, el.page, el.system)] = el.bbox.center.y

    checked = wrong = 0
    for el in engraved.layout.elements:
        i = el.identity
        eid = str(i.element_id)
        if i.kind is not ElementKind.STEM or i.part is None or ":seg" in eid:
            continue
        ordinal = int(eid.split(":")[1][1:])
        seq = int(eid.split(":")[-1])
        if len(voices.get((i.part, ordinal, i.staff), ())) != 1:
            continue
        flags = plain.get((i.part, ordinal, i.staff, i.voice), [])
        if seq >= len(flags) or not flags[seq]:
            continue                       # beamed, grace, or unmatched
        group = heads.get(group_key(i))
        mid = middles.get((i.part, i.staff, el.page, el.system))
        if not group or mid is None:
            continue
        far = max(group, key=lambda h: abs(h.bbox.center.y - mid))
        offset = far.bbox.center.y - mid
        if abs(offset) < 1e-6:
            continue                       # on the line: Verovio's call
        checked += 1
        wrong += int(stem_is_up(el, group) != (offset > 0))
    return checked, wrong


@pytest.mark.parametrize("fixture", ["engraved", "engraved_video",
                                     "engraved_complex1"])
def test_the_normalized_render_follows_the_convention(fixture, request):
    """The whole point of the feature. As Dorico exported them these
    fixtures scored 77.2 %, 65.7 % and 86.7 % (spikes/stem_dirs.py);
    through the seam every one of these stems points the right way."""
    checked, wrong = _wrong_way_stems(request.getfixturevalue(fixture))
    assert checked > 50, "oracle matched nothing — the test would be vacuous"
    assert wrong == 0


def test_the_oracle_can_actually_fail(engraved):
    """Non-vacuity guard for the test above: flip every stem in the
    document and the same oracle must condemn nearly all of them. A
    check that cannot fail pins nothing (PATTERNS' vacuous-pin trap)."""
    directions = {eid: StemDirection("down" if drawn == "up" else "up")
                  for eid, drawn in _drawn_directions(engraved).items()}
    flipped = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), stem_directions=directions)
    checked, wrong = _wrong_way_stems(flipped)
    assert checked > 50 and wrong / checked > 0.9


# --- the flip pass ---------------------------------------------------------

def test_a_flip_writes_an_explicit_direction():
    root = _measure("1/1/quarter/down", "1/1/quarter/down")
    _normalize_stem_directions(root)
    inert = _apply_stem_directions(
        root, {"P1:m1:s1:v1:stem:1": StemDirection.UP})
    assert inert == ()
    assert _stems(root) == [None, "up"]


def test_a_flip_beats_the_strip_on_the_same_note():
    """The precedence the module states out loud: the user's flip is the
    last word on the note it names."""
    root = _measure("1/1/quarter/down")
    _normalize_stem_directions(root)
    _apply_stem_directions(root, {"P1:m1:s1:v1:stem:0": StemDirection.DOWN})
    assert _stems(root) == ["down"]


def test_a_chord_takes_one_direction_on_every_note():
    root = _measure("1/1/quarter", "1/1/quarter")
    ET.SubElement(root.findall("part/measure/note")[1], "chord")
    _apply_stem_directions(root, {"P1:m1:s1:v1:stem:0": StemDirection.UP})
    assert _stems(root) == ["up", "up"]


def test_a_stemless_note_consumes_no_sequence_number():
    """A whole note draws nothing, so the quarter after it is stem 0 —
    not stem 1. Get this wrong and every key past a whole note points
    one note too far (spike Q3)."""
    root = _measure("1/1/whole", "1/1/quarter")
    _apply_stem_directions(root, {"P1:m1:s1:v1:stem:0": StemDirection.UP})
    assert _stems(root) == [None, "up"]


def test_rests_consume_no_sequence_number():
    root = _measure("1/1/rest", "1/1/quarter")
    _apply_stem_directions(root, {"P1:m1:s1:v1:stem:0": StemDirection.DOWN})
    assert _stems(root) == [None, "down"]


@pytest.mark.parametrize("key", [
    "P1:m9:s1:v1:stem:0",          # no such measure
    "P1:m1:s1:v9:stem:0",          # no such voice
    "P9:m1:s1:v1:stem:0",          # no such part
    "P1:m1:s1:v1:stem:7",          # past the end of the measure
    "P1:m1:s1:v1:note:0",          # not a stem id at all
    "nonsense",
])
def test_a_key_that_cannot_land_is_reported_not_raised(key):
    root = _measure("1/1/quarter")
    assert _apply_stem_directions(root, {key: StemDirection.UP}) == (key,)
    assert _stems(root) == [None]


def test_no_directions_is_a_literal_no_op():
    root = _measure("1/1/quarter/down")
    before = ET.tostring(root)
    assert _apply_stem_directions(root, {}) == ()
    assert ET.tostring(root) == before


# --- the two passes against condensing -------------------------------------

def test_condensing_gets_verovio_s_own_two_voice_rule():
    """The reason normalize runs BEFORE condense. Each source player is
    single-voice, so its stems are stripped; after the merge Verovio
    sees two voices with no direction and applies its own voice-1-up /
    voice-2-down. Run it after and every condensed staff would keep
    what the file encoded."""
    from scoreanim.core.score.musicxml_prep import PartCondenseSpec
    spec = PartCondenseSpec(parts=("P1", "P2"), name="Flute 1.2")
    merged = _root(prepare(CONDENSE_SCORE, condense=(spec,)).canonical_xml)
    voices = {v.text for v in merged.iter("voice")}
    assert voices == {"1", "2"}                    # the merge did happen
    assert list(merged.iter("stem")) == []         # and carries no direction


def test_a_flip_is_keyed_to_the_condensed_voice():
    """Flips run after the merge, so a key naming voice 2 lands on the
    absorbed player — which only exists post-seam."""
    from scoreanim.core.score.musicxml_prep import PartCondenseSpec
    spec = PartCondenseSpec(parts=("P1", "P2"), name="Flute 1.2")
    prepared = prepare(CONDENSE_SCORE, condense=(spec,),
                       stem_directions={"P1:m1:s1:v2:stem:0":
                                        StemDirection.UP})
    assert prepared.inert_stem_directions == ()
    assert [s.text for s in _root(prepared.canonical_xml).iter("stem")] == ["up"]


# --- the helpers the key resolution rests on -------------------------------

def test_a_chord_is_one_note_event():
    root = _measure("1/1/quarter", "1/1/quarter", "1/1/quarter")
    for note in root.findall("part/measure/note")[1:]:
        ET.SubElement(note, "chord")
    events = _note_events(root.find("part/measure"))
    assert len(events) == 1 and len(events[0]) == 3


@pytest.mark.parametrize("type_, drawn", [
    ("quarter", True), ("eighth", True), ("half", True),
    ("whole", False), ("breve", False), ("long", False),
])
def test_which_note_values_draw_a_stem(type_, drawn):
    root = _measure(f"1/1/{type_}")
    assert _draws_a_stem(_note_events(root.find("part/measure"))[0]) is drawn


# --- end to end through Verovio --------------------------------------------

def _drawn_directions(engraved) -> dict[str, str]:
    heads = heads_by_group(engraved.layout)
    out = {}
    for el in engraved.layout.elements:
        i = el.identity
        if i.kind is not ElementKind.STEM:
            continue
        group = heads.get(group_key(i))
        if group:
            out[str(i.element_id)] = "up" if stem_is_up(el, group) else "down"
    return out


@pytest.fixture(scope="module")
def baseline_directions(engraved):
    return _drawn_directions(engraved)


def test_a_flip_moves_exactly_the_stem_it_names(baseline_directions):
    target, was = next(iter(sorted(baseline_directions.items())))
    want = "down" if was == "up" else "up"
    engraved = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(),
        stem_directions={target: StemDirection(want)})
    after = _drawn_directions(engraved)
    assert after[target] == want
    moved = [k for k, v in baseline_directions.items() if after.get(k) != v]
    assert moved == [target]


def test_a_stale_flip_warns_instead_of_failing_the_load():
    engraved = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(),
        stem_directions={"P1:m999:s1:v1:stem:0": StemDirection.UP})
    assert engraved.prepared.inert_stem_directions == ("P1:m999:s1:v1:stem:0",)
    assert any(w.code == "stem-flip-inert" for w in engraved.warnings)


# --- the retries must carry the flips (the M5.2 trap) ----------------------

def _flip_survives(path, **kw) -> None:
    """Load `path` with one stem flipped and assert it came out that
    way. `prepare()` runs up to three times per load, and a retry that
    forgets the map loses the user's edits exactly on the hardest
    scores — which is what happened to the break maps in M5.2."""
    provider = VerovioEngravingProvider()
    before = _drawn_directions(provider.load_detailed(path, EngravingParams(),
                                                      **kw))
    target, was = next(iter(sorted(before.items())))
    want = "down" if was == "up" else "up"
    after = provider.load_detailed(path, EngravingParams(),
                                   stem_directions={target:
                                                    StemDirection(want)},
                                   **kw)
    assert after.prepared.inert_stem_directions == ()
    assert _drawn_directions(after)[target] == want


def test_the_repagination_retry_carries_the_flips():
    """Forcing a break at 19 overflows the final system, so never-clip
    re-prepares — and that re-prepare has to pass the flips on."""
    forced = {19: SystemBreak.FORCE}
    engraved = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), system_breaks=forced)
    assert "repaginated" in {w.code for w in engraved.warnings}
    _flip_survives(TESTSCORE, system_breaks=forced)


def test_the_scale_to_fit_retry_carries_the_flips():
    """The deepest retry — tall_system_min re-prepares under a scale."""
    engraved = VerovioEngravingProvider().load_detailed(
        TALL_SYSTEM_SCORE, EngravingParams(), strict=False)
    assert "scaled-to-fit" in {w.code for w in engraved.warnings}
    _flip_survives(TALL_SYSTEM_SCORE, strict=False)


def test_the_hide_unavailable_retry_carries_the_flips(monkeypatch):
    """This retry re-uses the same prep rather than re-preparing, so the
    flips ride for free — pinned so it stays that way. The region fill
    (2026-08-09) keeps the fallback from firing on testscore at all,
    so this pin disables the fill to reach it."""
    from scoreanim.core.engraving.verovio import region_fill
    monkeypatch.setattr(region_fill, "fill_region_measures",
                        lambda xml, *regions: xml)
    engraved = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), hide_empty_staves=True)
    assert "hide-unavailable" in {w.code for w in engraved.warnings}
    _flip_survives(TESTSCORE, hide_empty_staves=True)
