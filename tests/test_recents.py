"""Open Recent (B1), offscreen: the store's ordering rule, the submenu
built from it, the suffix dispatch, and the round trip through a real
window — open a score, close, reopen with the same settings store, and
the entry is still there and still opens.

Every test injects its own ini-backed QSettings (tmp_path), so nothing
touches the developer's real preferences store.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from scoreanim.ui.main_window import MainWindow  # noqa: E402
from scoreanim.ui.recents import (MAX_RECENTS, RecentFiles,  # noqa: E402
                                  RecentsMenu, pushed)
from tests.conftest import TESTSCORE  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def settings(tmp_path):
    return QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)


# -- the ordering rule (pure) ---------------------------------------------

def test_pushed_puts_the_newest_first() -> None:
    assert pushed(["a", "b"], "c") == ["c", "a", "b"]


def test_pushed_moves_a_repeat_to_the_front_without_duplicating() -> None:
    assert pushed(["a", "b", "c"], "b") == ["b", "a", "c"]


def test_pushed_caps_the_list() -> None:
    older = [str(n) for n in range(MAX_RECENTS)]
    kept = pushed(older, "new")
    assert len(kept) == MAX_RECENTS
    assert kept[0] == "new"
    assert older[-1] not in kept          # the oldest fell off the end


# -- the store ------------------------------------------------------------

def test_store_round_trips_through_a_fresh_reader(settings, tmp_path) -> None:
    """What survives a restart is what a second RecentFiles over the
    same store reads back."""
    path = tmp_path / "song.musicxml"
    RecentFiles(settings).add(path)
    reader = RecentFiles(QSettings(settings.fileName(),
                                   QSettings.Format.IniFormat))
    assert reader.paths() == [path.resolve()]


def test_store_keeps_absolute_paths(settings, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "song.musicxml").touch()
    recents = RecentFiles(settings)
    recents.add(Path("song.musicxml"))
    assert recents.paths() == [(tmp_path / "song.musicxml").resolve()]


def test_store_remove_and_clear(settings, tmp_path) -> None:
    recents = RecentFiles(settings)
    first, second = tmp_path / "a.musicxml", tmp_path / "b.scoreanim"
    recents.add(first)
    recents.add(second)
    recents.remove(second.resolve())
    assert recents.paths() == [first.resolve()]
    recents.clear()
    assert recents.paths() == []


def test_empty_store_reads_as_an_empty_list(settings) -> None:
    assert RecentFiles(settings).paths() == []


# -- the submenu ----------------------------------------------------------

def test_menu_lists_the_names_newest_first(qapp, settings, tmp_path) -> None:
    recents = RecentFiles(settings)
    recents.add(tmp_path / "one.musicxml")
    recents.add(tmp_path / "two.scoreanim")
    menu = RecentsMenu(recents, lambda path: None)
    assert [a.text() for a in menu.actions()] == ["two.scoreanim",
                                                  "one.musicxml"]
    assert menu.actions()[0].toolTip() \
        == str((tmp_path / "two.scoreanim").resolve())


def test_empty_menu_says_so_and_cannot_be_clicked(qapp, settings) -> None:
    menu = RecentsMenu(RecentFiles(settings), lambda path: None)
    assert [a.text() for a in menu.actions()] == ["No Recent Files"]
    assert not menu.actions()[0].isEnabled()


def test_menu_refills_itself_when_it_opens(qapp, settings,
                                           tmp_path) -> None:
    """Nobody tells the menu about an open; it re-reads the store."""
    recents = RecentFiles(settings)
    menu = RecentsMenu(recents, lambda path: None)
    recents.add(tmp_path / "later.musicxml")
    menu.aboutToShow.emit()
    assert [a.text() for a in menu.actions()] == ["later.musicxml"]


def test_menu_action_opens_the_file_it_names(qapp, settings,
                                             tmp_path) -> None:
    opened: list[Path] = []
    recents = RecentFiles(settings)
    recents.add(tmp_path / "one.musicxml")
    recents.add(tmp_path / "two.musicxml")
    menu = RecentsMenu(recents, opened.append)
    menu.actions()[1].trigger()               # the older of the two
    assert opened == [(tmp_path / "one.musicxml").resolve()]


# -- dispatch + the window round trip -------------------------------------

def test_open_recent_picks_the_opener_from_the_suffix(qapp, settings,
                                                      tmp_path) -> None:
    window = MainWindow(settings=settings)
    calls: list[tuple[str, Path]] = []
    window.files.open_score = lambda p: calls.append(("score", p))
    window.files.open_project = lambda p: calls.append(("project", p))
    score, project = tmp_path / "a.musicxml", tmp_path / "b.scoreanim"
    score.touch()
    project.touch()
    window.files.open_recent(score)
    window.files.open_recent(project)
    assert calls == [("score", score), ("project", project)]


def test_open_recent_drops_an_entry_whose_file_has_gone(
        qapp, settings, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    window = MainWindow(settings=settings)
    gone = tmp_path / "gone.musicxml"
    window.files.recents.add(gone)
    window.files.open_recent(gone.resolve())
    assert window.files.recents.paths() == []


def test_a_score_open_survives_a_restart_and_reopens(qapp, settings,
                                                     monkeypatch) -> None:
    """The whole feature end to end: open a score, close the window,
    build a fresh one over the same store — the entry is listed, and
    triggering it loads that score again."""
    # the fixture has a .tempo sidecar, so the open leaves the document
    # dirty and the close would ask about saving
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard))
    first = MainWindow(settings=settings)
    first.files.open_score(TESTSCORE)
    assert first.files.recents.paths() == [TESTSCORE.resolve()]
    assert first.close()

    second = MainWindow(settings=settings)
    menu = second.menus.recents_menu
    assert [a.text() for a in menu.actions()] == [TESTSCORE.name]
    second.menus.recents_menu.actions()[0].trigger()
    assert second.files.score_name == TESTSCORE.name
    assert second.app_state.measures                  # a score really loaded
