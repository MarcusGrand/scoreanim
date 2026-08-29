"""Selection panel (M2.5, restructured M2.8): what is selected on the
stage, and what that selection carries.

The inspector's Selection section body: a readout, and since M3.3 the
editing controls under it (`selection_style.py` — per-element or
per-part colour/effect, and the cheap reset). The readout stays here and
the writes stay there, so this file remains a description of what is
selected and never grows into a form.

Two blocks, because rule 13 draws exactly this line. The OBJECT block is
what the user picked. The CONTEXT block below it — part and measure — is
derived from the object's id and shown captioned as carried, not chosen;
a measure is never a selection target, so it must never look like one.
The stage shows only the object (ruling 2026-07-27: the implicit levels
are panel-only, so nothing on the page can read as a second selection).

Unlike EffectsPanel this panel is driven by TRANSIENT state, so it
subscribes to app_state.selection_changed itself instead of riding the
window's document pass. The precedent is the view router's page/system
position, which is deliberately absent from the document for the same
reason: there is nothing in there to resync from.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFormLayout, QFrame, QLabel, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from scoreanim.core.score.identity import ElementIdentity
from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.selection import Selection
from scoreanim.ui import panel_style, tips
from scoreanim.ui.app_state import AppState
from scoreanim.ui.panels.selection_style import SelectionStyleControls
from scoreanim.ui.panels.selection_trigger import SelectionTriggerControls

_EMPTY = "—"

# What you picked: what it is, where on the staff, when it sounds.
_OBJECT_ROWS = ("Kind", "Staff", "Voice", "Onset", "Extent")
# What that pick carries. Both derived from the id, never chosen.
_CONTEXT_ROWS = ("Part", "Measure")
_CONTEXT_CAPTION = "carries"

# What each row means, in one sentence. Every row is here on purpose:
# a readout nobody can explain is a readout nobody can use, and the
# table being complete is what `tests/test_tooltips.py` leans on.
_ROW_TIPS = {
    "Kind": "What you picked — a note, a slur, a dynamic, a text",
    "Staff": "Which staff of its part the object sits on",
    "Voice": "Which voice on that staff",
    "Onset": "The beat it sounds on, counted along the performance",
    "Extent": "The beats it runs over, for something that lasts",
    "Part": "The player it belongs to — carried by the pick, not chosen",
    "Measure": "The bar it is in — carried by the pick, not chosen",
}
_ID_TIP = ("The id an override is keyed by. Select it with the mouse to "
           "copy it.")


class SelectionPanel(QWidget):
    def __init__(self, app_state: AppState,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = app_state

        # Empty state (C3): the tab now comes to the front on its own,
        # so somebody will land here with nothing selected. It says what
        # to do about that. Wrapping, and free to be narrower than its
        # text, so one sentence cannot set the dock's minimum width.
        self._empty = QLabel("Nothing selected — click a note on the "
                             "stage.")
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._empty.setSizePolicy(QSizePolicy.Policy.Ignored,
                                  QSizePolicy.Policy.Preferred)
        self._empty.setEnabled(False)

        self._values: dict[str, QLabel] = {}
        self._forms: list[QFormLayout] = []
        details = QWidget()
        outer_details = QVBoxLayout(details)
        outer_details.setContentsMargins(0, 0, 0, 0)
        outer_details.setSpacing(panel_style.GROUP_GAP)

        form = self._add_form(outer_details)
        for row in _OBJECT_ROWS:
            form.addRow(self._row_label(row), self._value_label(row))
        # the raw id: the debugging handle, and what an override would be
        # keyed by — dimmed, selectable, wrapping
        self._eid = QLabel(_EMPTY)
        self._eid.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._eid.setWordWrap(True)
        self._eid.setEnabled(False)
        self._eid.setSizePolicy(QSizePolicy.Policy.Ignored,
                                QSizePolicy.Policy.Preferred)
        tips.describe(self._eid, _ID_TIP)
        id_label = QLabel("Id")
        tips.describe(id_label, _ID_TIP)
        form.addRow(id_label, self._eid)

        # the seam between chosen and carried, drawn: a rule, then a
        # dimmed caption, then the derived rows
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        outer_details.addWidget(line)
        caption = QLabel(_CONTEXT_CAPTION)
        caption.setEnabled(False)
        tips.describe(caption,
                      "Derived from what you picked, and never selectable "
                      "on its own")
        outer_details.addWidget(caption)

        context = self._add_form(outer_details)
        for row in _CONTEXT_ROWS:
            context.addRow(self._row_label(row), self._value_label(row))

        # the writes (M3.3), below the description of what they act on
        edit_line = QFrame()
        edit_line.setFrameShape(QFrame.Shape.HLine)
        edit_line.setFrameShadow(QFrame.Shadow.Sunken)
        outer_details.addWidget(edit_line)
        self.trigger_controls = SelectionTriggerControls(app_state)
        outer_details.addWidget(self.trigger_controls)
        self.style_controls = SelectionStyleControls(app_state)
        outer_details.addWidget(self.style_controls)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._empty)
        self._stack.addWidget(details)
        outer = QFormLayout(self)
        panel_style.style_form(outer)
        outer.addRow(self._stack)

        # one label column across both readout blocks, so "Kind" above
        # and "Measure" below start their values at the same x
        width = max(panel_style.fix_label_column(f) for f in self._forms)
        for form in self._forms:
            panel_style.set_label_column(form, width)

        app_state.selection_changed.connect(self._on_selection_changed)
        self._on_selection_changed()

    # -- construction helpers ----------------------------------------------

    def _add_form(self, parent: QVBoxLayout) -> QFormLayout:
        """A readout block. The padding is paid once at the panel's own
        edge, so these forms sit flush inside it."""
        block = QWidget()
        form = QFormLayout(block)
        panel_style.style_form(form, padding=False)
        parent.addWidget(block)
        self._forms.append(form)
        return form

    def _row_label(self, row: str) -> QLabel:
        """The row's name, carrying the row's sentence — the pointer
        lands on the name or on the value and gets the same answer."""
        label = QLabel(row)
        tips.describe(label, _ROW_TIPS[row])
        return label

    def _value_label(self, row: str) -> QLabel:
        value = QLabel(_EMPTY)
        tips.describe(value, _ROW_TIPS[row])
        value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._values[row] = value
        return value

    # -- readout -----------------------------------------------------------

    def _on_selection_changed(self) -> None:
        selection = self._state.selection
        if selection is None:
            self._stack.setCurrentWidget(self._empty)
            return
        self._fill(selection)
        self._stack.setCurrentIndex(1)

    def _fill(self, selection: Selection) -> None:
        """Object rows off the identity; context rows off the Selection's
        derived properties, never off the identity's fields directly —
        one source of truth for what a pick carries (rule 13)."""
        obj = selection.obj
        set_ = self._values
        set_["Kind"].setText(_kind_label(obj))
        set_["Staff"].setText(_text(obj.staff))
        set_["Voice"].setText(_text(obj.voice))
        set_["Onset"].setText(_beats(obj.onset))
        set_["Extent"].setText(_extent(obj.extent))
        set_["Part"].setText(
            selection.part_name or _text(selection.part))
        set_["Measure"].setText(
            _measure_label(selection, self._state.measures))
        self._eid.setText(str(obj.element_id))


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


def _measure_label(selection: Selection,
                   measures: tuple[MeasureInfo, ...]) -> str:
    """The document-order ordinal the selection carries, plus the PRINTED
    number when the two differ (a Dorico "X0" pickup makes them differ
    for the whole score). System-scoped and page-furniture ids have no
    measure at all."""
    ordinal = selection.measure_ordinal
    if ordinal is None:
        return _EMPTY
    if 1 <= ordinal <= len(measures):
        printed = measures[ordinal - 1].number
        if printed != ordinal:
            return f"{ordinal}  (printed {printed})"
    return str(ordinal)
