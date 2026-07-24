"""Inspector dock: right-hand panel of collapsible sections (M1.4).

Three sections per the roadmap, amended by the time-fields ruling
(Marcus, 2026-07-24): Tempo/Offset/Swing live on the transport strip
with the transport they configure, so *Playback & Sync* here holds only
the Follow/Systems toggles.

Two sync behaviors share the first section (brief flag 3): Follow is
transient controller state exposed as `follow_action` — the Playback
menu adds the SAME action, so the menu item and the inspector toggle
cannot diverge — and is never resynced from the document (there is
nothing to resync from). Systems and Sweep are document intent
(commands), resynced with the blockSignals idiom via
`sync_from_document`, which the window calls on every document change —
a resync never re-executes a command.

Floor opacity is the last prefix-in-spinbox, retired here into a
labeled field with the alpha commit wiring verbatim: keyboard tracking
off, commit on editingFinished, epsilon no-op guard.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QCheckBox, QDockWidget, QDoubleSpinBox,
                               QFormLayout, QLabel, QVBoxLayout, QWidget)

from scoreanim.core.animation import RevealMode
from scoreanim.core.project import (PresentationMode, ProjectDoc,
                                    SetFloorOpacity, SetPresentationMode,
                                    SetRevealMode)
from scoreanim.ui.app_state import AppState
from scoreanim.ui.collapsible import CollapsibleSection
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

        # RevealMode toggle: checked = CONTINUOUS sweep, unchecked =
        # STEPPED (jumps at musical onsets). Document intent → command.
        self._sweep_box = QCheckBox("Sweep")
        self._sweep_box.setToolTip("Continuous reveal sweep; unchecked "
                                   "steps at musical onsets")
        self._sweep_box.toggled.connect(
            lambda checked: app_state.execute(SetRevealMode(
                RevealMode.CONTINUOUS if checked else RevealMode.STEPPED)))

        # ghost floor (Phase 7.2): document intent, 0 allowed — scaffold
        # stays visible, unrevealed animated ink goes fully invisible
        self._floor_spin = QDoubleSpinBox()
        self._floor_spin.setDecimals(2)
        self._floor_spin.setSingleStep(0.05)
        self._floor_spin.setRange(0.0, 1.0)
        self._floor_spin.setKeyboardTracking(False)
        self._floor_spin.setToolTip("Opacity of unrevealed animated ink; "
                                    "0 hides it until onset")
        self._floor_spin.editingFinished.connect(self._commit_floor)

        playback_body = QWidget()
        playback_col = QVBoxLayout(playback_body)
        playback_col.setContentsMargins(8, 2, 8, 6)
        playback_col.addWidget(self._follow_box)
        playback_col.addWidget(self._systems_box)

        appearance_body = QWidget()
        appearance_form = QFormLayout(appearance_body)
        appearance_form.setContentsMargins(8, 2, 8, 6)
        appearance_form.addRow("Floor opacity", self._floor_spin)
        appearance_form.addRow(self._sweep_box)

        selection_body = QLabel("Nothing selected")   # placeholder for M2
        selection_body.setContentsMargins(8, 2, 8, 6)
        selection_body.setEnabled(False)

        body = QWidget(self)
        column = QVBoxLayout(body)
        column.setContentsMargins(4, 4, 4, 4)
        column.setSpacing(4)
        self.sections: dict[str, CollapsibleSection] = {}
        for key, title, content in (
                ("playback", "Playback && Sync", playback_body),
                ("appearance", "Appearance && Effects", appearance_body),
                ("selection", "Selection", selection_body)):
            section = CollapsibleSection(title)
            section.set_content(content)
            self.sections[key] = section
            column.addWidget(section)
        column.addStretch(1)
        self.setWidget(body)

    # -- document sync ---------------------------------------------------------

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Resync the document-intent toggles/field (execute, undo,
        redo, and project load all arrive here via the window). Follow
        is deliberately absent — transient controller state."""
        self._systems_box.blockSignals(True)
        self._systems_box.setChecked(doc.stage.mode
                                     is PresentationMode.SYSTEM)
        self._systems_box.blockSignals(False)
        self._sweep_box.blockSignals(True)
        self._sweep_box.setChecked(doc.style.reveal_mode
                                   is RevealMode.CONTINUOUS)
        self._sweep_box.blockSignals(False)
        self._floor_spin.blockSignals(True)
        self._floor_spin.setValue(doc.style.floor_opacity)
        self._floor_spin.blockSignals(False)

    # -- commit handlers -------------------------------------------------------

    def _commit_floor(self) -> None:
        value = self._floor_spin.value()
        if abs(value - self._state.doc.style.floor_opacity) < 1e-9:
            return
        self._state.execute(SetFloorOpacity(value))
