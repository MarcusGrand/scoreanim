"""Phase 11.1 decomposer/geometry coverage: bTrem/fTrem emit their own
element (the stroke is never folded into the static staff scaffold),
beamSpan resolves onset/extent from @startid/@endid, and rotate
transforms flow through the walk (corner-mapped bboxes). Each class is
pinned synthetically — the SYSTEM_DIVIDER precedent — so coverage does
not depend on which fixture happens to draw the shape."""

from collections import defaultdict

import pytest

from scoreanim.core.animation import ANIMATED_KINDS, TINTED_KINDS, is_animated
from scoreanim.core.engraving.verovio_adapter import (_LoadState, _MeiIndex,
                                                      _PageDecomposer,
                                                      _identity_for)
from scoreanim.core.score.identity import ElementKind


def _page(inner: str) -> str:
    """Wrap decomposer-ready inner SVG in the definition-scale envelope
    (outer:inner viewBox = 1:10, so page-unit coords scale by 0.1)."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2096 2967">'
        '<svg viewBox="0 0 20960 29670" class="definition-scale">'
        '<g class="page-margin" transform="translate(50, 50)">'
        '<g class="system" xml:id="s1">'
        '<g class="measure" xml:id="m1">'
        f'{inner}'
        '</g></g></g></svg></svg>')


# --- tremolo ---------------------------------------------------------------

def test_tremolo_is_animated_but_untinted():
    # ruling (a): the tremolo stroke lights with its note but keeps the
    # part color off (tint scope unchanged)
    assert ElementKind.TREMOLO in ANIMATED_KINDS
    assert ElementKind.TREMOLO not in TINTED_KINDS


def test_btrem_emits_its_own_element_claiming_the_stroke():
    """The stroke <path> is a DIRECT child of bTrem; a container treatment
    would orphan it into the staff scaffold (the BACKLOG-6 shape). bTrem
    must emit and claim the stroke, while the nested note stays separate
    and carries the tremolo's onset (chord-member style)."""
    svg = _page(
        '<g class="bTrem" xml:id="bt1">'
        '<path d="M0 0 L200 0 L200 40 L0 40 Z"/>'          # the stroke
        '<g class="note" xml:id="n1">'
        '<path d="M0 100 L80 100 L80 160 L0 160 Z"/></g>'
        '</g>')
    st = _LoadState(prep=None,
                    mei=_MeiIndex(measure_by_id={"m1": 1},
                                  tremolo_note_ids={"bt1": ("n1",)}),
                    onset_by_id={"n1": 4.0},
                    measure_start={1: 0.0}, measure_duration={1: 4.0},
                    staff_n_by_id={}, layer_n_by_id={})
    accs = _PageDecomposer(svg, page=1, adapter=st).run()
    kinds = {a.kind for a in accs}
    trem = [a for a in accs if a.kind is ElementKind.TREMOLO]
    note = [a for a in accs if a.kind is ElementKind.NOTEHEAD]
    assert len(trem) == 1 and len(note) == 1
    (t,) = trem
    assert len(t.paths) == 1                                # stroke only
    assert ElementKind.STAFF_LINES not in kinds            # not folded away
    ident = _identity_for(t, page=1, st=st, counters=defaultdict(int))
    assert ident.kind is ElementKind.TREMOLO
    assert ident.onset == 4.0                              # inherited
    assert str(ident.element_id) == "score:m1:tremolo:0"
    assert is_animated(ident)


def test_ftrem_maps_to_tremolo_defensively():
    # fTrem occurs in neither fixture; cover it synthetically
    svg = _page(
        '<g class="fTrem" xml:id="ft1">'
        '<path d="M0 0 L200 0 L200 40 L0 40 Z"/>'
        '<g class="note" xml:id="n1">'
        '<path d="M0 100 L80 100 L80 160 L0 160 Z"/></g>'
        '</g>')
    st = _LoadState(prep=None,
                    mei=_MeiIndex(measure_by_id={"m1": 1},
                                  tremolo_note_ids={"ft1": ("n1",)}),
                    onset_by_id={"n1": 2.5},
                    measure_start={1: 0.0}, measure_duration={1: 4.0},
                    staff_n_by_id={}, layer_n_by_id={})
    accs = _PageDecomposer(svg, page=1, adapter=st).run()
    trem = [a for a in accs if a.kind is ElementKind.TREMOLO]
    assert len(trem) == 1
    ident = _identity_for(trem[0], page=1, st=st, counters=defaultdict(int))
    assert ident.onset == 2.5


