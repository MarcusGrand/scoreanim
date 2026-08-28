"""One look for every form in the three docks: spacing, and a label
column that never squeezes.

Two jobs, both of which were being done slightly differently in every
panel.

**Spacing.** Four numbers, written down once. A panel calls
`style_form` and gets the same padding and the same gaps as the panel
above it, instead of its own `(8, 2, 8, 6)`.

**A fixed label column.** A `QFormLayout` sizes its label column to
whatever fits, so the same field started at a different x in every
section, and a squeezed dock shrank the labels until the text was cut
off. `fix_label_column` measures the widest label in a form once and
pins every label to that width, so the fields line up and no label can
be squeezed.

That leaves the other half of the clipping: a `QScrollArea` with
`widgetResizable` deliberately lets its content be squeezed below the
content's own minimum, which is what cut "Entire note value" and the
volume "Loud" row in half at the dock's default width. `lock_min_width`
puts that minimum back, so the dock cannot be made narrower than the
widest thing in it.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFormLayout, QLayout, QScrollArea, QWidget)

# The four numbers. PADDING is the breathing room inside a panel on
# every side; GROUP_GAP separates two groups of controls (two sections
# in a dock, two clusters on the transport strip); ROW_GAP is one row to
# the next, and COLUMN_GAP a label to its field.
PADDING = 8
GROUP_GAP = 12
ROW_GAP = 6
COLUMN_GAP = 8

# Room for the label column even when every label in a form is short, so
# two sections still line up with each other. In characters of the app's
# own font, not pixels — a bigger system font gets a wider column.
_MIN_LABEL_CHARS = 9

# A field never squeezed down to the arrows alone. Same units.
_MIN_FIELD_CHARS = 7


def style_form(form: QFormLayout, padding: bool = True) -> None:
    """The shared spacing, and fields that grow with the dock.

    `padding=False` for a form nested inside a panel that has already
    paid the padding at its own edge.
    """
    margin = PADDING if padding else 0
    form.setContentsMargins(margin, margin, margin, margin)
    form.setHorizontalSpacing(COLUMN_GAP)
    form.setVerticalSpacing(ROW_GAP)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft
                           | Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(Qt.AlignmentFlag.AlignLeft
                          | Qt.AlignmentFlag.AlignTop)
    # A row is never allowed to wrap its field under its label: the
    # label column is fixed, so wrapping would break the alignment it
    # buys — the dock gets a minimum width instead (`lock_min_width`).
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
    form.setFieldGrowthPolicy(
        QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)


def fix_label_column(form: QFormLayout) -> int:
    """Pin every label in `form` to one width, and return it.

    Call it once the form has all its rows. The width is the widest
    label the form holds, floored at `_MIN_LABEL_CHARS`, so nothing is
    cut off and a short form still lines up with a long one.
    """
    labels = _labels(form)
    if not labels:
        return 0
    floor = _chars(labels[0], _MIN_LABEL_CHARS)
    width = max([floor] + [label.sizeHint().width() for label in labels])
    return set_label_column(form, width)


def set_label_column(form: QFormLayout, width: int) -> int:
    """Pin every label in `form` to a width somebody else measured — for
    two forms that have to line up with each other."""
    for label in _labels(form):
        label.setFixedWidth(width)
    return width


def _labels(form: QFormLayout) -> list[QWidget]:
    """The label widget of every row that has one."""
    items = (form.itemAt(row, QFormLayout.ItemRole.LabelRole)
             for row in range(form.rowCount()))
    return [item.widget() for item in items
            if item is not None and item.widget() is not None]


def min_field_width(widget: QWidget) -> int:
    """A sensible floor for a field that would otherwise collapse to its
    arrows — a spin box sharing its row with something else."""
    return _chars(widget, _MIN_FIELD_CHARS)


def lock_min_width(scroller: QScrollArea, body: QWidget) -> None:
    """Stop a scrolled dock from squeezing its content into clipping.

    `setWidgetResizable(True)` lets a `QScrollArea` shrink its child
    below the child's own minimum width, and Qt then simply cuts the
    text inside it — with the horizontal scrollbar switched off there is
    not even a way to scroll to what was cut. This hands the child's
    minimum back to the scroll area, plus room for the vertical bar,
    which is what stops the dock at a width everything still fits in.
    """
    bar = scroller.verticalScrollBar().sizeHint().width()
    scroller.setMinimumWidth(body.minimumSizeHint().width() + bar + 2)


def natural_width(layout: QLayout) -> int:
    """What a layout wants while everything in it is showing.

    A panel that hides rows (a preset's block of options) measures this
    while it is still whole, so its minimum width is the widest it can
    ever get to be, not the widest it happens to be right now.
    """
    return layout.sizeHint().width()


def _chars(widget: QWidget, count: int) -> int:
    """`count` characters wide in the widget's own font."""
    return widget.fontMetrics().averageCharWidth() * count
