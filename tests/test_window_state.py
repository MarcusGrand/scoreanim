"""Shell-layout persistence (M1.8), offscreen: an accepted close saves
geometry + dock layout + section expansion into QSettings and a fresh
window restores them; a cancelled close saves nothing; an empty store
falls back to the first-run default size.

Each test injects its own ini-backed QSettings (tmp_path), so nothing
touches the developer's real preferences store.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from scoreanim.core.project import SetOffset  # noqa: E402
from scoreanim.ui.main_window import MainWindow  # noqa: E402
from scoreanim.ui.window_state import FIRST_RUN_SIZE  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def settings(tmp_path):
    return QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)


def test_empty_store_yields_first_run_default(qapp, settings) -> None:
    window = MainWindow(settings=settings)
    assert (window.width(), window.height()) == FIRST_RUN_SIZE


def test_accepted_close_round_trips_layout(qapp, settings) -> None:
    first = MainWindow(settings=settings)
    first.show()
    # ask for a size inside the offscreen screen (800×600); a shown
    # window clamps to the chrome's minimum (which grew with the M4.8
    # effects panel), so the round-trip pin compares against the ACTUAL
    # size the first window settled at, not the requested literal
    first.resize(780, 560)
    saved_size = (first.width(), first.height())
    first.inspector.sections["appearance"].set_expanded(False)
    first.inspector.hide()               # dock visibility is saveState's
    assert first.close()                 # clean doc → accepted → saved

    second = MainWindow(settings=settings)
    second.show()
    assert (second.width(), second.height()) == saved_size
    assert not second.inspector.sections["appearance"].expanded
    assert second.inspector.sections["playback"].expanded
    assert second.inspector.sections["selection"].expanded
    assert second.inspector.isHidden()
    assert not second.lower_zone.isHidden()
    second.close()


def test_cancelled_close_saves_nothing(qapp, settings, monkeypatch) -> None:
    window = MainWindow(settings=settings)
    assert window.app_state.execute(SetOffset(1.0))   # dirty the project
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))
    assert not window.close()            # cancelled → event ignored
    assert settings.value("window/geometry") is None
    assert settings.value("window/dockState") is None
