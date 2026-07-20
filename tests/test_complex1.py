"""Phase 11 milestone fixture: testdata/complex1.musicxml loads, joins,
and pins the Dorico-robustness features (tremolo, mRest ledger tier, the
grace-note join gap, notation coverage). Grows across tasks 11.2/11.3/11.5.
"""

from collections import Counter

from scoreanim.core.animation import TINTED_KINDS, is_animated
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio_adapter import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.join import join_notes

from .conftest import COMPLEX1_SCORE


# The 22 layout notes the join cannot match: the PRINCIPAL notes carrying
# complex1's grace notes. Verovio's timemap delays each principal by the
# grace duration (+0.0957 q) while music21 keeps the notated beat, so the
# exact-onset key misses. Fixed by the Phase 12.1 order-based join rewrite
# — pinned here so that fix (or any regression) moves a known number. The
# graces THEMSELVES all match via join.py's onset-excluded grace tier.
_GRACE_DELAYED_PRINCIPALS = frozenset({
    "P1:m8:s1:v1:note:1",
    "P2:m8:s1:v2:note:1", "P2:m9:s1:v2:note:1", "P2:m10:s1:v2:note:1",
    "P3:m8:s1:v1:note:1", "P3:m9:s1:v1:note:1", "P3:m10:s1:v1:note:1",
    "P4:m8:s1:v1:note:1", "P4:m9:s1:v1:note:1", "P4:m10:s1:v1:note:1",
    "P7:m8:s1:v1:note:2", "P7:m8:s1:v1:note:3",
    "P7:m9:s1:v1:note:2", "P7:m9:s1:v1:note:3",
    "P7:m10:s1:v1:note:2", "P7:m10:s1:v1:note:3",
    "P10:m14:s1:v1:note:1", "P10:m14:s1:v2:note:1",
    "P11:m14:s1:v1:note:1", "P11:m14:s1:v2:note:1",
    "P12:m14:s1:v1:note:1", "P12:m14:s1:v2:note:1",
})


# --- 11.2 mRest ledger tier ------------------------------------------------

def test_mrest_ledger_dash_carries_the_rest_onset_and_voice(engraved_complex1):
    """complex1 p3 m13 staff 8 is a two-voice measure whose whole-bar rest
    is displaced above the staff onto a ledger dash at x=1277; the rest
    tier claims it, so the dash inherits the mRest's (onset, voice)."""
    dashes = [e for e in engraved_complex1.layout.elements
              if e.identity.kind is ElementKind.LEDGER_LINES
              and e.page == 3 and abs(e.bbox.x - 1277) < 3]
    assert dashes                                    # the dash exists
    for d in dashes:
        assert d.identity.onset is not None          # attributed, not orphaned
        assert d.identity.voice is not None


def test_complex1_staff_lines_are_exactly_five_paths(engraved_complex1):
    """The tremolo stroke emits its own element (11.1), so no staff's
    scaffold gains a 6th primitive (the container-shim misattribution)."""
    for e in engraved_complex1.layout.elements:
        if e.identity.kind is ElementKind.STAFF_LINES:
            assert len(e.glyph.paths) == 5


# --- 11.3 join gap pinned (not fixed — Phase 12.1) -------------------------

def test_join_is_899_of_921(engraved_complex1, complex1_score_model):
    report = join_notes(complex1_score_model, engraved_complex1.note_records)
    assert len(complex1_score_model.notes) == 921
    assert len(engraved_complex1.note_records) == 921
    assert len(report.matched) == 899
    assert len(report.unmatched_score) == 22
    assert len(report.unmatched_layout) == 22


def test_every_grace_note_matches(engraved_complex1, complex1_score_model):
    """The 26 graces themselves all join (the onset-excluded grace tier);
    the gap is the principals, not the graces (spike correction)."""
    graces = [n for n in complex1_score_model.notes if n.grace]
    assert len(graces) == 26
    report = join_notes(complex1_score_model, engraved_complex1.note_records)
    matched_graces = sum(1 for _, n in report.matched if n.grace)
    assert matched_graces == 26
    # nothing unmatched is itself a grace
    assert not any(n.grace for n in report.unmatched_score)
    assert not any(r.grace for r in report.unmatched_layout)


