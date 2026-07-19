"""Phase 11 milestone fixture: testdata/complex1.musicxml loads, joins,
and pins the Dorico-robustness features (tremolo, mRest ledger tier, the
grace-note join gap, notation coverage). Grows across tasks 11.2/11.3/11.5.
"""

from scoreanim.core.score.identity import ElementKind


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
