"""Selection panel (M2.5): what is selected on the stage.

The inspector's Selection section body. A pure readout — M2 makes the
selection EXIST and nothing else; the editing controls that will live
here (per-element color/effect, clear-overrides) are M3.

Unlike EffectsPanel this panel is driven by TRANSIENT state, so it
subscribes to app_state.selection_changed itself instead of riding the
window's document pass. The precedent is Inspector.follow_action, which
is deliberately absent from sync_from_document for the same reason:
there is nothing in the document to resync from.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFormLayout, QLabel, QSizePolicy, QStackedWidget,
                               QWidget)

from scoreanim.core.score.identity import ElementIdentity
from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.selection import measure_ordinal_of
from scoreanim.ui.app_state import AppState

_EMPTY = "—"

# Row order is musical: what it is, whose it is, where it is, when.
_ROWS = ("Kind", "Part", "Staff", "Voice", "Measure", "Onset", "Extent")


class SelectionPanel(QWidget):
    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state

        self._empty = QLabel("Nothing selected")
        self._empty.setEnabled(False)

        self._values: dict[str, QLabel] = {}
        details = QWidget()
        form = QFormLayout(details)
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        for row in _ROWS:
            value = QLabel(_EMPTY)
            value.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            self._values[row] = value
            form.addRow(row, value)
        # the raw id: the debugging handle, and what an override would be
        # keyed by — dimmed, selectable, wrapping
        self._eid = QLabel(_EMPTY)
        self._eid.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._eid.setWordWrap(True)
        self._eid.setEnabled(False)
        self._eid.setSizePolicy(QSizePolicy.Policy.Ignored,
                                QSizePolicy.Policy.Preferred)
        form.addRow("Id", self._eid)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._empty)
        self._stack.addWidget(details)
        outer = QFormLayout(self)
        outer.setContentsMargins(8, 2, 8, 6)
        outer.addRow(self._stack)

        app_state.selection_changed.connect(self._on_selection_changed)
        self._on_selection_changed()

    # -- readout -----------------------------------------------------------

    def _on_selection_changed(self) -> None:
        identity = self._state.selected
        if identity is None:
            self._stack.setCurrentWidget(self._empty)
            return
        self._fill(identity)
        self._stack.setCurrentIndex(1)

    def _fill(self, identity: ElementIdentity) -> None:
        set_ = self._values
        set_["Kind"].setText(_kind_label(identity))
        set_["Part"].setText(identity.part_name or _text(identity.part))
        set_["Staff"].setText(_text(identity.staff))
        set_["Voice"].setText(_text(identity.voice))
        set_["Measure"].setText(
            _measure_label(identity, self._state.measures))
        set_["Onset"].setText(_beats(identity.onset))
        set_["Extent"].setText(_extent(identity.extent))
        self._eid.setText(str(identity.element_id))
        self._eid.setToolTip(str(identity.element_id))


def _text(value: object) -> str:
    return _EMPTY if value is None else str(value)


def _kind_label(identity: ElementIdentity) -> str:
    """Title-cased kind, and for a system-broken spanner the segment it
    is: an override targets ONE :seg, so the panel must not pretend the
    whole slur is selected."""
    label = identity.kind.name.replace("_", " ").title()
    tail = str(identity.element_id).rsplit(":", 1)[-1]
    if tail.startswith("seg"):
        label = f"{label} (segment {tail[3:]})"
    return label


def _beats(onset: float | None) -> str:
    return _EMPTY if onset is None else f"{onset:g}"


def _extent(extent: tuple[float, float] | None) -> str:
    if extent is None:
        return _EMPTY
    return f"{extent[0]:g} – {extent[1]:g}"


def _measure_label(identity: ElementIdentity,
                   measures: tuple[MeasureInfo, ...]) -> str:
    """The document-order ordinal parsed out of the id, plus the PRINTED
    number when the two differ (a Dorico "X0" pickup makes them differ
    for the whole score). System-scoped and page-furniture ids have no
    measure at all."""
    ordinal = measure_ordinal_of(identity.element_id)
    if ordinal is None:
        return _EMPTY
    if 1 <= ordinal <= len(measures):
        printed = measures[ordinal - 1].number
        if printed != ordinal:
            return f"{ordinal}  (printed {printed})"
    return str(ordinal)
