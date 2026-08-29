"""The app-wide QSS: what the palette cannot say.

Docks, the toolbar, our own section headers, field padding, scrollbars,
the flat look of a menu bar. One string, written with `$TOKEN`
placeholders (string.Template) rather than an f-string: QSS is mostly
braces, and doubling every one of them would make this unreadable.

Deliberately NOT styled: check and radio indicators, spin box arrows,
combo box arrows. Styling those subcontrols makes Qt stop drawing its
own glyph, and we would have to ship an image for a tick mark. Fusion
draws them from the palette, which is dark enough already.
"""
from __future__ import annotations

from string import Template

from scoreanim.ui.theme import palette as tokens


def stylesheet() -> str:
    """The app-wide QSS, with every `$TOKEN` filled in from the palette."""
    names = {name: value for name, value in vars(tokens).items()
             if name.isupper() and isinstance(value, str)}
    return _QSS.substitute(names)


_QSS = Template("""
QMainWindow {
    background: $WINDOW;
}
QMainWindow::separator {
    background: $BORDER;
    width: 1px;
    height: 1px;
}
QToolTip {
    background: $PANEL;
    color: $TEXT;
    border: 1px solid $BORDER;
    padding: 3px 6px;
}

/* -- chrome ------------------------------------------------------- */

QMenuBar {
    background: $WINDOW;
    border-bottom: 1px solid $BORDER;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
}
QMenuBar::item:selected {
    background: $HOVER;
}
QMenu {
    background: $PANEL;
    border: 1px solid $BORDER;
    padding: 4px;
}
QMenu::item {
    padding: 4px 22px 4px 22px;
}
QMenu::item:selected {
    background: $HIGHLIGHT;
}
QMenu::item:disabled {
    color: $DISABLED;
}
QMenu::separator {
    height: 1px;
    background: $BORDER;
    margin: 4px 6px;
}

QToolBar {
    background: $PANEL;
    border: 0px;
    border-bottom: 1px solid $BORDER;
    padding: 3px;
    spacing: 4px;
}
QToolBar::separator {
    background: $BORDER;
    width: 1px;
    margin: 4px 6px;
}

QStatusBar {
    background: $WINDOW;
    border-top: 1px solid $BORDER;
    color: $DIM;
}
QStatusBar::item { border: 0px; }

QDockWidget {
    background: $PANEL;
    color: $DIM;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}
QDockWidget::title {
    background: $WINDOW;
    border-bottom: 1px solid $BORDER;
    padding: 5px 8px;
    text-align: left;
}
QDockWidget > QWidget {
    background: $PANEL;
}

/* -- our own section headers -------------------------------------- */

/* A flat band the full width of the panel, not a button: no frame, no
   rounding, text pinned left beside its chevron, and a highlight that
   runs edge to edge under the pointer.

   The band is also where one section ends and the next begins: it sits
   a shade darker than the body below it — the same darker ground a
   dock title bar uses — with a single 1px line along its top.

   One line, not two. A line above AND below would draw a box around
   the heading, which reads as enclosing the title rather than dividing
   the sections; the whole job of the line is to say "the section above
   ended here". The band's own edge against the lighter body is what
   closes it off at the bottom. */
QPushButton#SectionHeader {
    background: $WINDOW;
    color: $DIM;
    border: 0px solid $BORDER;
    border-top-width: 1px;
    border-radius: 0px;
    padding: 6px 8px;
    font-weight: 600;
    text-align: left;
}
QPushButton#SectionHeader[topmost="true"] {
    /* the section at the top of a stack has nothing above it to be
       separated from, and in a dock its line would land straight on
       the title bar's own */
    border-top-width: 0px;
}
QPushButton#SectionHeader:hover {
    background: $HOVER;
    color: $TEXT;
}
QPushButton#SectionHeader:pressed {
    background: $PRESSED;
}
QPushButton#SectionHeader:checked {
    /* expanded, not "active": a header must not take the accent, and
       it keeps its line — that is the divider */
    background: $WINDOW;
    color: $TEXT;
}
QPushButton#SectionHeader:checked:hover {
    background: $HOVER;
}
QLabel#ZoneHeading {
    background: transparent;
    color: $DIM;
    font-weight: 600;
    padding: 2px 0px;
}

/* -- controls ----------------------------------------------------- */

QPushButton, QToolButton {
    background: $PANEL;
    color: $TEXT;
    border: 1px solid $BORDER;
    border-radius: 3px;
    padding: 4px 10px;
}
QPushButton:hover, QToolButton:hover {
    background: $HOVER;
}
QPushButton:pressed, QToolButton:pressed {
    background: $PRESSED;
}
QPushButton:checked, QToolButton:checked {
    background: $PRESSED;
    color: $ACCENT;
    border-color: $ACCENT;
}
QPushButton:disabled, QToolButton:disabled {
    color: $DISABLED;
    border-color: $BORDER;
}
QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
}
QToolBar QToolButton:hover {
    background: $HOVER;
    border-color: $BORDER;
}
QToolBar QToolButton:disabled {
    /* a toolbar button draws no frame; a disabled one must not be the
       only one that does */
    border-color: transparent;
}

/* The one filled button in the app: Export is what the whole session
   is aimed at, so it is the only thing wearing the accent (B2). It
   goes flat and grey until a score is loaded. */
QToolBar QToolButton#ExportButton {
    background: $ACCENT;
    color: $WINDOW;
    border: 1px solid $ACCENT;
    border-radius: 3px;
    padding: 3px 12px;
    font-weight: 600;
}
QToolBar QToolButton#ExportButton:hover {
    background: $ACCENT_HOVER;
    border-color: $ACCENT_HOVER;
}
QToolBar QToolButton#ExportButton:pressed {
    background: $ACCENT_PRESSED;
    border-color: $ACCENT_PRESSED;
}
QToolBar QToolButton#ExportButton:disabled {
    background: transparent;
    color: $DISABLED;
    border-color: $BORDER;
}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox,
QComboBox, QAbstractSpinBox {
    background: $INSET;
    color: $TEXT;
    border: 1px solid $BORDER;
    border-radius: 3px;
    padding: 2px 5px;
    selection-background-color: $HIGHLIGHT;
    selection-color: $TEXT;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QAbstractSpinBox:focus, QPlainTextEdit:focus {
    border-color: $ACCENT;
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QComboBox:disabled, QAbstractSpinBox:disabled {
    color: $DISABLED;
    background: $WINDOW;
}
QComboBox QAbstractItemView {
    background: $PANEL;
    border: 1px solid $BORDER;
    selection-background-color: $HIGHLIGHT;
}

QAbstractItemView, QListWidget, QListView, QTreeView, QTableView {
    background: $INSET;
    alternate-background-color: $PANEL;
    border: 1px solid $BORDER;
    selection-background-color: $HIGHLIGHT;
    selection-color: $TEXT;
    outline: 0;
}
QListWidget::item, QListView::item, QTreeView::item {
    padding: 2px 4px;
}
QHeaderView::section {
    background: $PANEL;
    color: $DIM;
    border: 0px;
    border-right: 1px solid $BORDER;
    padding: 3px 6px;
}

QGroupBox {
    border: 1px solid $BORDER;
    border-radius: 3px;
    margin-top: 10px;
    padding-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0px 3px;
    color: $DIM;
}

QTabWidget::pane {
    background: $PANEL;
    border: 1px solid $BORDER;
    top: -1px;
}
QTabBar::tab {
    background: $WINDOW;
    color: $DIM;
    border: 1px solid $BORDER;
    padding: 5px 12px;
}
QTabBar::tab:selected {
    background: $PANEL;
    color: $TEXT;
    border-bottom-color: $PANEL;
}
QTabBar::tab:hover {
    color: $TEXT;
}

/* The inspector's three tabs (C1) sit right under the dock title bar,
   so they are drawn as a row of headings rather than as folder tabs:
   no frames, no pane border, the selected one lit by the body colour
   under it and an underline. This is the one place the accent marks a
   heading, because here it is answering "which tab am I in" — the same
   question the glow answers on the stage. */
QTabWidget#InspectorTabs::pane {
    background: $PANEL;
    border: 0px;
}
QTabWidget#InspectorTabs > QTabBar {
    background: $WINDOW;
}
QTabWidget#InspectorTabs > QTabBar::tab {
    background: $WINDOW;
    color: $DIM;
    border: 0px;
    border-bottom: 2px solid transparent;
    padding: 6px 12px;
    font-weight: 600;
}
QTabWidget#InspectorTabs > QTabBar::tab:hover {
    background: $HOVER;
    color: $TEXT;
}
QTabWidget#InspectorTabs > QTabBar::tab:selected {
    background: $PANEL;
    color: $TEXT;
    border-bottom: 2px solid $ACCENT;
}

QScrollArea, QAbstractScrollArea {
    background: $PANEL;
    border: 0px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: $BORDER;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:hover {
    background: $DIM;
}
QScrollBar::add-line, QScrollBar::sub-line {
    height: 0px;
    width: 0px;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}

QSlider::groove:horizontal {
    background: $INSET;
    border: 1px solid $BORDER;
    border-radius: 2px;
    height: 4px;
}
QSlider::sub-page:horizontal {
    background: $PLAYHEAD;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: $TEXT;
    border: 0px;
    width: 10px;
    margin: -5px 0px;
    border-radius: 5px;
}
QSlider::handle:horizontal:hover {
    background: $ACCENT;
}
QSlider::groove:vertical {
    background: $INSET;
    border: 1px solid $BORDER;
    width: 4px;
}

QSplitter::handle {
    background: $BORDER;
}
QProgressBar {
    background: $INSET;
    border: 1px solid $BORDER;
    border-radius: 3px;
    text-align: center;
}
QProgressBar::chunk {
    background: $PLAYHEAD;
}
""")
