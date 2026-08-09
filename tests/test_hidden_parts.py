"""Hiding a part end to end through the Verovio adapter (2026-08-09).

The document names parts to hide; the prep seam removes them before
Verovio, so the engraving simply never contains them. These tests pin
the adapter half: the layout carries no ink for a hidden part, the
OTHER parts' ids never move (ids embed the part id, not an index), the
retry paths re-prepare with the hiding intact (the M5.2 trap, third
family), and hiding the one slash-region part CURES hide-unavailable
on testscore rather than tripping it.
"""
from __future__ import annotations

import pytest

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from tests.conftest import TALL_SYSTEM_SCORE, TESTSCORE


@pytest.fixture(scope="module")
def hidden_p2():
    return VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), hidden_parts=frozenset({"P2"}))


def _parts_in(engraved_score) -> set[str]:
    return {str(e.identity.part) for e in engraved_score.layout.elements
            if e.identity.part is not None}


def test_hidden_part_has_no_ink(hidden_p2) -> None:
    parts = _parts_in(hidden_p2)
    assert "P2" not in parts
    assert {"P1", "P3", "P4", "P5", "P6", "P7"} <= parts


def test_other_parts_ids_do_not_shift(engraved, hidden_p2) -> None:
    """Ids embed the MusicXML part id, so stored overrides on visible
    parts survive a hide. P1 draws identically (same system shape), so
    its id set must match the flat baseline's exactly."""
    def ids_of(engraved_score, pid):
        return {str(e.identity.element_id)
                for e in engraved_score.layout.elements
                if str(e.identity.part) == pid}
    assert ids_of(hidden_p2, "P1") == ids_of(engraved, "P1")


def test_hiding_the_region_part_cures_hide_unavailable() -> None:
    """testscore is hide-unavailable at baseline (P7's slash regions).
    With P7 hidden its regions leave the scan, so empty-staff hiding
    genuinely runs — at least one system thins, and no warning fires."""
    out = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), hide_empty_staves=True,
        hidden_parts=frozenset({"P7"}))
    assert "hide-unavailable" not in {w.code for w in out.warnings}
    assert out.prepared.slash_regions == ()
    by_system: dict[tuple[int, int | None], set[str]] = {}
    for e in out.layout.elements:
        if e.system is None or e.identity.part is None:
            continue
        by_system.setdefault((e.page, e.system), set()) \
            .add(str(e.identity.part))
    # non-vacuous: with hiding OFF every system carries all 6 visible
    # parts; with it genuinely on, at least one system has fewer
    assert any(len(parts) < 6 for parts in by_system.values())


def test_scale_to_fit_retry_keeps_the_part_hidden() -> None:
    """The never-clip retries re-prepare from scratch: every intent has
    to ride along or it is silently lost (the M5.2 trap). tall_system_min
    takes the scaled-to-fit path; the hidden part must stay gone."""
    out = VerovioEngravingProvider().load_detailed(
        TALL_SYSTEM_SCORE, EngravingParams(), strict=False,
        hidden_parts=frozenset({"P25"}))
    assert "scaled-to-fit" in {w.code for w in out.warnings}
    assert "P25" not in _parts_in(out)


def test_a_gone_part_is_warned_inert() -> None:
    out = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(), hidden_parts=frozenset({"P99"}))
    warning = next(w for w in out.warnings
                   if w.code == "hidden-part-inert")
    assert "P99" in warning.message
    assert len(_parts_in(out)) == 7          # nothing actually removed
