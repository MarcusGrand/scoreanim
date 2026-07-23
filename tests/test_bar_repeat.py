"""Phase 12.2 — bar-repeat synthesis.

Verovio's MusicXML importer has no <measure-repeat> support (the repeat
bars import as invisible <space>), so the adapter synthesizes a %
repeat-bar symbol per repeated measure — the slash-region shape (rule 10
family). Per measure, onset on the downbeat (ruling b); animated by
default (denylist) and tinted/reveal-anchored like a slash.
"""

from scoreanim.core.animation import ANCHOR_KINDS, TINTED_KINDS, is_animated
from scoreanim.core.animation.schedule import REVEALED_KINDS, STATIC_KINDS
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.musicxml_prep import RepeatRegion, prepare

from .conftest import BAR_REPEAT_SCORE


# --- prep-seam detection ---------------------------------------------------

def test_repeat_regions_detected_half_open():
    """One [start, stop) region; the fixture's start at m2 stays open to the
    end (no stop within mm.1-6), so it closes at last+1 = 7."""
    prep = prepare(BAR_REPEAT_SCORE)
    assert prep.repeat_regions == (
        RepeatRegion(part="P25", start_measure=2, stop_measure=7, bar_span=1),)


# --- synthesis -------------------------------------------------------------

def _bar_repeats(engraved_bar_repeat):
    return [e for e in engraved_bar_repeat.layout.elements
            if e.identity.kind is ElementKind.BAR_REPEAT]


def test_one_symbol_per_repeated_bar(engraved_bar_repeat):
    """Per-measure granularity (ruling b): five bars in [2, 7)."""
    br = _bar_repeats(engraved_bar_repeat)
    assert len(br) == 5
    ids = {str(e.identity.element_id) for e in br}
    assert ids == {f"P25:m{m}:barrepeat" for m in range(2, 7)}


def test_onsets_are_the_bar_downbeats(engraved_bar_repeat):
    """4/4 at 20 divisions: the region's bars start at qstamps 4, 8, …, 20."""
    br = sorted(_bar_repeats(engraved_bar_repeat), key=lambda e: e.identity.onset)
    assert [e.identity.onset for e in br] == [4.0, 8.0, 12.0, 16.0, 20.0]
    for e in br:
        assert e.identity.part == "P25" and e.identity.staff == 1


def test_bar_repeat_animates_tints_and_anchors(engraved_bar_repeat):
    """The kind is outside the scaffold denylist (so it animates once it
    carries an onset), and joins the tint + reveal-anchor sets like SLASH."""
    assert ElementKind.BAR_REPEAT not in STATIC_KINDS
    assert ElementKind.BAR_REPEAT not in REVEALED_KINDS
    assert ElementKind.BAR_REPEAT in TINTED_KINDS
    assert ElementKind.BAR_REPEAT in ANCHOR_KINDS
    for e in _bar_repeats(engraved_bar_repeat):
        assert is_animated(e.identity)


def test_bar_repeat_has_ink_centered_in_its_bar(engraved_bar_repeat):
    """A drawn glyph (not an empty element), positioned inside its staff."""
    for e in _bar_repeats(engraved_bar_repeat):
        assert e.glyph.paths                      # actual ink
        assert e.bbox.w > 0 and e.bbox.h > 0
        assert e.anchor == e.bbox.center


def test_no_unknown_class_warnings(engraved_bar_repeat):
    """The empty <space> the repeat bars import as is invisible — it must
    not trip the unknown-class guard or leave the load with warnings."""
    codes = {w.code for w in engraved_bar_repeat.warnings}
    assert "unknown-class" not in codes
