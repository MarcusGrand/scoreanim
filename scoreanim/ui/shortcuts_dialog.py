"""The Keyboard Shortcuts window (B3): what the app can do, and how to
ask for it.

Two halves, and only one of them is written down here.

**The keys are harvested, not listed.** Every shortcut in the app
belongs to a QAction, and every one of those actions sits in a menu, so
this dialog reads the menu bar when it opens and prints what it finds.
A key that is added, moved or renamed anywhere shows up here without
anybody touching this file — a hand-kept key list is a list that goes
quietly wrong.

It reads the bar at OPEN time, not once at build time, because the
Score menu is empty until a score loads: open the dialog after a load
and the break actions are in it too.

**The gestures are hand-kept**, in `GESTURES` below, because nothing in
Qt knows about them: dragging a note, right-clicking a stave,
double-clicking a text. That list is the one thing to update when the
stage learns a new gesture.

An action with no shortcut is skipped. A row with an empty key column
teaches nobody anything, and enough of them would bury the rows that do.

Keys are shown in the platform's own writing (`NativeText`), so a Mac
reads ⌘E where Windows reads Ctrl+E — which is what the two keyboards
actually have on them.

**A few actions rename themselves**, and their menu text is no name to
list a key under: Undo becomes "Undo import tempo (testscore.tempo)",
and a break action says what it would do to the thing you have
selected. Those actions carry a fixed name for this sheet, set with
`set_sheet_name` where they are built. Nothing here branches on which
action it is looking at — an action either carries the name or it does
not.

`harvest` is handed the menus rather than the menu bar, and never calls
`QAction.menu()` on anything. That call hands shiboken a second Python
wrapper for a menu somebody else already owns, and the C++ menu dies
with the temporary — opening this dialog would empty the menu bar. So
the chrome passes the menu objects it holds (`MainMenus.all_menus`),
and this module only ever reads them.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout,
                               QLabel, QMenu, QScrollArea, QVBoxLayout,
                               QWidget)

from scoreanim.ui import panel_style
from scoreanim.ui.theme import palette

TITLE = "Keyboard Shortcuts"

# The fixed name of an action whose menu text moves with the document.
_SHEET_NAME = "shortcut_sheet_name"


def set_sheet_name(action: QAction, name: str) -> None:
    """Pin what this action is called in the shortcut sheet, for an
    action that renames itself as the document changes."""
    action.setProperty(_SHEET_NAME, name)


@dataclass(frozen=True)
class Row:
    """One line of the dialog: what it does, and what you press."""
    label: str
    keys: str


@dataclass(frozen=True)
class Group:
    """The rows under one heading — one menu, or the gesture list."""
    title: str
    rows: tuple[Row, ...]


# The half Qt cannot tell us about. Everything here is a mouse gesture
# or a key handled by a widget rather than by a QAction, so it would be
# invisible to `harvest` no matter how carefully that was written.
GESTURES = Group("The stage", (
    Row("Select an object", "Click"),
    Row("Deselect", "Click off the score, or Esc"),
    Row("Move the selected object", "Drag"),
    Row("Nudge it", "Arrow keys"),
    Row("Nudge it further", "Shift + Arrow keys"),
    Row("Edit a text where it sits", "Double-click"),
    Row("Hide a stave, in this system or everywhere", "Right-click"),
    Row("Pan the page", "Scroll"),
    Row("Zoom", "Pinch, or Ctrl/⌘ + scroll"),
))


def harvest(menus: Iterable[QMenu]) -> list[Group]:
    """Every shortcut in `menus`, grouped by the menu holding it.

    A menu with no shortcut in it at all is left out rather than shown
    as an empty heading.

    Only the top level of each menu is walked. A submenu action carries
    no shortcut of its own, so it drops out with everything else that
    has no key — and nothing here has to reach into the Score menu's
    per-part submenus, which is the one place the ownership trap above
    would still be waiting.
    """
    groups: list[Group] = []
    for menu in menus:
        rows = _rows(menu)
        if rows:
            groups.append(Group(_clean(menu.title()), rows))
    return groups


def _rows(menu: QMenu) -> tuple[Row, ...]:
    """The shortcut-carrying actions of one menu, in menu order."""
    rows: list[Row] = []
    seen: set[tuple[str, str]] = set()
    for action in menu.actions():
        if action.isSeparator():
            continue
        keys = _keys(action)
        if not keys:
            continue
        row = (_name(action), keys)
        if row in seen:
            continue
        seen.add(row)
        rows.append(Row(*row))
    return tuple(rows)


def _name(action: QAction) -> str:
    """The fixed name if the action carries one, else its menu text."""
    pinned = action.property(_SHEET_NAME)
    return pinned if pinned else _clean(action.text())


def _keys(action: QAction) -> str:
    """An action's key, or its keys — Delete answers to two of them."""
    written = [seq.toString(QKeySequence.SequenceFormat.NativeText)
               for seq in action.shortcuts()]
    return " or ".join(text for text in written if text)


def _clean(text: str) -> str:
    """Drop the mnemonic markers Qt puts in menu titles, keeping a real
    ampersand ("&&") as one."""
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


class ShortcutsDialog(QDialog):
    """A read-only sheet of every key and gesture, built on open."""

    def __init__(self, menus: Iterable[QMenu],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.groups = harvest(menus) + [GESTURES]

        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(panel_style.PADDING, panel_style.PADDING,
                                  panel_style.PADDING, panel_style.PADDING)
        column.setSpacing(panel_style.GROUP_GAP)
        for group in self.groups:
            column.addWidget(_heading(group.title))
            column.addLayout(_table(group.rows))
        column.addStretch(1)

        scroller = QScrollArea()
        scroller.setWidget(body)
        scroller.setWidgetResizable(True)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel_style.lock_min_width(scroller, body)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(scroller)
        root.addWidget(buttons)
        # tall enough for the whole sheet when the screen has room, and
        # scrolling rather than running off the bottom when it does not
        wanted = body.sizeHint().height() + buttons.sizeHint().height() \
            + 3 * panel_style.PADDING
        room = self.screen().availableGeometry().height() - 80
        self.resize(max(self.sizeHint().width(), 460), min(wanted, room))


def _heading(title: str) -> QLabel:
    label = QLabel(title)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def _table(rows: tuple[Row, ...]) -> QGridLayout:
    """Two columns: what it does on the left, the key on the right, and
    the key dim so the eye runs down the descriptions first."""
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(panel_style.GROUP_GAP)
    grid.setVerticalSpacing(panel_style.ROW_GAP)
    grid.setColumnStretch(0, 1)
    for index, row in enumerate(rows):
        keys = QLabel(row.keys)
        keys.setStyleSheet(f"color: {palette.DIM};")
        keys.setAlignment(Qt.AlignmentFlag.AlignRight
                          | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(QLabel(row.label), index, 0)
        grid.addWidget(keys, index, 1)
    return grid
