"""The score scale (2026-08-06): the notation drawn bigger on the SAME
page — an engraving input, verified through the provider and through a
real window. Spiked first in spikes/score_scale.py."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from scoreanim.core.engraving.types import EngravingParams  # noqa: E402
from scoreanim.core.engraving.verovio import (  # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.score.identity import ElementKind  # noqa: E402

TESTSCORE = Path(__file__).parent.parent / "testdata" / "testscore.musicxml"


def _mean_head_width(layout) -> float:
    heads = [e for e in layout.elements
             if e.identity.kind is ElementKind.NOTEHEAD]
    return sum(e.bbox.w for e in heads) / len(heads)


@pytest.fixture(scope="module")
def scaled():
    return VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(scale=1.3))


def test_bigger_notation_on_the_same_page(engraved, scaled) -> None:
    """Scale 1.3 draws every notehead 1.3x as wide; the page geometry
    never moves (scaleToPageSize — measured in the spike)."""
    assert scaled.layout.pages[0].width \
        == engraved.layout.pages[0].width
    assert scaled.layout.pages[0].height \
        == engraved.layout.pages[0].height
    ratio = _mean_head_width(scaled.layout) \
        / _mean_head_width(engraved.layout)
    assert ratio == pytest.approx(1.3, abs=0.02)


def test_overflow_repaginates_never_clip(engraved, scaled) -> None:
    """At 1.3 testscore's two-system pages no longer fit, so the rule-7
    machinery repaginates — more pages, nothing clipped, and the
    warning says so."""
    assert len(scaled.layout.pages) > len(engraved.layout.pages)
    codes = {w.code for w in scaled.warnings}
    assert "repaginated" in codes
    page_h = scaled.layout.pages[0].height
    from scoreanim.core.engraving.systems import system_bands
    for band in system_bands(scaled.layout):
        assert band.rect.y + band.rect.h <= page_h + 1e-6


def test_default_scale_is_byte_identical(engraved) -> None:
    """1.0 multiplies out to Verovio's own default and sets nothing —
    the goldens' guarantee, checked directly."""
    again = VerovioEngravingProvider().load_detailed(
        TESTSCORE, EngravingParams(scale=1.0))
    assert again.layout == engraved.layout


def test_the_command_reengraves_in_the_window(qapp_window) -> None:
    """SetScoreScale through the app path: the engraved world
    re-derives (fresh scenes, bigger ink), and undo restores it."""
    from scoreanim.core.project import SetScoreScale

    win = qapp_window
    before_scenes = win._scenes
    before_pages = win._scenes.page_count
    win.app_state.execute(SetScoreScale(1.3))
    assert win._scenes is not before_scenes       # re-engraved
    assert win._scenes.page_count > before_pages  # repaginated
    win.app_state.undo()
    assert win._scenes.page_count == before_pages


@pytest.fixture()
def qapp_window(tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from scoreanim.ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "ui.ini"),
                         QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(TESTSCORE)
    return win
