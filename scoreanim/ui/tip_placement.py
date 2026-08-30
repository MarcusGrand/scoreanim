"""Where the hover box sits: always to the RIGHT of the pointer.

Marcus, 2026-08-30. A tooltip should read away from the pointer in one
direction — the box starts at the cursor and runs right — so the eye
always knows where the first word is. Near the right edge of the screen
the box slides left until it fits, and the pointer then sits somewhere
along it. What must never happen is the box jumping to the OTHER side
of the pointer, because then the same gesture puts the text in two
different places depending on where you happened to be.

Qt does exactly that jump. `QTipLabel::placeTip` offsets the box a
couple of pixels right of the cursor, and if that would overrun the
screen it moves the whole box to the left of the cursor
(`p.rx() -= 4 + width`) before a later clamp. So this module takes the
horizontal placement back: `tip_left` is the rule, pure and headless,
and `TipPlacement` is an application-wide event filter that applies it
to Qt's own tooltip window.

Only the x is ours. Qt's vertical behaviour — drop below the pointer,
lift above it near the bottom of the screen — is right already, and
leaving it alone keeps this to one job.

The box's LOOK is not here: it is `ui/theme/palette.py` (the three TIP
tokens) and the `QToolTip` rule in `ui/theme/stylesheet.py`.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QWidget

# How far right of the pointer the box's left edge starts. Qt's own
# number, kept so the box sits where a Qt user expects it to.
CURSOR_GAP = 2

# Qt's tooltip window. There is no public class for it, so it is found
# by the name its metaobject carries — the same handle Qt's own test
# suite uses.
TIP_CLASS = "QTipLabel"


def tip_left(cursor_x: int, tip_width: int,
             screen_left: int, screen_right: int) -> int:
    """The x of the box's left edge.

    `screen_right` is one past the last usable pixel, so a box exactly
    as wide as the screen lands at `screen_left`.

    The box starts at the pointer and runs right. If it would overrun,
    it slides left just far enough to fit — never to the other side of
    the pointer. A box wider than the screen is pinned to the left edge
    and overruns on the right, which is the only way it can be read
    from its first word.
    """
    x = cursor_x + CURSOR_GAP
    if x + tip_width > screen_right:
        x = screen_right - tip_width
    return max(x, screen_left)


class TipPlacement(QObject):
    """Puts Qt's tooltip window where `tip_left` says, and nothing else.

    Installed on the QApplication, so it sees every widget's events and
    picks out the one window it cares about. Three events, and all
    three are needed:

    - **Move**, because Qt places the box before showing it, and places
      it AGAIN with no second show when the pointer travels to another
      control while a box is already up (`QTipLabel::reuseTip`).
    - **Resize**, because whether a box fits depends on its width, and
      the stylesheet's padding is applied AFTER Qt has placed it — a
      correction made before that lands two pixels out (measured).
    - **Show**, as the backstop for a box that is neither moved nor
      resized on its way up.

    Moving the box is itself a move, so the correction would loop — the
    guard is that it only moves a box that is not already where it
    belongs, and after one correction it is.
    """

    _WATCHED = (QEvent.Type.Show, QEvent.Type.Move, QEvent.Type.Resize)

    def eventFilter(self, watched: QObject,  # noqa: N802 (Qt naming)
                    event: QEvent) -> bool:
        if (event.type() in self._WATCHED and isinstance(watched, QWidget)
                and watched.metaObject().className() == TIP_CLASS):
            self.place(watched)
        return False                 # this only watches; it consumes nothing

    @staticmethod
    def place(tip: QWidget) -> None:
        """Correct one box's x. Public so a test can drive it without
        conjuring a real hover."""
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) \
            or QGuiApplication.primaryScreen()
        if screen is None:           # no screen at all: nothing to fit into
            return
        # the AVAILABLE geometry, so a box near the bottom-right does not
        # slide under the dock or the taskbar
        area = screen.availableGeometry()
        wanted = tip_left(cursor.x(), tip.width(),
                          area.left(), area.left() + area.width())
        if tip.x() != wanted:
            tip.move(wanted, tip.y())


def install(app) -> TipPlacement:
    """Take over tooltip placement for this application.

    Parented to `app`, which is what keeps it alive — an event filter
    whose last Python reference is dropped stops filtering.
    """
    placement = TipPlacement(app)
    app.installEventFilter(placement)
    return placement
