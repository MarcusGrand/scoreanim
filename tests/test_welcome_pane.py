"""The welcome pane and window-wide drag-and-drop (E1), offscreen.

Three things are pinned here: the pure rule for what this app can open,
the pane's one promise — it is there exactly while no score is — and
the drop path, including the question a drop asks before it throws an
open score away.

Every window gets its own ini-backed QSettings (tmp_path), so no test
touches the developer's real recent-files store.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (QMimeData, QPoint, QPointF,  # noqa: E402
                            QSettings, Qt, QUrl)
from PySide6.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from scoreanim.core.project import (SUFFIX, FileKind,  # noqa: E402
                                    FileRef, ProjectDoc, first_openable,
                                    kind_of)
from scoreanim.ui.main_window import MainWindow  # noqa: E402
from scoreanim.ui.recents import RecentFiles  # noqa: E402
from scoreanim.ui.welcome_pane import NO_RECENTS  # noqa: E402
from tests.conftest import TESTSCORE  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def settings(tmp_path):
    return QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)


@pytest.fixture()
def window(qapp, settings):
    return MainWindow(settings=settings)


# -- what we can open (pure) ----------------------------------------------

def test_kind_of_knows_the_two_openable_suffixes() -> None:
    assert kind_of(Path("a.musicxml")) is FileKind.SCORE
    assert kind_of(Path("a.xml")) is FileKind.SCORE
    assert kind_of(Path(f"a{SUFFIX}")) is FileKind.PROJECT


def test_kind_of_ignores_case_and_refuses_everything_else() -> None:
    assert kind_of(Path("A.MusicXML")) is FileKind.SCORE
    assert kind_of(Path("a.pdf")) is None
    assert kind_of(Path("a.wav")) is None
    assert kind_of(Path("plain")) is None


def test_first_openable_takes_the_first_file_we_can_open() -> None:
    dropped = [Path("notes.pdf"), Path("song.xml"), Path("other.musicxml")]
    assert first_openable(dropped) == Path("song.xml")
    assert first_openable([Path("notes.pdf")]) is None
    assert first_openable([]) is None


# -- the pane --------------------------------------------------------------

def test_pane_shows_on_an_empty_launch(window) -> None:
    window.show()
    QApplication.processEvents()
    assert window.welcome.isVisible()


def test_pane_covers_the_stage(window) -> None:
    window.show()
    QApplication.processEvents()
    assert window.welcome.geometry() == window.view.viewport().geometry()


def test_pane_never_sets_a_floor_under_the_window(window) -> None:
    """The stage sizes the pane, never the other way round."""
    assert window.welcome.minimumSize() == window.view.viewport() \
        .minimumSize()


def test_pane_lists_the_recent_files(qapp, settings, tmp_path) -> None:
    recents = RecentFiles(settings)
    recents.add(tmp_path / "one.musicxml")
    recents.add(tmp_path / f"two{SUFFIX}")
    window = MainWindow(settings=settings)
    listed = window.welcome._recents
    assert [listed.item(n).text() for n in range(listed.count())] \
        == [f"two{SUFFIX}", "one.musicxml"]


def test_pane_says_so_when_nothing_was_opened_yet(window) -> None:
    window.show()
    QApplication.processEvents()
    assert window.welcome._empty.isVisible()
    assert window.welcome._empty.text() == NO_RECENTS
    assert not window.welcome._recents.isVisible()


def test_pane_goes_when_a_score_is_loaded(window) -> None:
    window.show()
    QApplication.processEvents()
    _load(window)
    assert not window.welcome.isVisible()


def test_a_real_open_hides_the_pane_and_fills_the_list(qapp,
                                                       settings) -> None:
    """The end-to-end check: open the fixture score for real."""
    window = MainWindow(settings=settings)
    window.show()
    window.files.open_score(TESTSCORE)
    QApplication.processEvents()
    assert not window.welcome.isVisible()
    assert window.app_state.measures                  # a score really loaded
    second = MainWindow(settings=settings)
    listed = second.welcome._recents
    assert [listed.item(n).text() for n in range(listed.count())] \
        == [TESTSCORE.name]


# -- dropping on the window ------------------------------------------------

def test_a_score_drag_is_accepted(window, tmp_path) -> None:
    event = _drag_enter(tmp_path / "song.musicxml")
    window.dragEnterEvent(event)
    assert event.isAccepted()


def test_a_project_drag_is_accepted(window, tmp_path) -> None:
    event = _drag_enter(tmp_path / f"song{SUFFIX}")
    window.dragEnterEvent(event)
    assert event.isAccepted()


def test_a_drag_of_something_else_is_left_alone(window, tmp_path) -> None:
    event = _drag_enter(tmp_path / "notes.pdf")
    window.dragEnterEvent(event)
    assert not event.isAccepted()


def test_a_drop_on_the_empty_stage_opens_without_asking(window, tmp_path,
                                                        monkeypatch) -> None:
    opened = _spy(window, monkeypatch)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(_never_asked))
    score = tmp_path / "song.musicxml"
    window.dropEvent(_drop(score))
    assert opened == [score]


def test_a_drop_takes_the_openable_file_out_of_the_drag(window, tmp_path,
                                                        monkeypatch) -> None:
    opened = _spy(window, monkeypatch)
    score = tmp_path / "song.musicxml"
    window.dropEvent(_drop(tmp_path / "sleeve.pdf", score))
    assert opened == [score]


def test_a_drop_of_nothing_openable_is_ignored(window, tmp_path,
                                               monkeypatch) -> None:
    opened = _spy(window, monkeypatch)
    event = _drop(tmp_path / "sleeve.pdf")
    window.dropEvent(event)
    assert opened == []
    assert not event.isAccepted()


def test_a_drop_over_a_loaded_score_asks_first(window, tmp_path,
                                               monkeypatch) -> None:
    opened = _spy(window, monkeypatch)
    _load(window)
    asked: list[str] = []

    def question(parent, title, text, *args, **kwargs):
        asked.append(text)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    score = tmp_path / "song.musicxml"
    window.dropEvent(_drop(score))
    assert opened == []                       # Cancel kept the old score
    assert asked and "song.musicxml" in asked[0]

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Open))
    window.dropEvent(_drop(score))
    assert opened == [score]


def test_the_stage_does_not_swallow_a_drop(window) -> None:
    """QGraphicsView accepts drops in its own constructor; if it kept
    them, a drag over the score would stop there and never reach the
    window (the whole reason FileDrops turns them off)."""
    assert not window.view.acceptDrops()
    assert window.acceptDrops()


# -- helpers ---------------------------------------------------------------

def _load(window) -> None:
    """Put a score in the document without engraving one: the pane and
    the drop question read `doc.score`, nothing else."""
    window.app_state.reset_document(
        ProjectDoc(score=FileRef(path="/somewhere/song.musicxml",
                                 sha256="0" * 64)))
    QApplication.processEvents()


def _spy(window, monkeypatch) -> list[Path]:
    opened: list[Path] = []
    monkeypatch.setattr(window.files, "open_file", opened.append)
    return opened


def _never_asked(*args, **kwargs):
    raise AssertionError("an empty stage has nothing to replace")


# A drag event does NOT own its QMimeData: hand it a temporary and
# Python frees it the moment the constructor returns, leaving the event
# pointing at nothing (a segfault, found while writing these). Qt keeps
# the real thing alive for the length of a real drag; here we do.
_KEEP_ALIVE: list[QMimeData] = []


def _mime(*paths: Path) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    _KEEP_ALIVE.append(mime)
    return mime


def _drag_enter(*paths: Path) -> QDragEnterEvent:
    return QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction,
                           _mime(*paths), Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)


def _drop(*paths: Path) -> QDropEvent:
    return QDropEvent(QPointF(10.0, 10.0), Qt.DropAction.CopyAction,
                      _mime(*paths), Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)
