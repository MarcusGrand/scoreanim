"""QSettings persistence of the shell layout (M1.8).

UI state ONLY — window geometry, dock layout, inspector-section
expansion. Nothing here enters the document, and no document intent
enters the settings (rule 5). Saved on an ACCEPTED close only (a
cancelled close-with-unsaved-changes leaves the stored layout
untouched); restored in MainWindow.__init__ once the docks and toolbar
exist. An empty store yields the first-run default, grown from the
alpha's 1000×1200 to fit the right-hand inspector dock (brief flag 8).
"""
from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMainWindow

from scoreanim.ui.collapsible import CollapsibleSection

FIRST_RUN_SIZE = (1400, 1000)

_GEOMETRY = "window/geometry"
_DOCK_STATE = "window/dockState"
_SECTION_PREFIX = "inspector/section/"
_STATE_VERSION = 0        # bump to discard stored dock layouts on upgrade


def default_settings() -> QSettings:
    """The app's one settings store — explicit identity, since app.py
    sets no organization/application name on the QApplication."""
    return QSettings("ScoreAnim", "ScoreAnim")


def restore_window_state(window: QMainWindow,
                         sections: Mapping[str, CollapsibleSection],
                         settings: QSettings) -> None:
    """Restore geometry, dock layout, and section expansion; any
    missing key falls back to the built-in default (first run, or a
    deleted/partial store)."""
    geometry = settings.value(_GEOMETRY)
    if geometry is not None:
        window.restoreGeometry(geometry)
    else:
        window.resize(*FIRST_RUN_SIZE)
    dock_state = settings.value(_DOCK_STATE)
    if dock_state is not None:
        window.restoreState(dock_state, _STATE_VERSION)
    for key, section in sections.items():
        section.set_expanded(settings.value(
            _SECTION_PREFIX + key, section.expanded, type=bool))


def save_window_state(window: QMainWindow,
                      sections: Mapping[str, CollapsibleSection],
                      settings: QSettings) -> None:
    settings.setValue(_GEOMETRY, window.saveGeometry())
    settings.setValue(_DOCK_STATE, window.saveState(_STATE_VERSION))
    for key, section in sections.items():
        settings.setValue(_SECTION_PREFIX + key, section.expanded)
