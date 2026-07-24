"""CollapsibleSection (M1.2), offscreen: header toggle flips content
visibility, programmatic set_expanded stays in sync with the header."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from scoreanim.ui.collapsible import CollapsibleSection  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def section(qapp) -> CollapsibleSection:
    s = CollapsibleSection("Playback & Sync")
    s.set_content(QLabel("body"))
    s.show()  # offscreen; visibility propagation needs a shown parent
    return s


def test_starts_expanded_with_visible_content(section) -> None:
    assert section.expanded
    assert section._content.isVisible()
    assert section._header.arrowType() == Qt.ArrowType.DownArrow


def test_header_click_toggles_content(section) -> None:
    section._header.click()
    assert not section.expanded
    assert not section._content.isVisible()
    assert section._header.arrowType() == Qt.ArrowType.RightArrow
    section._header.click()
    assert section.expanded
    assert section._content.isVisible()
    assert section._header.arrowType() == Qt.ArrowType.DownArrow


def test_set_expanded_drives_header_and_content(section) -> None:
    section.set_expanded(False)
    assert not section._header.isChecked()
    assert not section._content.isVisible()
    section.set_expanded(True)
    assert section._header.isChecked()
    assert section._content.isVisible()


def test_content_installed_while_collapsed_stays_hidden(qapp) -> None:
    s = CollapsibleSection("Selection")
    s.set_expanded(False)
    s.set_content(QLabel("nothing selected"))
    s.show()
    assert not s._content.isVisible()
    s.set_expanded(True)
    assert s._content.isVisible()


def test_set_content_replaces_previous(section) -> None:
    replacement = QLabel("new body")
    section.set_content(replacement)
    assert section._content is replacement
    assert replacement.isVisible()
