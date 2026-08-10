"""Decoration ink stolen under Verovio id reuse (2026-08-10): an empty
tupletNum/tupletBracket group whose id appears on another group in the
same page gets its ink back from that group's direct children, matched
by the class's own ink signature (kinds._DECORATION_INK). Pinned
synthetically — the test_adapter_coverage precedent — so the mechanism
does not depend on the 5-part fixture; test_tuplet_reclaim.py pins the
real score."""

import pytest

from scoreanim.core.engraving.verovio.decompose import _PageDecomposer
from scoreanim.core.engraving.verovio.mei_index import _MeiIndex
from scoreanim.core.engraving.verovio.records import _LoadState
from scoreanim.core.score.identity import ElementKind

# Glyph defs: E883 is a SMuFL tuplet digit (in the reclaim range),
# E0A4 a notehead (outside it).
_DEFS = ('<defs>'
         '<g id="E883-p1"><path d="M0 0 L10 0 L10 14 L0 14 Z"/></g>'
         '<g id="E0A4-p1"><path d="M0 0 L8 0 L8 8 L0 8 Z"/></g>'
         '</defs>')


def _page(m1_inner: str, m2_inner: str) -> str:
    """Two measures on one system, plus the glyph defs the <use>s need
    (outer:inner viewBox = 1:10, the definition-scale envelope)."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'viewBox="0 0 2096 2967">'
        f'{_DEFS}'
        '<svg viewBox="0 0 20960 29670" class="definition-scale">'
        '<g class="page-margin" transform="translate(50, 50)">'
        '<g class="system" xml:id="s1">'
        f'<g class="measure" xml:id="m1">{m1_inner}</g>'
        f'<g class="measure" xml:id="m2">{m2_inner}</g>'
        '</g></g></svg></svg>')


def _state(strict: bool = True, **mei_kwargs) -> _LoadState:
    return _LoadState(
        prep=None,
        mei=_MeiIndex(measure_by_id={"m1": 1, "m2": 2}, **mei_kwargs),
        onset_by_id={"n1": 0.0, "n2": 4.0},
        measure_start={1: 0.0, 2: 4.0},
        measure_duration={1: 4.0, 2: 4.0},
        staff_n_by_id={}, layer_n_by_id={}, strict=strict)


def test_note_host_gives_the_numeral_back_by_glyph_range():
    """The stolen tuplet digit is a DIRECT <use> child of the same-id
    note; the note's own head is a NESTED notehead <use> outside the
    digit range — the host keeps exactly its own ink."""
    svg = _page(
        '<g class="note" xml:id="dup1">'
        '<g class="notehead"><use xlink:href="#E0A4-p1"/></g>'
        '<use xlink:href="#E883-p1"/>'                      # stolen digit
        '</g>',
        '<g class="tuplet" xml:id="t1">'
        '<g class="tupletNum" xml:id="dup1"></g>'           # empty victim
        '<g class="note" xml:id="n2">'
        '<g class="notehead"><use xlink:href="#E0A4-p1"/></g></g>'
        '</g>')
    st = _state(tuplet_note_ids={"t1": ("n2",)})
    accs = _PageDecomposer(svg, page=1, adapter=st).run()
    nums = [a for a in accs if a.svg_class == "tupletNum"]
    assert len(nums) == 1
    (num,) = nums
    assert len(num.paths) == 1
    assert num.measure == 2 and num.kind is ElementKind.OTHER
    assert num.owner_onset == 4.0            # the tuplet's own first note
    host = next(a for a in accs
                if a.svg_class == "note" and a.verovio_id == "dup1")
    assert len(host.paths) == 1              # its own head, nothing else
    assert [w.code for w in st.warnings] == ["reclaimed-decoration-ink"]
    assert "tupletNum m2" in st.warnings[0].message
    assert "note m1" in st.warnings[0].message


def test_container_host_gives_the_bracket_back_and_the_staff_keeps_five_lines():
    """Bracket polylines drawn directly in a same-id LAYER fall through
    the container to the staff element — the reclaim must intercept
    them before the staff absorbs ink it never owned."""
    staff_lines = "".join(
        f'<path d="M0 {y} L2000 {y}"/>' for y in (0, 90, 180, 270, 360))
    svg = _page(
        f'<g class="staff" xml:id="st1" data-n="1">{staff_lines}'
        '<g class="layer" xml:id="dup2">'
        '<polyline points="0,500 300,500"/>'                # stolen
        '<polyline points="0,500 0,540"/>'                  # stolen
        '<g class="note" xml:id="n1">'
        '<g class="notehead"><use xlink:href="#E0A4-p1"/></g></g>'
        '</g></g>',
        '<g class="tuplet" xml:id="t1">'
        '<g class="tupletBracket" xml:id="dup2"></g>'       # empty victim
        '<g class="note" xml:id="n2">'
        '<g class="notehead"><use xlink:href="#E0A4-p1"/></g></g>'
        '</g>')
    st = _state(tuplet_note_ids={"t1": ("n2",)})
    accs = _PageDecomposer(svg, page=1, adapter=st).run()
    staff = next(a for a in accs if a.kind is ElementKind.STAFF_LINES)
    assert len(staff.paths) == 5             # exactly its own lines
    brackets = [a for a in accs if a.svg_class == "tupletBracket"]
    assert len(brackets) == 1
    assert len(brackets[0].paths) == 2
    assert brackets[0].measure == 2
    assert [w.code for w in st.warnings] == ["reclaimed-decoration-ink"]
    assert "layer m1" in st.warnings[0].message


def test_collision_without_matching_ink_raises_strict_warns_app():
    """The id collides but no signature ink exists anywhere — the
    decoration is genuinely missing. Loud both ways: strict raises,
    the app path warns and drops the empty element."""
    m1 = ('<g class="note" xml:id="dup3">'
          '<g class="notehead"><use xlink:href="#E0A4-p1"/></g></g>')
    m2 = ('<g class="tuplet" xml:id="t1">'
          '<g class="tupletBracket" xml:id="dup3"></g>'
          '<g class="note" xml:id="n2">'
          '<g class="notehead"><use xlink:href="#E0A4-p1"/></g></g>'
          '</g>')
    with pytest.raises(ValueError, match="page 1.*tupletBracket m2"):
        _PageDecomposer(_page(m1, m2), page=1,
                        adapter=_state(tuplet_note_ids={"t1": ("n2",)})
                        ).run()
    st = _state(strict=False, tuplet_note_ids={"t1": ("n2",)})
    accs = _PageDecomposer(_page(m1, m2), page=1, adapter=st).run()
    assert not [a for a in accs if a.svg_class == "tupletBracket"]
    assert [w.code for w in st.warnings] == ["empty-decoration"]
    assert "no matching ink was found" in st.warnings[0].message


def test_empty_groups_without_theft_evidence_stay_silent():
    """Two routine shapes, neither a theft: an empty NON-decoration
    class colliding with real ink (the page-1 accid/barLine pairs on
    the fixture), and an empty decoration group whose id is unique.
    Both drop silently — status quo."""
    svg = _page(
        '<g class="barLine" xml:id="dup4"><path d="M0 0 L0 360"/></g>'
        '<g class="accid" xml:id="dup4"></g>'                # not ours
        '<g class="tuplet" xml:id="t1">'
        '<g class="tupletNum" xml:id="lonely"></g>'          # no collision
        '<g class="note" xml:id="n1">'
        '<g class="notehead"><use xlink:href="#E0A4-p1"/></g></g>'
        '</g>',
        '<g class="note" xml:id="n2">'
        '<g class="notehead"><use xlink:href="#E0A4-p1"/></g></g>')
    st = _state(tuplet_note_ids={"t1": ("n1",)})
    accs = _PageDecomposer(svg, page=1, adapter=st).run()
    assert st.warnings == []
    assert not [a for a in accs if a.svg_class in ("tupletNum", "accid")]
