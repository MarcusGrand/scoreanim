"""Inspector dock: right-hand panel of collapsible sections (M1.4).

Three sections per the roadmap, amended by the time-fields ruling
(Marcus, 2026-07-24): Tempo/Offset/Swing live on the transport strip
with the transport they configure, so *Playback & Sync* here holds only
the Follow/Systems toggles.

Two sync behaviors share the first section (brief flag 3): Follow is
transient controller state exposed as `follow_action` — the Playback
menu adds the SAME action, so the menu item and the inspector toggle
cannot diverge — and is never resynced from the document (there is
nothing to resync from). Systems is document intent (a command),
resynced with the blockSignals idiom via `sync_from_document`, which
the window calls on every document change — a resync never re-executes
a command.

The *Appearance & Effects* body is the EffectsPanel (M4.8,
ui/panels/effects_panel.py) — Floor opacity and Sweep moved there with
the effect controls; this dock composes it and delegates its resync.

The *Selection* body is the SelectionPanel (M2.5,
ui/panels/selection_panel.py) — a third sync behavior: it reads
TRANSIENT selection state, so it subscribes to
`AppState.selection_changed` itself and, like Follow, takes no part in
`sync_from_document`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QCheckBox, QDockWidget, QScrollArea,
                               QVBoxLayout, QWidget)

from scoreanim.core.project import (PresentationMode, ProjectDoc,
                                    SetPresentationMode)
from scoreanim.ui.app_state import AppState
from scoreanim.ui.collapsible import CollapsibleSection
from scoreanim.ui.panels import EffectsPanel, SelectionPanel
from scoreanim.ui.playback import PlaybackController


class Inspector(QDockWidget):
    """Right dock: Playback & Sync, Appearance & Effects, Selection.

    A fixed-feeling zone like the lower zone (ruling 2026-07-24): no
    close/float/move titlebar chrome; its show/hide surface is the
    dock's `toggleViewAction()`, which the View menu picks up in M1.5.
    `sections` maps stable keys to the CollapsibleSections so M1.8 can
    persist their expanded states (UI state only — rule 5).
    """

    def __init__(self, app_state: AppState, playback: PlaybackController,
                 parent: QWidget | None = None) -> None:
        super().__init__("Inspector", parent)
        self.setObjectName("Inspector")      # saveState identity (M1.8)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.toggleViewAction().setText("Inspector")
        self._state = app_state

        # Follow: transient controller state, NOT doc intent — survives
        # nothing, so no command and no resync. Checkbox and action are
        # bound both ways (setChecked no-ops on an unchanged value, so
        # the binding cannot loop).
        self.follow_action = QAction("Follow", self)
        self.follow_action.setCheckable(True)
        self.follow_action.setChecked(True)
        self.follow_action.toggled.connect(playback.set_follow)
        self._follow_box = QCheckBox("Follow")
        self._follow_box.setToolTip("Keep the stage on the playhead's "
                                    "page (or system)")
        self._follow_box.setChecked(self.follow_action.isChecked())
        self._follow_box.toggled.connect(self.follow_action.setChecked)
        self.follow_action.toggled.connect(self._follow_box.setChecked)

        # PresentationMode toggle (Phase 7.4): checked = one system at a
        # time. Document intent → command, like Sweep.
        self._systems_box = QCheckBox("Systems")
        self._systems_box.setToolTip("Stage one system at a time; "
                                     "unchecked shows whole pages")
        self._systems_box.toggled.connect(
            lambda checked: app_state.execute(SetPresentationMode(
                PresentationMode.SYSTEM if checked
                else PresentationMode.PAGED)))

        playback_body = QWidget()
        playback_col = QVBoxLayout(playback_body)
        playback_col.setContentsMargins(8, 2, 8, 6)
        playback_col.addWidget(self._follow_box)
        playback_col.addWidget(self._systems_box)

        # Appearance & Effects body: the M4.8 panel owns its commit
        # handlers and resync; the dock only composes and delegates.
        self.effects_panel = EffectsPanel(app_state)

        # Selection body (M2.5): transient-state driven, so it observes
        # app_state.selection_changed itself and takes no part in
        # sync_from_document.
        self.selection_panel = SelectionPanel(app_state)

        body = QWidget(self)
        column = QVBoxLayout(body)
        column.setContentsMargins(4, 4, 4, 4)
        column.setSpacing(4)
        self.sections: dict[str, CollapsibleSection] = {}
        for key, title, content in (
                ("playback", "Playback && Sync", playback_body),
                ("appearance", "Appearance && Effects", self.effects_panel),
                ("selection", "Selection", self.selection_panel)):
            section = CollapsibleSection(title)
            section.set_content(content)
            self.sections[key] = section
            column.addWidget(section)
        column.addStretch(1)
        # Scrolled, so the dock's content NEVER dictates the window's
        # minimum height: sections keep accruing controls (M4 grew
        # Appearance, M2 added Selection, M3 will grow it again) and
        # without this each addition raises the smallest usable window.
        scroller = QScrollArea(self)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QScrollArea.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setWidget(body)
        self.setWidget(scroller)

    # -- document sync ---------------------------------------------------------

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Resync the document-intent controls (execute, undo, redo, and
        project load all arrive here via the window); the effects panel
        resyncs its own controls. Follow is deliberately absent —
        transient controller state."""
        self._systems_box.blockSignals(True)
        self._systems_box.setChecked(doc.stage.mode
                                     is PresentationMode.SYSTEM)
        self._systems_box.blockSignals(False)
        self.effects_panel.sync_from_document(doc)
