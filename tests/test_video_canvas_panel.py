"""The Video canvas block: presets and fields drive the document, the
display re-derives from it, and the preview background never touches
the document at all."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.project import SetVideoCanvas, VideoCanvas  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.panels.video_canvas import VideoCanvasPanel  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, tmp_path):
    state = AppState()
    settings = QSettings(str(tmp_path / "test.ini"),
                         QSettings.Format.IniFormat)
    return VideoCanvasPanel(state, settings=settings), state


def _pick(p: VideoCanvasPanel, data) -> None:
    index = p._preset_index(data)
    assert index >= 0
    p._preset.setCurrentIndex(index)
    p._on_preset(index)                     # activated is user-only


def test_opens_on_page_aspect_with_nothing_stored(panel) -> None:
    p, state = panel
    assert state.doc.stage.canvas is None
    assert p._preset.currentData() is None
    assert not p._width.isEnabled()
    # score scale is canvas-independent (it sizes the notation itself)
    assert p._scale.isEnabled()
    assert p._scale.value() == 100.0


def test_a_preset_click_is_one_command(panel) -> None:
    p, state = panel
    _pick(p, (1080, 1920))
    assert state.doc.stage.canvas == VideoCanvas(1080, 1920)
    assert state.undo_text() == "set video canvas"
    assert p._width.value() == 1080 and p._height.value() == 1920
    assert p._width.isEnabled()
    state.undo()
    assert state.doc.stage.canvas is None
    assert not state.can_undo               # one entry for the gesture
    assert not p._width.isEnabled()         # display re-derived


def test_scale_previews_debounced_and_commits_once(panel) -> None:
    """Scale re-engraves, so its LiveField is debounced: a value change
    arms the timer instead of previewing at once; the (flushed) preview
    changes the document live with NO undo entry; the finished edit is
    one entry, and undo re-derives the display."""
    p, state = panel
    scale_field = p.live_fields[2]
    assert scale_field.spin is p._scale
    p._scale.setValue(130.0)
    assert state.doc.engraving.scale == 1.0  # armed, not fired
    scale_field.flush_preview()              # the pause elapses
    assert state.doc.engraving.scale == 1.3  # live in the playback
    assert not state.can_undo                # preview: no entry yet
    scale_field.commit()
    assert state.committed.engraving.scale == 1.3
    assert state.undo_text() == "set score scale"
    state.undo()
    assert state.doc.engraving.scale == 1.0
    assert not state.can_undo
    assert p._scale.value() == 100.0         # display re-derived


def test_page_aspect_clears_the_canvas(panel) -> None:
    p, state = panel
    state.execute(SetVideoCanvas(VideoCanvas(1920, 1080)))
    _pick(p, None)
    assert state.doc.stage.canvas is None
    assert state.undo_text() == "clear video canvas"


def test_custom_seeds_a_canvas_only_when_none(panel) -> None:
    p, state = panel
    _pick(p, "custom")
    assert state.doc.stage.canvas == VideoCanvas(1920, 1080)
    seeded = state.doc
    _pick(p, "custom")                      # already set: no new entry
    assert state.doc is seeded


def test_the_display_rederives_on_load_and_undo(panel) -> None:
    p, state = panel
    state.execute(SetVideoCanvas(VideoCanvas(2160, 3840)))
    assert p._preset.currentData() == (2160, 3840)
    state.execute(SetVideoCanvas(VideoCanvas(1000, 600)))  # off-preset
    assert p._preset.currentData() == "custom"
    state.undo()
    assert p._preset.currentData() == (2160, 3840)


def test_preview_toggle_writes_settings_not_the_document(panel) -> None:
    p, state = panel
    heard = []
    p.preview_changed.connect(lambda on, color: heard.append(
        (on, color.name())))
    before = state.doc
    p._preview_box.setChecked(True)
    assert heard == [(True, "#000000")]     # black is the default
    assert state.doc is before              # document untouched
    assert not state.can_undo               # and no undo entry
    assert not state.is_dirty
    assert p._settings.value("stage/overlayPreview", type=bool) is True
    p._preview_box.setChecked(False)
    assert heard[-1] == (False, "#000000")


def test_restore_preview_reflects_settings(panel, qapp, tmp_path) -> None:
    p, state = panel
    p._settings.setValue("stage/overlayPreview", True)
    p._settings.setValue("stage/overlayColor", "#123456")
    heard = []
    p.preview_changed.connect(lambda on, color: heard.append(
        (on, color.name())))
    p.restore_preview()
    assert heard == [(True, "#123456")]
    assert p.overlay_preview() == (True, QColor("#123456"))


def test_lyrics_size_is_a_debounced_engraving_field(panel) -> None:
    """Same contract as Scale: armed on change, live on the pause,
    one undo entry on commit."""
    p, state = panel
    lyrics_field = p.live_fields[3]
    assert lyrics_field.spin is p._lyrics
    p._lyrics.setValue(70.0)
    assert state.doc.engraving.lyric_size == 1.0
    lyrics_field.flush_preview()
    assert state.doc.engraving.lyric_size == 0.7
    assert not state.can_undo
    lyrics_field.commit()
    assert state.undo_text() == "set lyrics size"
    state.undo()
    assert state.doc.engraving.lyric_size == 1.0
    assert p._lyrics.value() == 100.0


def test_staff_line_width_is_a_debounced_engraving_field(panel) -> None:
    """Same contract as Scale and Lyrics: armed on change, live on the
    pause, one undo entry on commit."""
    p, state = panel
    field = p.live_fields[4]
    assert field.spin is p._staff_lines
    p._staff_lines.setValue(150.0)
    assert state.doc.engraving.staff_line_width == 1.0
    field.flush_preview()
    assert state.doc.engraving.staff_line_width == 1.5
    assert not state.can_undo
    field.commit()
    assert state.undo_text() == "set staff line width"
    state.undo()
    assert state.doc.engraving.staff_line_width == 1.0
    assert p._staff_lines.value() == 100.0
