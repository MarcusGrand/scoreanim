"""Hide-empty-staves (Phase 10R): the two-pass optimize load hides
staves that are empty for a whole system — the layout the score's
encoded page breaks assume. Mechanics: spikes/NOTES.md "Phase 10R"
(id- and timemap-transparent MEI round-trip; slash regions win over
the option via the hide-unavailable fallback, rule 10)."""

from collections import Counter, defaultdict

from scoreanim.core.engraving.systems import system_bands
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio_adapter import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind

from .conftest import TESTSCORE, VIDEO_SCORE

# first system full (engraving convention), then per-system hiding
EXPECTED_ROWS = [8, 2, 2, 4, 2, 2, 5, 4, 5, 4, 4, 4, 4, 4, 4]


def _staves_per_system(engraved) -> list[int]:
    by_system: dict[int, set] = defaultdict(set)
    for e in engraved.layout.elements:
        if e.identity.kind is ElementKind.STAFF_LINES:
            by_system[e.system].add((e.identity.part, e.identity.staff))
    return [len(by_system[s]) for s in sorted(by_system)]


def test_hidden_layout_matches_the_encoded_page_plan(engraved_video_hidden):
    assert _staves_per_system(engraved_video_hidden) == EXPECTED_ROWS
    assert not [e for e in engraved_video_hidden.layout.elements
                if e.identity.kind is ElementKind.SYSTEM_DIVIDER]


def test_hiding_never_touches_musical_content(engraved_video,
                                              engraved_video_hidden):
    # staves with notes are never hidden: the note-record stream (ids,
    # onsets, pitches) is identical to the flat load
    assert engraved_video_hidden.note_records == engraved_video.note_records


def test_no_system_overflows_its_page(engraved_video_hidden):
    page_h = engraved_video_hidden.layout.pages[0].height
    for band in system_bands(engraved_video_hidden.layout):
        assert band.rect.y + band.rect.h <= page_h, \
            f"system {band.system} overflows page {band.page}"


def test_native_brace_follows_staff_visibility(engraved_video_hidden):
    # the brace draws only where a piano staff survives — including
    # systems with ONE visible piano staff (geometric identity's
    # single-part branch)
    syms = sorted(str(e.identity.element_id)
                  for e in engraved_video_hidden.layout.elements
                  if e.identity.kind is ElementKind.GROUP_SYMBOL)
    assert syms == ["score:sys1:grpsym:P5", "score:sys7:grpsym:P5",
                    "score:sys8:grpsym:P5"]


def test_hidden_load_warning_census(engraved_video_hidden):
    """The condensed layout changes Verovio's tie behavior slightly:
    one previously-dropped open tie (P4 m41) now DRAWS, producing a
    continuation segment with no resolvable source — skipped with a
    flag, never absorbed (ruling b). The 13 implausible ties suppress
    identically to the flat load."""
    assert Counter(w.code for w in engraved_video_hidden.warnings) == {
        "dropped-spanner": 5, "implausible-tie": 13,
        "segment-count-mismatch": 1, "unattributed-continuation": 1}


def test_hidden_load_is_deterministic():
    p = VerovioEngravingProvider()
    a = p.load_detailed(VIDEO_SCORE, EngravingParams(),
                        hide_empty_staves=True)
    b = p.load_detailed(VIDEO_SCORE, EngravingParams(),
                        hide_empty_staves=True)
    assert [str(e.identity.element_id) for e in a.layout.elements] == \
        [str(e.identity.element_id) for e in b.layout.elements]


def test_note_owned_fragments_keep_their_owner_onset(engraved_video_hidden):
    """Regression (Phase 10R page-jump bug): under condensed layout
    Verovio reuses SVG group ids across element types, so a stem's id
    can collide with a distant note's — a naive id lookup gave the stem
    the note's late onset, dragging the page-follow forward (bar 3 →
    page 4). Every note-owned fragment must sit within its measure's own
    note-onset range."""
    import re

    by_scope: dict[str, list] = {}
    for e in engraved_video_hidden.layout.elements:
        m = re.match(r"^(P\d+:m\d+:s\d+:v\d+):", str(e.identity.element_id))
        if m and e.identity.onset is not None:
            by_scope.setdefault(m.group(1), []).append(
                (e.identity.kind, e.identity.onset,
                 str(e.identity.element_id)))
    fragment = {ElementKind.STEM, ElementKind.FLAG, ElementKind.ACCIDENTAL,
                ElementKind.BEAM, ElementKind.ARTICULATION}
    for items in by_scope.values():
        notes = [o for k, o, _ in items if k is ElementKind.NOTEHEAD]
        if not notes:
            continue
        lo, hi = min(notes), max(notes)
        for kind, onset, eid in items:
            if kind in fragment:
                assert lo - 0.01 <= onset <= hi + 0.01, \
                    f"{eid} onset {onset} outside note range [{lo},{hi}]"


def test_page_follow_never_jumps_backward(engraved_video_hidden,
                                          video_score_model):
    """The page a trigger stamps must not leap ahead of its neighbours
    (the visible symptom of the id-collision bug): follow-mode page
    turns walk the stamped pages, so a stray late page = a visible jump
    and snap-back."""
    from scoreanim.core.animation import build_trigger_schedule
    from scoreanim.core.score.join import join_notes

    report = join_notes(video_score_model, engraved_video_hidden.note_records)
    sched = build_trigger_schedule(engraved_video_hidden.layout,
                                   report.mapping, video_score_model.measures)
    pages = [t.page for t in sched.triggers]
    # chronological triggers ⇒ non-decreasing pages (encoded page order
    # follows musical time; no system revisits an earlier page)
    assert pages == sorted(pages), \
        f"page follow jumps: {[p for p in pages]}"


def test_slash_regions_win_over_hiding(engraved):
    # testscore's drum staff would be hidden across its slash regions
    # (Verovio sees MEI <space> as empty) — the adapter falls back to
    # the flat layout, flagged, never a broken slash synthesis (rule 10)
    hidden = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), hide_empty_staves=True)
    assert [w.code for w in hidden.warnings].count("hide-unavailable") == 1
    assert _staves_per_system(hidden) == _staves_per_system(engraved)
    slashes = [e for e in hidden.layout.elements
               if e.identity.kind is ElementKind.SLASH]
    assert len(slashes) == 52            # the Phase 1 census, intact
