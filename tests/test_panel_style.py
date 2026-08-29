"""The dock panels' shared look (A3), offscreen.

Two things worth a test, both of which used to be wrong and neither of
which an eye catches reliably:

**Nothing clips.** A `QScrollArea` with `widgetResizable` lets its
content be squeezed below the content's own minimum, and Qt then simply
cuts the text — "Entire note value" and the volume "Loud" row were the
two that showed it. The check walks every piece of text in the right
dock at the narrowest width the dock allows and asserts each one still
has the room it asked for.

**The label column is fixed.** Every label in a form is pinned to one
width, so fields line up and no label can be squeezed.

Font metrics differ between machines, so nothing here asserts a pixel
count — only that a widget got at least what it asked for.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QApplication, QCheckBox,  # noqa: E402
                               QFormLayout, QLabel, QRadioButton, QWidget)

from scoreanim.ui import panel_style  # noqa: E402
from scoreanim.ui.app_state import AppState  # noqa: E402
from scoreanim.ui.inspector import Inspector  # noqa: E402

# What we hold to its size hint: plain text that has no way to shrink.
# A combo box or a spin box may be squeezed — it elides, and it is not
# what the ruling is about.
_TEXT = (QLabel, QCheckBox, QRadioButton)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dock(qapp) -> Inspector:
    inspector = Inspector(AppState())
    # Every preset's block on screen: a block hides itself when nothing
    # is using it, and the promise is that none of them clips.
    panel = inspector.effects_panel
    for block in panel.blocks.values():
        block.set_visible(panel._form, True)
    return inspector


def _clipped(root: QWidget) -> list[tuple[str, int, int]]:
    """Every piece of text with less room than it asked for."""
    out = []
    for child in root.findChildren(QWidget):
        if not isinstance(child, _TEXT) or not child.isVisibleTo(root):
            continue
        wraps = isinstance(child, QLabel) and child.wordWrap()
        if not child.text() or wraps:
            continue
        wanted = child.sizeHint().width()
        if wanted > child.width():
            out.append((child.text(), child.width(), wanted))
    return out


def _clipped_in_every_tab(dock, qapp) -> list[tuple[str, int, int]]:
    """Everything clipped anywhere in the dock.

    A tab shows one page at a time and `_clipped` only measures what is
    visible, so the check walks the tabs itself (C1) — otherwise it
    would only ever look at whichever page happens to be in front.
    """
    out = []
    for index in range(dock.tabs.count()):
        dock.tabs.setCurrentIndex(index)
        qapp.processEvents()
        out += _clipped(dock)
    return out


def test_nothing_clips_at_the_narrowest_the_dock_allows(dock, qapp) -> None:
    narrowest = dock.minimumSizeHint().width()
    dock.resize(narrowest, 1600)
    dock.show()
    qapp.processEvents()
    assert _clipped_in_every_tab(dock, qapp) == []


def test_the_dock_cannot_be_squeezed_below_that(dock, qapp) -> None:
    """The scroll area hands the content's minimum back up, so asking
    for a narrower dock does not get one."""
    narrowest = dock.minimumSizeHint().width()
    dock.show()
    dock.resize(narrowest // 2, 1600)
    qapp.processEvents()
    assert dock.width() >= narrowest
    assert _clipped_in_every_tab(dock, qapp) == []


def test_every_label_in_a_form_shares_one_width(dock) -> None:
    form = dock.effects_panel._form
    widths = {label.width() for label in _labels(form)}
    assert len(widths) == 1


def test_the_label_column_fits_the_longest_label(dock) -> None:
    for label in _labels(dock.effects_panel._form):
        assert label.width() >= label.sizeHint().width()


def test_the_shared_spacing_is_what_the_panels_use(dock) -> None:
    form = dock.effects_panel._form
    assert form.contentsMargins().left() == panel_style.PADDING
    assert form.horizontalSpacing() == panel_style.COLUMN_GAP
    assert form.verticalSpacing() == panel_style.ROW_GAP
    # a group is separated from the one above by the group gap, paid
    # above the heading that opens it
    heading = dock.effects_panel.volume.header
    assert heading.contentsMargins().top() == panel_style.GROUP_GAP


def _labels(form: QFormLayout) -> list[QWidget]:
    items = (form.itemAt(row, QFormLayout.ItemRole.LabelRole)
             for row in range(form.rowCount()))
    return [item.widget() for item in items
            if item is not None and item.widget() is not None]
