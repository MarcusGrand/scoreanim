"""The triplet_error fixture end to end: under the default hidden load
the m28 tuplet numbers and brackets exist as their OWN parts' elements
(Alto 1 = P1, Trumpet 1 = P3), light at the triplet's onset, and are
selectable and onset-movable — while the Trombone 1 (P4) m27 groups
that used to absorb the stolen ink keep exactly their own. The
mechanism itself is pinned synthetically in test_decoration_reclaim.py."""

import pytest

from scoreanim.core.animation.retime import is_retimeable
from scoreanim.core.selection.policy import is_selectable
from scoreanim.core.score.identity import ElementKind

TUPLET_IDS = ("P1:m28:s1:v1:other:0", "P1:m28:s1:v1:other:1",
              "P3:m28:s1:v1:other:0", "P3:m28:s1:v1:other:1")


@pytest.fixture(scope="module")
def by_id(engraved_triplet_hidden):
    return {str(el.identity.element_id): el
            for el in engraved_triplet_hidden.layout.elements}


def test_the_four_tuplet_decorations_exist_with_their_own_onset(by_id):
    for eid in TUPLET_IDS:
        el = by_id.get(eid)
        assert el is not None, f"{eid} missing under hidden load"
        assert el.identity.kind is ElementKind.OTHER
        assert el.identity.onset == 108.0        # the triplet's first note
        assert el.glyph.paths                    # it has its ink back


def test_the_decorations_are_clickable_and_onset_movable(by_id):
    # Correct attribution is what makes both true: OTHER is not
    # backdrop, and it is animated-but-not-anchor once it has an onset.
    for eid in TUPLET_IDS:
        ident = by_id[eid].identity
        assert is_selectable(ident.kind)
        assert is_retimeable(ident)


def test_the_absorbers_keep_exactly_their_own_ink(by_id):
    # The Trombone 1 m27 hosts the ink used to land in: the staff its
    # five lines, the notehead and beam one path each. The phantom
    # accidental (born entirely of stolen bracket polylines) is asserted
    # by ink, not id — accidental seqs renumber once it is gone.
    assert len(by_id["P4:m27:s1:v0:staff_lines:0"].glyph.paths) == 5
    assert len(by_id["P4:m27:s1:v1:note:14"].glyph.paths) == 1
    assert len(by_id["P4:m27:s1:v2:beam:0"].glyph.paths) == 1
    assert not [eid for eid, el in by_id.items()
                if ":m27:" in eid and ":accidental:" in eid
                and len(el.glyph.paths) > 1]


def test_the_default_load_has_nothing_left_to_reclaim(engraved_triplet_hidden):
    """Since the slash fill went unconditional (2026-08-31) this score
    no longer TRIGGERS the artifact: the fill notes change what Verovio
    mints ids for, and the m28 decorations keep their own ink from the
    start. The four tests above still pass, so the outcome is the same
    — it is now reached without a reclaim rather than through one."""
    codes = [w.code for w in engraved_triplet_hidden.warnings]
    assert codes.count("reclaimed-decoration-ink") == 0
    assert "empty-decoration" not in codes


def test_the_reclaim_still_works_on_the_load_that_provokes_it(
        engraved_triplet_unfilled):
    """The score is our only real-Verovio reproducer of stolen
    decoration ink, and the pass that fixes it is still live code — so
    the coverage is kept by loading the way that still provokes it,
    with the region fill off. Same trick the rule-10 fallback tests use
    (test_hide_empty_staves), and for the same reason: the path has to
    stay reachable to stay tested. The synthetic half is in
    test_decoration_reclaim.py."""
    codes = [w.code for w in engraved_triplet_unfilled.warnings]
    assert codes.count("reclaimed-decoration-ink") == 4
    assert "empty-decoration" not in codes
    by_id = {str(el.identity.element_id): el
             for el in engraved_triplet_unfilled.layout.elements}
    for eid in TUPLET_IDS:                       # and the ink lands right
        assert by_id[eid].glyph.paths
        assert by_id[eid].identity.onset == 108.0


def test_hidden_onsets_match_the_flat_load(engraved_triplet_hidden):
    from pathlib import Path

    from scoreanim.core.engraving.types import EngravingParams
    from scoreanim.core.engraving.verovio import VerovioEngravingProvider
    from tests.conftest import TRIPLET_SCORE
    flat = VerovioEngravingProvider().load_detailed(
        Path(TRIPLET_SCORE), EngravingParams())
    flat_by_id = {str(el.identity.element_id): el.identity.onset
                  for el in flat.layout.elements}
    hidden_by_id = {str(el.identity.element_id): el.identity.onset
                    for el in engraved_triplet_hidden.layout.elements}
    for eid in TUPLET_IDS:
        assert hidden_by_id[eid] == flat_by_id[eid] == 108.0
