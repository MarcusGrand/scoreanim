"""The welcome pane (E1): what the stage shows before a score is open.

The app's front door. It names the app, offers the two openers, lists
what was open last, and says that a file can simply be dropped on the
window — so an empty launch is a place to start rather than a dark
rectangle.

It is a child of the STAGE VIEW, sized to the viewport, for the same
reason the zoom controls are (`ui/zoom_overlay.py`): a child of the
viewport scrolls away with the picture. It decides nothing — the
buttons drive `FileActions`, the list is a view of the same
`RecentFiles` store the File menu reads, and the window tells it
whether a score is open.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel,
                               QLayout, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout, QWidget)

from scoreanim.core.project import ProjectDoc
from scoreanim.ui.stage_view import StageView
from scoreanim.ui.theme import icons

if TYPE_CHECKING:
    from scoreanim.ui.file_actions import FileActions

# How many recent files the front door shows. The store keeps eight
# (`recents.MAX_RECENTS`) and the File menu shows all of them; this is a
# starting point, not the whole history, and a short list reads faster.
SHOWN_RECENTS = 6

TAGLINE = "Animate a score against a recording."
DROP_HINT = "Drop a score or a project anywhere in this window."
NO_RECENTS = "Nothing opened yet."


class WelcomePane(QWidget):
    """The empty-stage front door, over one `StageView`."""

    def __init__(self, view: StageView, files: FileActions) -> None:
        super().__init__(view)
        self.setObjectName("WelcomePane")
        # a plain QWidget paints no background of its own; this is what
        # lets the stylesheet give it the app's ground, so the pane
        # covers the letterbox instead of showing through it
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._view = view
        self._files = files
        # kept as a reference, not re-fetched: the event filter still
        # runs while Qt is tearing the window down (the zoom overlay's
        # lesson, 2026-08-29)
        self._viewport = view.viewport()

        title = QLabel("ScoreAnim")
        title.setObjectName("WelcomeTitle")
        tagline = QLabel(TAGLINE)
        tagline.setObjectName("WelcomeTagline")

        open_score = QPushButton(icons.icon("file-music"), "Open Score…")
        open_score.clicked.connect(files.open_score_dialog)
        open_project = QPushButton("Open Project…")
        open_project.clicked.connect(files.open_project_dialog)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(open_score)
        buttons.addWidget(open_project)
        buttons.addStretch(1)

        self._recents_heading = QLabel("Recent")
        self._recents_heading.setObjectName("WelcomeHeading")
        self._recents = QListWidget()
        self._recents.setObjectName("WelcomeRecents")
        # one click opens, the way a front door's list should; no
        # selection to leave behind and no keyboard focus to steal from
        # the stage
        self._recents.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._recents.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._recents.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._recents.itemClicked.connect(self._open_item)
        self._empty = QLabel(NO_RECENTS)
        self._empty.setObjectName("WelcomeDim")

        hint = QLabel(DROP_HINT)
        hint.setObjectName("WelcomeDim")

        column = QVBoxLayout()
        column.setSpacing(6)
        column.addWidget(title)
        column.addWidget(tagline)
        column.addSpacing(14)
        column.addLayout(buttons)
        column.addSpacing(14)
        column.addWidget(self._recents_heading)
        column.addWidget(self._recents)
        column.addWidget(self._empty)
        column.addSpacing(14)
        column.addWidget(hint)

        # the column is a fixed-width card in the middle of the stage:
        # stretches on all four sides, so it stays centered whatever the
        # window does, and never grows into a page-wide banner
        card = QWidget(self)
        card.setLayout(column)
        card.setFixedWidth(360)
        middle = QHBoxLayout()
        middle.addStretch(1)
        middle.addWidget(card)
        middle.addStretch(1)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        outer.addLayout(middle)
        outer.addStretch(2)          # a little above center reads better
        # the pane must never set a floor under the window's size: with
        # the default constraint a layout pushes its minimum onto the
        # widget, and this widget is sized by the STAGE. A stage too
        # small for the card simply clips it.
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        self._viewport.installEventFilter(self)
        self.raise_()                # over the viewport, which was here first
        self.refresh()
        self._place()

    # -- what the window tells us -------------------------------------------

    def sync_from_document(self, doc: ProjectDoc) -> None:
        """Show the pane exactly while nothing is loaded (called from the
        window's document-changed pass, beside the other syncs)."""
        showing = doc.score is None
        if showing:
            self.refresh()           # an open in this session moved the list
            self._place()
        self.setVisible(showing)

    def refresh(self) -> None:
        """Rebuild the recent list from the store."""
        self._recents.clear()
        paths = self._files.recents.paths()[:SHOWN_RECENTS]
        for path in paths:
            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self._recents.addItem(item)
        self._recents_heading.setVisible(bool(paths))
        self._recents.setVisible(bool(paths))
        self._empty.setVisible(not paths)
        if paths:
            # exactly as tall as its rows: a list box with empty space
            # under the last entry reads as a scroll area that is not one
            row = self._recents.sizeHintForRow(0)
            self._recents.setFixedHeight(row * len(paths) + 4)

    # -- geometry ------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """The viewport's size. Never consumes anything — this only
        watches."""
        if watched is self._viewport and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Show):
            self._place()
        return False

    def _place(self) -> None:
        """Fill the stage, in the VIEW's coordinates — the pane IS the
        empty stage, so it covers the whole of it."""
        self.setGeometry(self._viewport.geometry())

    # -- the list ------------------------------------------------------------

    def _open_item(self, item: QListWidgetItem) -> None:
        self._files.open_recent(Path(item.data(Qt.ItemDataRole.UserRole)))
