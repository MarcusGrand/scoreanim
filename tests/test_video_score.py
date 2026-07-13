"""Phase 10 pins against testdata/video_test.musicxml — the real
production score whose loading failures drove the robustness phase
(multi-staff piano, displaced-rest ledger dashes, 3+-system tie
continuations, dropped ties, novel SVG classes). Root causes and
mechanism corrections: spikes/NOTES.md "Phase 10" +
spikes/video_test_triage.py."""

from collections import Counter

from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_prep import prepare

from .conftest import VIDEO_SCORE


# --- 10.1: multi-staff part model -----------------------------------------

def test_prep_part_geometry():
    prep = prepare(VIDEO_SCORE)
    assert [p.part_id for p in prep.parts] == \
        ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]
    p5 = prep.parts[4]
    assert (p5.staff_count, p5.first_staff) == (2, 5)
    assert [p.first_staff for p in prep.parts] == [1, 2, 3, 4, 5, 7, 8]
    assert prep.part_for_staff(5).part_id == "P5"
    assert prep.part_for_staff(6).part_id == "P5"
    assert prep.part_for_staff(7).part_id == "P6"


def test_score_model_builds_with_multi_staff_part(video_score_model):
    model = video_score_model
    assert model.parts == ("P1", "P2", "P3", "P4", "P5", "P6", "P7")
    assert len(model.measures) == 45


def test_piano_notes_carry_part_local_staff(video_score_model):
    prep = prepare(VIDEO_SCORE)
    count_by_part = {p.part_id: p.staff_count for p in prep.parts}
    # This chart's piano LEFT hand holds only rests and chord symbols —
    # its 9 music21 "notes" are all ChordSymbol (excluded from the
    # model), so every piano ScoreNote sits on staff 1. The grouped
    # consume itself is pinned by the PartStaff-id contract check in
    # build_score_model (a wrong order raises) plus the staff-2 REST
    # identities pinned adapter-side.
    p5_staves = {n.staff for n in video_score_model.notes if n.part == "P5"}
    assert p5_staves == {1}
    assert len([n for n in video_score_model.notes if n.part == "P5"]) > 0
    for n in video_score_model.notes:
        assert 1 <= n.staff <= count_by_part[n.part], \
            f"{n.part} note in m{n.measure} claims staff {n.staff}"
    # the parts AFTER the multi-staff slot are where a misaligned zip
    # would show: bass and drums must still own their notes
    parts_with_notes = {n.part for n in video_score_model.notes}
    assert {"P6", "P7"} <= parts_with_notes


def test_piano_staff_two_elements_mint_part_local_ids(engraved_video):
    # No noteheads live on the piano LH in this chart, but its scaffold
    # and whole-bar rests do — global staff 6 must mint as P5 staff 2.
    s2 = [e for e in engraved_video.layout.elements
          if e.identity.part == "P5" and e.identity.staff == 2]
    kinds = Counter(e.identity.kind for e in s2)
    assert kinds[ElementKind.MREST] == 45
    assert kinds[ElementKind.STAFF_LINES] == 45
    assert all(":s2:" in str(e.identity.element_id) for e in s2)


# --- 10.2: ledger-dash attribution (notehead tier, then rest tier) --------

def test_all_ledger_dashes_carry_onset_and_voice(engraved_video):
    ledgers = [e for e in engraved_video.layout.elements
               if e.identity.kind is ElementKind.LEDGER_LINES]
    assert len(ledgers) == 355
    assert all(e.identity.onset is not None and e.identity.voice is not None
               for e in ledgers)


def test_m12_dash_attributes_to_the_displaced_rest(engraved_video):
    # m12 staff 2 (Ten/Bari) is two-voice; the voice-1 half rest is
    # displaced off the staff and Verovio draws a ledger dash through it
    # (spikes/video_test_triage.py section C). The dash must inherit the
    # REST's (onset, voice) — no notehead overlaps it.
    els = {str(e.identity.element_id): e
           for e in engraved_video.layout.elements}
    dash = els["P2:m12:s1:v1:ledger_lines:2"]
    rest = els["P2:m12:s1:v1:rest:0"]
    assert rest.identity.onset == dash.identity.onset == 42.0
    assert dash.identity.voice == rest.identity.voice == 1
    assert abs(dash.x - rest.x) < rest.bbox.w  # it is that rest's dash


