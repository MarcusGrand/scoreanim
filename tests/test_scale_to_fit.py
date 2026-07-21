"""Phase 12.5 — scale-to-fit (never-clip completion, rule 7).

A single system taller than its page cannot be paginated away (Dorico
sizes the page for its condensed score). The adapter scales the engraving
down uniformly so the tallest system fits — nothing is clipped. Derived
every load from the measured overflow, never stored.
"""

from scoreanim.core.engraving.systems import system_bands
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider

from .conftest import TALL_SYSTEM_SCORE, TESTSCORE


def _load(path):
    return VerovioEngravingProvider().load_detailed(
        path, EngravingParams(), strict=False)


def test_tall_system_is_scaled_to_fit_not_clipped():
    eng = _load(TALL_SYSTEM_SCORE)
    codes = [w.code for w in eng.warnings]
    assert "scaled-to-fit" in codes
    # nothing is left clipped: no system bottom exceeds the page
    page_h = eng.layout.pages[0].height
    assert all(b.rect.y + b.rect.h <= page_h
               for b in system_bands(eng.layout))
    # and the defensive residual-overflow warning never fires
    assert "system-overflow" not in codes


def test_scale_to_fit_reports_a_reduced_percentage():
    eng = _load(TALL_SYSTEM_SCORE)
    msg = next(w.message for w in eng.warnings if w.code == "scaled-to-fit")
    pct = int(msg.split("scaled to ")[1].split("%")[0])
    assert 1 <= pct < 100                      # shrunk, but positive


def test_a_fitting_score_is_never_scaled():
    """testscore fits its page — no scale-to-fit, byte-identical to before
    (the whole existing suite pins its layout)."""
    codes = [w.code for w in _load(TESTSCORE).warnings]
    assert "scaled-to-fit" not in codes