# --- beamSpan --------------------------------------------------------------

def test_beamspan_emits_beam_with_onset_from_start_end():
    """A beamSpan is id-bearing with direct polygon children; its
    onset/extent come from @startid/@endid (not the layer-beam table)."""
    svg = _page(
        '<g class="beamSpan" xml:id="bs1">'
        '<polygon points="0,0 300,20 300,60 0,40"/>'
        '<polygon points="0,80 300,100 300,140 0,120"/>'
        '</g>')
    st = _LoadState(prep=None,
                    mei=_MeiIndex(measure_by_id={"m1": 1},
                                  beamspan_ends={"bs1": ("a", "b")}),
                    onset_by_id={"a": 2.0, "b": 5.0},
                    measure_start={1: 0.0}, measure_duration={1: 4.0},
                    staff_n_by_id={}, layer_n_by_id={})
    accs = _PageDecomposer(svg, page=1, adapter=st).run()
    beams = [a for a in accs if a.kind is ElementKind.BEAM]
    assert len(beams) == 1
    (b,) = beams
    assert len(b.paths) == 2
    ident = _identity_for(b, page=1, st=st, counters=defaultdict(int))
    assert ident.onset == 2.0
    assert ident.extent == (2.0, 5.0)
    assert str(ident.element_id) == "score:m1:beam:0"
    assert is_animated(ident)


# --- rotate ----------------------------------------------------------------

def test_rotate_transform_flows_through_the_walk():
    """A rotate(-90 …) on an emitting group no longer crashes the walk;
    the bbox is corner-mapped, so a wide glyph becomes tall (Verovio's
    vertical text)."""
    svg = _page(
        '<g class="note" xml:id="n1" transform="rotate(-90 500 500)">'
        '<path d="M0 0 L1000 0 L1000 100 L0 100 Z"/></g>')
    st = _LoadState(prep=None,
                    mei=_MeiIndex(measure_by_id={"m1": 1}),
                    onset_by_id={"n1": 1.0},
                    measure_start={1: 0.0}, measure_duration={1: 4.0},
                    staff_n_by_id={}, layer_n_by_id={})
    accs = _PageDecomposer(svg, page=1, adapter=st).run()
    (acc,) = accs
    assert acc.bbox is not None
    # the 1000x100 rect rotated -90 becomes 100x1000 (taller than wide)
    assert acc.bbox.h > acc.bbox.w


# --- 11.4 graceful degradation ---------------------------------------------

def _unknown_class_page() -> str:
    return _page(
        '<g class="mysteryGlyph" xml:id="u1">'
        '<path d="M0 0 L100 0 L100 40 L0 40 Z"/></g>')


def test_unknown_class_raises_in_strict_mode():
    st = _LoadState(prep=None, mei=_MeiIndex(measure_by_id={"m1": 1}),
                    onset_by_id={}, measure_start={1: 0.0},
                    measure_duration={1: 4.0}, staff_n_by_id={},
                    layer_n_by_id={}, strict=True)
    with pytest.raises(ValueError, match="unknown SVG class 'mysteryGlyph'"):
        _PageDecomposer(_unknown_class_page(), page=1, adapter=st).run()


def test_unknown_class_degrades_to_other_element_in_app_mode():
    st = _LoadState(prep=None, mei=_MeiIndex(measure_by_id={"m1": 1}),
                    onset_by_id={}, measure_start={1: 0.0},
                    measure_duration={1: 4.0}, staff_n_by_id={},
                    layer_n_by_id={}, strict=False)
    accs = _PageDecomposer(_unknown_class_page(), page=1, adapter=st).run()
    (acc,) = accs
    assert acc.kind is ElementKind.OTHER
    assert len(acc.paths) == 1                          # drawable claimed
    ident = _identity_for(acc, page=1, st=st, counters=defaultdict(int))
    # animate-everything (ruling 2026-07-20): the degraded element is not
    # scaffold, so it resolves a measure-start onset and animates
    assert ident.onset == 0.0
    assert is_animated(ident)
    assert [w.code for w in st.warnings] == ["unknown-class"]
    assert "mysteryGlyph" in st.warnings[0].message


def test_no_known_fixture_degrades(engraved, engraved_spanners,
                                   engraved_video, engraved_complex1):
    # after 11.1 no permanent fixture carries an unknown drawable class
    for score in (engraved, engraved_spanners, engraved_video,
                  engraved_complex1):
        assert not [w for w in score.warnings if w.code == "unknown-class"]