def test_staff_lines_are_exactly_five_paths(engraved_video):
    staves = [e for e in engraved_video.layout.elements
              if e.identity.kind is ElementKind.STAFF_LINES]
    assert len(staves) == 360                  # 8 staves × 45 measures
    assert {len(e.glyph.paths) for e in staves} == {5}


# --- 10.3: tie continuation reconciliation + load warnings ----------------

def test_load_completes_with_exactly_the_flagged_ties(engraved_video):
    codes = Counter(w.code for w in engraved_video.warnings)
    # 6 ties Verovio drops (5 open + 1 backwards cross-staff tie), 13
    # it force-matches to distant notes (suppressed, 10R.3 — they drew
    # as ovals around m44), and the flat layout repaginates (10R.4) —
    # all flagged, never silent (ruling b); no attribution mismatches.
    assert codes == {"dropped-spanner": 6, "implausible-tie": 13,
                     "repaginated": 1}


def test_tie_continuations_reconcile_via_end_system_rule(engraved_video):
    segs = [e for e in engraved_video.layout.elements
            if e.identity.kind is ElementKind.TIE
            and ":seg" in str(e.identity.element_id)]
    by_system = Counter(e.system for e in segs)
    # the spike's per-system drawn counts (section D), minus the
    # suppressed implausible ties' segments (10R.3): system 15's ink
    # was ENTIRELY bogus (the m44 ovals) and is gone
    assert by_system == {4: 6, 7: 4, 11: 10, 12: 9, 13: 12}
    # system 4: all six segments continue the six m7→m8 ties, extent
    # q29.5→q30.0
    assert {e.identity.extent for e in segs if e.system == 4} == \
        {(29.5, 30.0)}


def test_no_implausible_tie_ink_survives(engraved_video, video_score_model):
    # the m44 regression pin: every remaining tie (source or segment)
    # spans at most two of its start measure's durations, and the worst
    # offender's id is gone
    dur = {m.number: m.quarter_length for m in video_score_model.measures}
    start_measure = {m.number: m.start for m in video_score_model.measures}
    for e in engraved_video.layout.elements:
        if e.identity.kind is not ElementKind.TIE or not e.identity.extent:
            continue
        s, en = e.identity.extent
        m = max((n for n, q in start_measure.items() if q <= s),
                default=1)
        assert en - s <= 2.0 * dur[m], str(e.identity.element_id)
    ids = {str(e.identity.element_id) for e in engraved_video.layout.elements}
    assert "P3:m5:s1:v1:tie:2" not in ids          # the q17.5→q166 tie
    assert not any(i.startswith("P3:m5:s1:v1:tie:2:") for i in ids)


# --- 10R.2: animate everything except ruled statics ------------------------

def test_ornaments_and_texts_carry_attach_onsets(engraved_video):
    """Phase 10R ruling: fermatas, trills, texts, chord symbols animate
    at their attach point (@startid note / @tstamp arithmetic); only
    page furniture (labels, measure numbers, headers) and the systemic
    scaffold stay onset-less."""
    els = engraved_video.layout.elements
    # the final-bar fermatas are measure-attached (v0), unlike the
    # note-attached accents sharing m45
    fermatas = [e for e in els
                if e.identity.kind is ElementKind.ARTICULATION
                and ":m45:" in str(e.identity.element_id)
                and ":v0:" in str(e.identity.element_id)]
    assert len(fermatas) == 6
    assert all(e.identity.onset is not None for e in fermatas)
    trill = next(e for e in els
                 if str(e.identity.element_id) == "P1:m35:s1:v0:other:0")
    assert trill.identity.onset is not None
    # texts: furniture (labels, headers, measure numbers) stays
    # onset-less; every other text attaches
    furniture = [e for e in els
                 if e.text_class in ("label", "labelAbbr", "pgHead",
                                     "pgFoot", "mNum")]
    assert len([e for e in furniture
                if e.text_class in ("label", "labelAbbr")]) == 7
    assert all(e.identity.onset is None for e in furniture)
    other_texts = [e for e in els
                   if e.identity.kind is ElementKind.TEXT
                   and e not in furniture]
    assert other_texts and \
        all(e.identity.onset is not None for e in other_texts)
    chords = [e for e in els
              if e.identity.kind is ElementKind.CHORD_SYMBOL]
    assert chords and all(e.identity.onset is not None for e in chords)


