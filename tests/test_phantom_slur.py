"""Phantom-slur guard (root cause B): a curved spanner (slur/tie/hairpin) must
render on the staff it is attributed to. A continuation segment of a
system-broken spanner that inherits the wrong source — the phase-12 family,
made worse under hide-empty-staves when a source's end note is hidden so its
staff key collapses to 0 and sorts degenerately — would be painted on another
part's staff and revealed on that part's (already-advanced) edge.

complex3 (orchestral, hide-empty-staves ON) has 69 spanner sources whose end
note has no drawn accumulator: the exact condition that mispairs continuation
segments. The fix keys each source by its START-note staff (the staff the
spanner is drawn on), which is reliable even when the end note is missing.

This checks every slur/tie/hairpin element's ink sits near the staff center of
the (system, part, staff) it claims — staff centers derived from that group's
noteheads, so the assertion uses only the public layout. The tolerance (2 staff
gaps) is generous for a slur's arc but catches a gross cross-part swap."""

import statistics
from collections import defaultdict
from pathlib import Path

import pytest

from scoreanim.core.engraving.provider import EngravingParams
from scoreanim.core.engraving.verovio_adapter import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind

COMPLEX3 = Path(__file__).resolve().parent.parent / "testdata" / "complex3.musicxml"
CURVES = {ElementKind.SLUR, ElementKind.TIE, ElementKind.HAIRPIN}


@pytest.fixture(scope="module")
def complex3_hidden():
    if not COMPLEX3.exists():
        pytest.skip("complex3.musicxml fixture not present")
    prov = VerovioEngravingProvider()
    return prov.load_detailed(COMPLEX3, EngravingParams(),
                              hide_empty_staves=True, strict=True)


def test_curves_render_on_their_attributed_staff(complex3_hidden) -> None:
    els = complex3_hidden.layout.elements

    # staff center = median notehead y per (system, part, staff)
    notes: dict[tuple, list[float]] = defaultdict(list)
    for el in els:
        idn = el.identity
        if (idn and idn.kind == ElementKind.NOTEHEAD and el.system
                and idn.part and idn.staff):
            notes[(el.system, idn.part, idn.staff)].append(el.bbox.center.y)
    center = {k: statistics.median(v) for k, v in notes.items()}

    per_system: dict[int, list[float]] = defaultdict(list)
    for (system, _p, _s), y in center.items():
        per_system[system].append(y)

    def gap(system: int) -> float | None:
        ys = sorted(per_system[system])
        diffs = [b - a for a, b in zip(ys, ys[1:])]
        return statistics.median(diffs) if diffs else None

    offenders = []
    for el in els:
        idn = el.identity
        if (not idn or idn.kind not in CURVES or not el.system
                or not idn.part or not idn.staff):
            continue
        c = center.get((el.system, idn.part, idn.staff))
        g = gap(el.system)
        if c is None or not g:
            continue
        dist = abs(el.bbox.center.y - c) / g
        if dist > 2.0:                       # a slur arc stays < ~1.5 gaps
            offenders.append(
                (round(dist, 2), el.system, idn.kind.name, idn.part, idn.staff))

    assert not offenders, (
        f"{len(offenders)} curve(s) rendered far from their attributed staff "
        f"(likely a mis-paired continuation segment): {offenders[:8]}")
