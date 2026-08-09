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


def test_the_panel_preview_reengraves_live(qapp_window) -> None:
    """Marcus's real-time requirement: the debounced Scale preview
    already re-engraves — the playback shows the bigger score before
    the edit is even committed — and the commit adds nothing but the
    one undo entry."""
    win = qapp_window
    panel = win.inspector.video_canvas_panel
    scale_field = panel.live_fields[2]
    before_scenes = win._scenes
    undo_before = win.app_state.undo_text()       # the open path's own
    panel._scale.setValue(130.0)
    scale_field.flush_preview()                   # the pause elapses
    assert win._scenes is not before_scenes       # re-engraved LIVE
    assert win.app_state.undo_text() == undo_before   # still a preview
    previewed = win._scenes
    scale_field.commit()
    assert win._scenes is previewed               # no second re-engrave
    assert win.app_state.undo_text() == "set score scale"


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
    # Flat on purpose: the repagination assertion below needs 130 % to
    # overflow, which it did when testscore always engraved flat. With
    # hiding genuinely working (the region fill, 2026-08-09) the hidden
    # systems are short enough to fit — so pin the flat behavior.
    from scoreanim.core.project import SetHideEmptyStaves
    win.app_state.execute(SetHideEmptyStaves(False))
    return win


COMPLEX2 = Path(__file__).parent.parent / "testdata" / "complex2.musicxml"


def test_lyrics_size_scales_only_the_lyrics() -> None:
    """The lyrics knob (spiked in spikes/lyric_size.py) on the one
    fixture whose lyrics reach the layout: syllables grow with the
    factor, noteheads do not, the page never moves. strict=False —
    complex2 is an app-path fixture with known dropped spanners."""
    plain = VerovioEngravingProvider().load_detailed(
        COMPLEX2, EngravingParams(), strict=False)
    sized = VerovioEngravingProvider().load_detailed(
        COMPLEX2, EngravingParams(lyric_size=1.6), strict=False)

    def mean(layout, kind, dim):
        els = [e for e in layout.elements if e.identity.kind is kind]
        assert els
        return sum(getattr(e.bbox, dim) for e in els) / len(els)

    lyric_ratio = mean(sized.layout, ElementKind.LYRIC, "h") \
        / mean(plain.layout, ElementKind.LYRIC, "h")
    head_ratio = mean(sized.layout, ElementKind.NOTEHEAD, "w") \
        / mean(plain.layout, ElementKind.NOTEHEAD, "w")
    assert lyric_ratio == pytest.approx(1.6, abs=0.1)
    assert head_ratio == pytest.approx(1.0, abs=0.02)
    assert sized.layout.pages[0].width == plain.layout.pages[0].width


def test_staff_line_width_thickens_only_the_lines() -> None:
    """The thickness knob (spiked in spikes/staff_line_width.py):
    rendered staff-line ink doubles at factor 2, noteheads and the
    page never move. Measured from pixels — the layout bbox tracks the
    path, not the stroke, so only a render shows the thickness."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from scoreanim.core.project.stage_config import (default_stage_config,
                                                     page_content_top)
    from scoreanim.render.scene import ScoreScenes

    QApplication.instance() or QApplication([])

    def line_thickness(factor):
        eng = VerovioEngravingProvider().load_detailed(
            TESTSCORE, EngravingParams(staff_line_width=factor))
        stage = default_stage_config(eng.prepared,
                                     page_content_top(eng.layout))
        scene = ScoreScenes(eng.layout, stage).scene_for_page(1)
        staff = next(e for e in eng.layout.elements
                     if e.identity.kind is ElementKind.STAFF_LINES
                     and e.page == 1)
        b, Z = staff.bbox, 32
        samples = []
        for frac in (0.15, 0.25, 0.45, 0.55, 0.65, 0.85):
            src = QRectF(b.x + b.w * frac, b.y - 5, 2, b.h + 10)
            img = QImage(int(src.width() * Z), int(src.height() * Z),
                         QImage.Format.Format_RGB32)
            img.fill(Qt.GlobalColor.white)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            scene.render(p, QRectF(0, 0, img.width(), img.height()), src)
            p.end()
            x = img.width() // 2
            run, y0 = 0, 0
            for y in range(img.height()):
                if img.pixelColor(x, y).value() < 200:
                    if run == 0:
                        y0 = y
                    run += 1
                else:
                    if 0 < run < 3 * Z:      # thin: a staff line
                        samples.append(sum(
                            (255 - img.pixelColor(x, yy).value()) / 255
                            for yy in range(max(0, y0 - 3),
                                            min(img.height(), y + 3))) / Z)
                    run = 0
        samples.sort()
        return samples[len(samples) // 2], eng

    def barline_runs(eng):
        """Drawn line widths inside the widest barline complex on the
        last page (a double bar on this fixture) — barlines must ride
        the knob at a fixed ratio, never separately (Marcus's rule)."""
        stage = default_stage_config(eng.prepared,
                                     page_content_top(eng.layout))
        last = len(eng.layout.pages)
        scene = ScoreScenes(eng.layout, stage).scene_for_page(last)
        bar = max((e for e in eng.layout.elements
                   if e.identity.kind is ElementKind.BARLINE
                   and e.page == last), key=lambda e: e.bbox.w)
        b, Z = bar.bbox, 16
        for yfrac in (0.05, 0.15, 0.3, 0.5, 0.8):
            src = QRectF(b.x - 3, b.y + b.h * yfrac, b.w + 6, 1)
            img = QImage(int(src.width() * Z), int(src.height() * Z),
                         QImage.Format.Format_RGB32)
            img.fill(Qt.GlobalColor.white)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            scene.render(p, QRectF(0, 0, img.width(), img.height()), src)
            p.end()
            y = img.height() // 2
            runs, run = [], 0
            for x in range(img.width()):
                if img.pixelColor(x, y).value() < 128:
                    run += 1
                elif run:
                    runs.append(run / Z)
                    run = 0
            if run:
                runs.append(run / Z)
            if runs:
                return runs
        raise AssertionError("no barline ink found")

    thin, plain = line_thickness(1.0)
    thick, sized = line_thickness(2.0)
    assert thick / thin == pytest.approx(2.0, abs=0.1)
    assert _mean_head_width(sized.layout) \
        == pytest.approx(_mean_head_width(plain.layout), rel=0.001)
    assert sized.layout.pages[0].height == plain.layout.pages[0].height
    bars_plain, bars_sized = barline_runs(plain), barline_runs(sized)
    assert len(bars_plain) == len(bars_sized)
    for before, after in zip(bars_plain, bars_sized):
        assert after / before == pytest.approx(2.0, abs=0.15)
