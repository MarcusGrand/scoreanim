"""The stage's floating zoom controls (D2): out, the percentage, in, Fit.

They sit in the bottom-right corner of the stage, on top of the score,
and they are the only chrome in the app that does that — so they are
see-through (the OVERLAY tokens) and they are only there while the
pointer is over the stage. Move the pointer away and they go, which is
what keeps them out of the way of a score they are sitting on.

Two things they never do. They never take keyboard focus, so clicking
one leaves Esc, the arrows and Space where they were. And they never
decide anything: the buttons drive `StageView.zoom_by` and the same Fit
QAction the View menu holds, and the readout is a plain view of
`StageView.zoom_percent()`, which the view announces with
`zoom_changed`.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QGraphicsView, QHBoxLayout, QLabel,
                               QToolButton, QWidget)

from scoreanim.ui.stage_view import StageView
from scoreanim.ui.stage_zoom import percent_text
from scoreanim.ui.theme import fonts, icons

# One button press. The wheel's notch is x1.1, which is right for a
# gesture you repeat without thinking; a button you click deliberately
# wants to get somewhere in fewer goes.
ZOOM_STEP = 1.25
_MARGIN = 12         # gap from the stage's corner, in device pixels
# The floor under the readout's width, so a step from 100% to 95% does
# not shuffle the buttons sideways. A floor, not a cap: a deep zoom
# reads four digits and the box simply grows, then re-places itself.
_WIDEST = "888%"


class ZoomOverlay(QWidget):
    """Floating zoom controls over one `StageView`."""

    def __init__(self, view: StageView, fit_action: QAction) -> None:
        # A child of the VIEW, beside the viewport, never inside it.
        # QGraphicsView scrolls by calling `viewport()->scroll(dx, dy)`,
        # and that moves the viewport's child widgets along with the
        # picture — controls parented there slide off the screen the
        # first time the user two-finger scrolls (found 2026-08-29).
        super().__init__(view)
        self.setObjectName("ZoomOverlay")
        # a plain QWidget paints no background of its own; this is what
        # lets the stylesheet give it one (and a translucent one)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._view = view
        # kept as a reference, not re-fetched: `eventFilter` still runs
        # while Qt is tearing the window down, and asking a half-deleted
        # view for its viewport then is an error
        self._viewport = view.viewport()
        # the pointer is "on the stage" while it is over either of
        # these; the overlay covers part of the viewport, so moving onto
        # it sends the viewport a Leave — without the second flag the
        # controls would vanish as you reached for them
        self._over_stage = False
        self._over_self = False

        self._out = _button(icons.icon("zoom-out"), "Zoom out",
                            lambda: self._step(1.0 / ZOOM_STEP))
        self._in = _button(icons.icon("zoom-in"), "Zoom in",
                           lambda: self._step(ZOOM_STEP))
        self._readout = QLabel(percent_text(0))
        self._readout.setObjectName("ZoomPercent")
        self._readout.setFont(fonts.monospace())
        self._readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._readout.setMinimumWidth(
            self._readout.fontMetrics().horizontalAdvance(_WIDEST))
        self._fit = QToolButton(self)
        self._fit.setDefaultAction(fit_action)   # the View menu's own
        self._fit.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._fit.setIconSize(icons.BUTTON_SIZE)
        self._fit.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        row = QHBoxLayout(self)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(2)
        for widget in (self._out, self._readout, self._in, self._fit):
            widget.setParent(self)
            row.addWidget(widget)

        view.zoom_changed.connect(self.refresh)
        self._viewport.installEventFilter(self)
        self.raise_()          # over the viewport, which was here first
        self.hide()
        self.refresh()

    # -- what the view tells us --------------------------------------------

    def refresh(self) -> None:
        """Re-read the view's zoom, and drop the controls if there is
        nothing on the stage to zoom."""
        value = self._view.zoom_percent()
        self._readout.setText(percent_text(value))
        self._place()
        self._apply_visibility()

    # -- showing and hiding -------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """The viewport's pointer and size. Never consumes anything —
        this only watches."""
        if watched is self._viewport:
            kind = event.type()
            if kind == QEvent.Type.Enter:
                self._over_stage = True
                self._apply_visibility()
            elif kind == QEvent.Type.Leave:
                self._over_stage = False
                self._apply_visibility()
            elif kind in (QEvent.Type.Resize, QEvent.Type.Show):
                self._place()
        return False

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._over_self = True
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._over_self = False
        self._apply_visibility()
        super().leaveEvent(event)

    def _apply_visibility(self) -> None:
        """Visible only while the pointer is on the stage AND there is a
        score there. Hidden means hidden, not transparent — an invisible
        widget still on top would eat a click meant for the score."""
        self.setVisible((self._over_stage or self._over_self)
                        and self._view.scene() is not None)

    def _place(self) -> None:
        """Bottom-right of the stage, one margin in — in the VIEW's
        coordinates, since that is what the controls are a child of.
        Fixed there: scrolling and zooming move the score under them,
        never them."""
        self.adjustSize()
        area = self._viewport.geometry()
        self.move(area.right() - self.width() - _MARGIN + 1,
                  area.bottom() - self.height() - _MARGIN + 1)

    # -- the buttons --------------------------------------------------------

    def _step(self, factor: float) -> None:
        """Zoom one press worth, about the middle of the stage.

        The view normally zooms about the pointer, which is right for a
        pinch and wrong here: the pointer is on a button in the corner,
        so the score would run away from it. The anchor is put back
        straight after, so the next pinch behaves as it always did."""
        anchor = self._view.transformationAnchor()
        self._view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter)
        try:
            self._view.zoom_by(factor)
        finally:
            self._view.setTransformationAnchor(anchor)


def _button(icon, tip: str, on_click) -> QToolButton:
    """One overlay button: icon only, no focus, no keyboard shortcut of
    its own (the wheel and the pinch are the fast paths)."""
    button = QToolButton()
    button.setIcon(icon)
    button.setToolTip(tip)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setIconSize(icons.BUTTON_SIZE)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.clicked.connect(on_click)
    return button
