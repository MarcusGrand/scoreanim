"""Overlay preview wiring on a real MainWindow, offscreen: the panel's
toggle hides the paper and paints the video color behind the ink, the
document never dirties, and a re-engrave keeps the preview applied."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.project import (SetHideEmptyStaves,  # noqa: E402
                                    SetVideoCanvas, VideoCanvas)
from scoreanim.ui.main_window import MainWindow  # noqa: E402

TESTSCORE = Path(__file__).parent.parent / "testdata" / "testscore.musicxml"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.files.open_score(TESTSCORE)
    win.resize(900, 700)
    win.show()
    qapp.processEvents()
    return win


def _page_pixel(window) -> str:
    """Viewport color at an ink-free spot on the page (just inside the
    left edge, mid-height)."""
    view = window.view
    page = view.scene().sceneRect()
    pt: QPoint = view.mapFromScene(
        QPointF(page.left() + page.width() * 0.02, page.height() * 0.5))
    image = view.viewport().grab().toImage()
    return image.pixelColor(pt).name()


def test_toggle_paints_and_restores(window, qapp) -> None:
    assert _page_pixel(window) == "#ffffff"
    doc_before = window.app_state.doc           # a fresh open is already
    dirty_before = window.app_state.is_dirty    # dirty; pin NO CHANGE
    undo_before = window.app_state.undo_text()
    panel = window.inspector.video_canvas_panel
    panel._preview_box.setChecked(True)
    qapp.processEvents()
    assert _page_pixel(window) == "#000000"     # black video behind ink
    assert window.app_state.doc is doc_before   # view state only
    assert window.app_state.is_dirty == dirty_before
    assert window.app_state.undo_text() == undo_before  # no new entry
    panel._preview_box.setChecked(False)
    qapp.processEvents()
    assert _page_pixel(window) == "#ffffff"


def test_preview_survives_a_reengrave(window, qapp) -> None:
    """A re-engrave adopts fresh scenes with their paper visible; the
    installer re-applies the preview."""
    panel = window.inspector.video_canvas_panel
    panel._preview_box.setChecked(True)
    qapp.processEvents()
    window.app_state.execute(SetHideEmptyStaves(False))   # re-engraves
    qapp.processEvents()
    assert _page_pixel(window) == "#000000"


def test_preview_fills_the_canvas_frame(window, qapp) -> None:
    """With a canvas set, the fill covers the frame — including the
    letterbox slack past the page edge, which is video too."""
    window.app_state.execute(SetVideoCanvas(VideoCanvas(1080, 1920)))
    panel = window.inspector.video_canvas_panel
    panel._preview_box.setChecked(True)
    qapp.processEvents()
    view = window.view
    page = view.scene().sceneRect()
    frame = view._framing.frame
    assert frame.bottom() > page.bottom()       # portrait slack is real
    below_page_y = (page.bottom() + frame.bottom()) / 2
    pt = view.mapFromScene(QPointF(page.center().x(), below_page_y))
    image = view.viewport().grab().toImage()
    assert image.pixelColor(pt).name() == "#000000"