# --- 10.4: native grand-staff brace identity -------------------------------

def test_native_piano_brace_is_part_keyed_and_static(engraved_video):
    # the piano's own brace is a grpSym Verovio draws WITHOUT any
    # injected part-group; geometric identity keys it to its part
    syms = [e for e in engraved_video.layout.elements
            if e.identity.kind is ElementKind.GROUP_SYMBOL]
    assert sorted(str(e.identity.element_id) for e in syms) == \
        sorted(f"score:sys{n}:grpsym:P5" for n in range(1, 16))
    assert all(e.identity.onset is None for e in syms)
    assert not [e for e in engraved_video.layout.elements
                if e.identity.kind is ElementKind.SYSTEM_DIVIDER]


def test_prior_fixtures_flag_their_known_open_ties(engraved,
                                                   engraved_spanners):
    # testscore's "5 ties left open" (Phase 0) and the spanner fixture's
    # 3 (Phase 5) now surface as warnings instead of passing silently;
    # nothing else warns on either fixture.
    assert Counter(w.code for w in engraved.warnings) == \
        {"dropped-spanner": 5}
    assert Counter(w.code for w in engraved_spanners.warnings) == \
        {"dropped-spanner": 3}


# --- 10.5: end-to-end pins on the promoted fixture -------------------------

def test_layout_and_join_census(engraved_video, video_join_mapping):
    # The FLAT fixture repaginates (10R.4): Dorico's encoded page breaks
    # assume hidden staves, so with all staves shown the systems don't
    # fit — never-clip re-derives the breaks, one system per page here.
    # Element census: 4661 raw minus the 13 implausible ties and their
    # 13 continuation segments (10R.3), plus the page-scoped elements
    # repagination re-scopes (re-derived below at 15 pages).
    assert len(engraved_video.layout.pages) == 15
    assert len(engraved_video.layout.elements) == 4635
    assert len(engraved_video.note_records) == 1368
    # complete bijection: every ScoreNote joined to exactly one notehead
    assert len(video_join_mapping) == 1368
    assert len(set(video_join_mapping.values())) == 1368


def test_new_notation_classes_render(engraved_video):
    # trills/fermatas/ppp/wedges/chord-symbol bass ride classes the
    # decomposer already knew — pin that the kinds actually materialize
    kinds = Counter(e.identity.kind for e in engraved_video.layout.elements)
    assert kinds[ElementKind.DYNAMIC] > 0        # incl. ppp
    assert kinds[ElementKind.HAIRPIN] > 0        # <wedge>
    assert kinds[ElementKind.ARTICULATION] > 0   # incl. fermata
    assert kinds[ElementKind.CHORD_SYMBOL] > 0   # incl. bass notes
    assert kinds[ElementKind.OTHER] > 0          # trills, tuplets, ...


def test_element_ids_deterministic_across_reloads(engraved_video):
    from scoreanim.core.engraving.types import EngravingParams
    from scoreanim.core.engraving.verovio_adapter import \
        VerovioEngravingProvider
    again = VerovioEngravingProvider().load_detailed(VIDEO_SCORE,
                                                     EngravingParams())
    ids = [str(e.identity.element_id) for e in engraved_video.layout.elements]
    assert [str(e.identity.element_id) for e in again.layout.elements] == ids


def test_element_ids_stable_under_grouping_on_video(engraved_video):
    # the 8.3 pin on the new fixture, with a NATIVE brace in play:
    # injecting a group must add exactly its grpSym ids and move nothing
    # (the native P5 brace ids included)
    from scoreanim.core.engraving.types import EngravingParams
    from scoreanim.core.engraving.verovio_adapter import \
        VerovioEngravingProvider
    from scoreanim.core.score.musicxml_prep import PartGroupSpec
    grouped = VerovioEngravingProvider().load_detailed(
        VIDEO_SCORE, EngravingParams(),
        groups=(PartGroupSpec(parts=("P1", "P2")),))
    base_ids = {str(e.identity.element_id)
                for e in engraved_video.layout.elements}
    grouped_ids = {str(e.identity.element_id)
                   for e in grouped.layout.elements}
    added = grouped_ids - base_ids
    assert added == {f"score:sys{n}:grpsym:P1-P2" for n in range(1, 16)}
    assert base_ids <= grouped_ids
