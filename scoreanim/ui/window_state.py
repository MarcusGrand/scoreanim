"""QSettings persistence of the shell layout (M1.8).

UI state ONLY — window geometry, dock layout, which inspector tab is
showing, and which of its sections are expanded. Nothing here enters
the document, and no document intent enters the settings (rule 5).
Saved on an ACCEPTED close only (a cancelled close-with-unsaved-changes
leaves the stored layout untouched); restored in MainWindow.__init__
once the docks and toolbar exist. An empty store yields the first-run
default, grown from the alpha's 1000×1200 to fit the right-hand
inspector dock (brief flag 8).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMainWindow

if TYPE_CHECKING:                       # import only for the type hint
    from scoreanim.ui.inspector import Inspector

FIRST_RUN_SIZE = (1400, 1000)

_GEOMETRY = "window/geometry"
_DOCK_STATE = "window/dockState"
_SECTION_PREFIX = "inspector/section/"
_ACTIVE_TAB = "inspector/tab"
_STATE_VERSION = 0        # bump to discard stored dock layouts on upgrade


def default_settings() -> QSettings:
    """The app's one settings store — explicit identity, since app.py
    sets no organization/application name on the QApplication."""
    return QSettings("ScoreAnim", "ScoreAnim")


def restore_window_state(window: QMainWindow, inspector: "Inspector",
                         settings: QSettings) -> None:
    """Restore geometry, dock layout, the inspector's active tab and its
    section expansion; any missing key falls back to the built-in
    default (first run, or a deleted/partial store)."""
    geometry = settings.value(_GEOMETRY)
    if geometry is not None:
        window.restoreGeometry(geometry)
    else:
        window.resize(*FIRST_RUN_SIZE)
    dock_state = settings.value(_DOCK_STATE)
    if dock_state is not None:
        window.restoreState(dock_state, _STATE_VERSION)
    inspector.set_active_tab(settings.value(_ACTIVE_TAB,
                                            inspector.active_tab, type=str))
    for key, section in inspector.sections.items():
        section.set_expanded(settings.value(
            _SECTION_PREFIX + key, section.expanded, type=bool))


def save_window_state(window: QMainWindow, inspector: "Inspector",
                      settings: QSettings) -> None:
    settings.setValue(_GEOMETRY, window.saveGeometry())
    settings.setValue(_DOCK_STATE, window.saveState(_STATE_VERSION))
    settings.setValue(_ACTIVE_TAB, inspector.active_tab)
    for key, section in inspector.sections.items():
        settings.setValue(_SECTION_PREFIX + key, section.expanded)