def test_unmatched_are_exactly_the_grace_delayed_principals(
        engraved_complex1, complex1_score_model):
    report = join_notes(complex1_score_model, engraved_complex1.note_records)
    unmatched_ids = {str(r.element_id) for r in report.unmatched_layout}
    assert unmatched_ids == _GRACE_DELAYED_PRINCIPALS

    # each unmatched pair (paired by part/measure/document order) is the
    # same pitch off by exactly one grace step (+0.0957 q)
    s_un = sorted(report.unmatched_score,
                  key=lambda n: (str(n.part), n.measure, n.order))
    l_un = sorted(report.unmatched_layout,
                  key=lambda r: (str(r.part), r.measure, r.order_in_voice))
    deltas = set()
    for n, r in zip(s_un, l_un):
        assert (n.pitch_step, n.octave) == (r.pitch_step, r.octave)
        deltas.add(round(r.onset - n.onset, 4))
    assert deltas == {0.0957}


# --- 11.5 census + notation coverage ---------------------------------------

def test_complex1_census(engraved_complex1):
    assert len(engraved_complex1.layout.elements) == 3491
    assert len(engraved_complex1.layout.pages) == 3
    assert len(engraved_complex1.note_records) == 921
    assert Counter(w.code for w in engraved_complex1.warnings) == \
        {"dropped-spanner": 3}


def test_complex1_tremolo_element_animates_untinted(engraved_complex1):
    """The one bowed tremolo emits a TREMOLO element carrying its note's
    onset (ruling a): it animates but does not tint."""
    trem = [e for e in engraved_complex1.layout.elements
            if e.identity.kind is ElementKind.TREMOLO]
    assert len(trem) == 1
    (t,) = trem
    assert t.identity.onset == 24.0
    assert is_animated(t.identity)
    assert ElementKind.TREMOLO not in TINTED_KINDS


def test_complex1_has_unpitched_percussion(engraved_complex1):
    # unpitched notes join by staff position, not pitch
    unpitched = [r for r in engraved_complex1.note_records
                 if r.pitch_step is None]
    assert unpitched
    assert all(r.staff_loc is not None for r in unpitched)


# --- animation-timing fixes (2026-07-20): decorations light with their note

def test_tuplet_bracket_lights_with_its_first_note_not_the_downbeat(
        engraved_complex1):
    """A tuplet bracket/number decorates the notes under it, so it must
    carry the tuplet's FIRST note onset — not the measure start (the
    animate-everything measure-start fallback would fire it at the
    downbeat, before the triplet). P11 m7's triplet starts at beat 26.0
    in a bar that begins at 24.0."""
    tuplet_other = [e for e in engraved_complex1.layout.elements
                    if e.identity.part == "P11"
                    and ":m7:" in str(e.identity.element_id)
                    and e.identity.kind is ElementKind.OTHER]
    assert tuplet_other                          # tupletNum + tupletBracket
    for e in tuplet_other:
        assert e.identity.onset == 26.0          # the first triplet note
        assert e.identity.onset != 24.0          # NOT the measure downbeat


def test_no_tuplet_decoration_falls_to_the_measure_start(engraved_complex1):
    """Across the whole score, every tuplet decoration (OTHER) shares an
    onset with a real note in its measure — never a bare measure start
    with no note there."""
    # collect note onsets per measure token
    note_onsets = {}
    for e in engraved_complex1.layout.elements:
        if e.identity.kind is ElementKind.NOTEHEAD and e.identity.onset is not None:
            eid = str(e.identity.element_id)
            token = eid.split(":note:")[0]       # part:mN:sN:vN
            note_onsets.setdefault(token, set()).add(e.identity.onset)
    for e in engraved_complex1.layout.elements:
        if e.identity.kind is ElementKind.OTHER and e.identity.onset is not None:
            token = str(e.identity.element_id).rsplit(":other:", 1)[0]
            onsets = note_onsets.get(token, set())
            assert e.identity.onset in onsets, str(e.identity.element_id)


def test_no_spanner_got_a_measure_start_fallback_onset(engraved_complex1):
    """A slur/tie/hairpin's timing is its start note or nothing — it must
    never fall to the measure-start fallback (which would animate it at a
    spurious downbeat). Signature of the bug: onset set but extent None."""
    from scoreanim.core.animation import REVEALED_KINDS
    for e in engraved_complex1.layout.elements:
        if e.identity.kind in REVEALED_KINDS and e.identity.onset is not None:
            assert e.identity.extent is not None, str(e.identity.element_id)


def test_complex1_reload_is_deterministic(engraved_complex1):
    again = VerovioEngravingProvider().load_detailed(COMPLEX1_SCORE,
                                                     EngravingParams())
    ids_a = [str(e.identity.element_id)
             for e in engraved_complex1.layout.elements]
    ids_b = [str(e.identity.element_id) for e in again.layout.elements]
    assert ids_a == ids_b
