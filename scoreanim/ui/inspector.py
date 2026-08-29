"""Inspector dock: the right-hand panel, three tabs (C1).

The dock used to be one long stack of collapsible sections. Five of them
in a column meant a lot of scrolling, and three of the five had nothing
to do with each other. So the stack became three tabs, one per job:

- **Animate** — the EffectsPanel (M4.8, ui/panels/effects_panel.py):
  which effect runs, its options, the volume response, Floor opacity,
  Sweep, Tied notes as one.
- **Stage** — what the page is drawn in and what the export frame looks
  like: PageColorsPanel over VideoCanvasPanel, still two collapsible
  sections, because both belong to the same tab but are separate jobs.
- **Selection** — the SelectionPanel (M2.5): what is selected, and what
  can be done to it.

A tab with one panel in it gets no section header — the tab label is
already that heading. Only the Stage tab stacks two, so `sections` (the
keys M1.8 persists) holds those two alone. The active tab is persisted
the same way, by key, so a reordering of the tabs cannot make a stored
value point at the wrong one.

Two sync behaviors meet here, unchanged by the move:

- Document intent is resynced through `sync_from_document`, which the
  window calls on every document change. The dock composes the panels
  and delegates; a resync never re-executes a command.
- Selection is transient: the SelectionPanel subscribes to
  `AppState.selection_changed` itself and takes no part in
  `sync_from_document`.

The Playback & Sync section is gone (C1), and with C2 so is the last
of it: Follow and Systems now live on the transport strip, next to the
playhead they describe. Nothing in this dock is playback state any
more, which is why it no longer needs the playback controller at all.
"""
from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDockWidget, QScrollArea, QTabWidget,
                               QVBoxLayout, QWidget)

from scoreanim.core.project import ProjectDoc
from scoreanim.ui import panel_style
from scoreanim.ui.app_state import AppState
from scoreanim.ui.collapsible import CollapsibleSection
from scoreanim.ui.panels import (EffectsPanel, PageColorsPanel,
                                 SelectionPanel, VideoCanvasPanel)

# Tab order, and the key each tab is stored under. The stored value is
# the key, never the index (M1.8 + C1).
TAB_KEYS = ("animate", "stage", "selection")


class Inspector(QDockWidget):
    """Right dock: Animate, Stage, Selection.

    A fixed-feeling zone like the lower zone (ruling 2026-07-24): no
    close/float/move titlebar chrome; its show/hide surface is the
    dock's `toggleViewAction()`, which the View menu picks up.
    `sections` maps stable keys to the CollapsibleSections the Stage tab
    stacks, so M1.8 can persist their expanded states (UI state only —
    rule 5).
    """

    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None, settings=None) -> None:
        super().__init__("Inspector", parent)
        self.setObjectName("Inspector")      # saveState identity (M1.8)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.toggleViewAction().setText("Inspector")
        self._state = app_state

        # Animate: the M4.8 panel owns its commit handlers and resync;
        # the dock only composes and delegates.
        self.effects_panel = EffectsPanel(app_state)

        # Stage, first section: light mode or dark mode. What the whole
        # page is drawn in, whether anything animates or not.
        self.page_colors_panel = PageColorsPanel(app_state)

        # Stage, second section (2026-08-06): the export frame previewed
        # live — preset/size/scale are document intent; the preview
        # background is view state the window subscribes to, riding the
        # window's own settings store (injectable, so tests stay
        # isolated).
        self.video_canvas_panel = VideoCanvasPanel(app_state,
                                                   settings=settings)

        # Selection: transient-state driven, so it observes
        # app_state.selection_changed itself.
        self.selection_panel = SelectionPanel(app_state)

        self.sections: dict[str, CollapsibleSection] = {}
        self.tabs = QTabWidget(self)
        # the app-wide theme styles this tab bar by name (ui/theme)
        self.tabs.setObjectName("InspectorTabs")
        self.tabs.setDocumentMode(True)
        # three short labels always fit; arrows would only ever be noise
        self.tabs.setUsesScrollButtons(False)
        self.tabs.addTab(self._tab([self.effects_panel]), "Animate")
        self.tabs.addTab(self._tab([self._section("page_colors", "Page",
                                                  self.page_colors_panel),
                                    self._section("video_canvas",
                                                  "Video canvas",
                                                  self.video_canvas_panel)]),
                         "Stage")
        self.tabs.addTab(self._tab([self.selection_panel]), "Selection")
        self.setWidget(self.tabs)

    # -- building the tabs -----------------------------------------------------

    def _section(self, key: str, title: str,
                 content: QWidget) -> CollapsibleSection:
        """A collapsible section, registered under `key` so its expanded
        state is persisted."""
        section = CollapsibleSection(title)
        section.set_content(content)
        self.sections[key] = section
        return section

    def _tab(self, widgets: Sequence[QWidget]) -> QScrollArea:
        """One tab page: the widgets in a column, scrolled.

        Scrolled, so the dock's content NEVER dictates the window's
        minimum height — a tab keeps accruing controls and without this
        each addition would raise the smallest usable window.
        """
        body = QWidget()
        column = QVBoxLayout(body)
        # No padding of its own: a section header is a band that runs
        # the full width of the dock, and each body pays its own 8 px
        # inside. The gap here is the one between two groups.
        column.setContentsMargins(0, 0, 0, panel_style.GROUP_GAP)
        column.setSpacing(panel_style.GROUP_GAP)
        for widget in widgets:
            column.addWidget(widget)
        column.addStretch(1)

        scroller = QScrollArea(self)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QScrollArea.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setWidget(body)
        # A scrolled dock will otherwise squeeze its content until the
        # text inside is cut off — "Entire note value" and the volume
        # "Loud" row were the two that showed it. This is the width
        # below which the dock will not go.
        panel_style.lock_min_width(scroller, body)
        return scroller

    # -- which tab is showing (persisted by M1.8) ------------------------------

    @property
    def active_tab(self) -> str:
        return TAB_KEYS[self.tabs.currentIndex()]

    def set_active_tab(self, key: str) -> None:
        """Show the tab stored under `key`; an unknown key is ignored,
        so a stale or hand-edited settings value cannot break startup."""
        if key in TAB_KEYS:
            self.tabs.setCurrentIndex(TAB_KEYS.index(key))

    # -- document sync ---------------------------------------------------------

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Resync the document-intent panels (execute, undo, redo, and
        project load all arrive here via the window); each panel resyncs
        its own controls."""
        self.effects_panel.sync_from_document(doc)
        self.page_colors_panel.sync_from_document(doc)
        self.video_canvas_panel.sync_from_document(doc)
