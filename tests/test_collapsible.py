"""CollapsibleSection (M1.2), offscreen: header toggle flips content
visibility, programmatic set_expanded stays in sync with the header, the
header band shows the chevron that says which way it is folded (A3), and
the band is the seam that keeps two open sections apart."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QApplication, QLabel,  # noqa: E402
                               QVBoxLayout, QWidget)

from scoreanim.ui.collapsible import CollapsibleSection  # noqa: E402
from scoreanim.ui.theme import build_palette, icons, stylesheet  # noqa: E402
from scoreanim.ui.theme import palette as tokens  # noqa: E402


def _chevron(section) -> int:
    """Which drawing the header is showing. `plain_icon` is cached, so
    the same name hands back the same QIcon and its key compares."""
    return section._header.icon().cacheKey()


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
    assert _chevron(section) == icons.plain_icon("chevron-down").cacheKey()


def test_header_click_toggles_content(section) -> None:
    section._header.click()
    assert not section.expanded
    assert not section._content.isVisible()
    assert _chevron(section) == icons.plain_icon("chevron-right").cacheKey()
    section._header.click()
    assert section.expanded
    assert section._content.isVisible()
    assert _chevron(section) == icons.plain_icon("chevron-down").cacheKey()


def test_the_header_is_a_flat_full_width_band(section) -> None:
    """A heading you can click, not a control: no frame, and it takes
    the whole width of whatever it is put in (A3)."""
    header = section._header
    assert header.objectName() == "SectionHeader"     # the QSS hook
    assert header.isFlat()
    assert not header.autoDefault()
    section.resize(400, 60)
    assert header.width() == section.width()


def test_the_chevron_never_takes_the_accent(section) -> None:
    """It is checkable, and `icons.icon` would tint a checked control
    accent — a section header must not read as the active one."""
    assert _chevron(section) != icons.icon("chevron-down").cacheKey()


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


def _themed_stack(qapp, titles: list[str]) -> QWidget:
    """A column of sections wearing the theme, shown offscreen.

    The theme goes on this widget rather than on the QApplication, so
    these tests cannot colour anything else in the suite.
    """
    stack = QWidget()
    column = QVBoxLayout(stack)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    for title in titles:
        section = CollapsibleSection(title)
        section.set_content(QLabel("body\nrows\nhere"))
        column.addWidget(section)
    column.addStretch(1)
    stack.setPalette(build_palette())
    stack.setStyleSheet(stylesheet())
    stack.setAutoFillBackground(True)   # so the bodies' ground is painted
    stack.resize(240, 400)
    stack.show()
    qapp.processEvents()
    return stack


def _sections(stack: QWidget) -> list[CollapsibleSection]:
    return stack.findChildren(CollapsibleSection)


def test_the_band_is_the_seam_between_two_sections(qapp) -> None:
    """Painted, not asserted from the QSS text: the header sits on a
    different ground from its body, with a 1px border line along its
    top, so a stack of open sections reads as separate blocks."""
    stack = _themed_stack(qapp, ["Playback && Sync", "Appearance && Effects"])
    second = _sections(stack)[1]
    image = stack.grab().toImage()
    x = stack.width() // 2             # clear of the chevron and the text
    header = second._header
    top = header.mapTo(stack, header.rect().topLeft()).y()
    bottom = top + header.height() - 1

    def at(y: int) -> str:
        return image.pixelColor(x, y).name()

    assert at(top - 1) == tokens.PANEL         # the body it divides from
    assert at(top) == tokens.BORDER            # the separator
    assert at(top + 4) == tokens.WINDOW        # the band
    assert at(bottom + 6) == tokens.PANEL      # its own body


def test_the_band_is_not_a_box_around_the_title(qapp) -> None:
    """One line, not two. A line under the band as well would enclose
    the heading instead of dividing the sections (Marcus, 2026-08-29)."""
    stack = _themed_stack(qapp, ["Playback && Sync", "Appearance && Effects"])
    second = _sections(stack)[1]
    image = stack.grab().toImage()
    x = stack.width() // 2
    header = second._header
    bottom = (header.mapTo(stack, header.rect().topLeft()).y()
              + header.height() - 1)
    assert image.pixelColor(x, bottom).name() == tokens.WINDOW


def test_the_top_section_of_a_stack_draws_no_separator(qapp) -> None:
    """The line separates two sections, so the first one has none: in a
    dock it would land straight on the title bar's own line."""
    stack = _themed_stack(qapp, ["Playback && Sync", "Appearance && Effects"])
    first, second = _sections(stack)[:2]
    assert first._header.property("topmost") is True
    assert second._header.property("topmost") is False

    image = stack.grab().toImage()
    x = stack.width() // 2
    top = first._header.mapTo(stack, first._header.rect().topLeft()).y()
    assert image.pixelColor(x, top).name() == tokens.WINDOW


def test_a_section_on_its_own_keeps_its_line(qapp) -> None:
    """With no parent layout it cannot know what is above it, and one
    line too many is tidier than a stack with no seam in it."""
    s = CollapsibleSection("Selection")
    s.set_content(QLabel("nothing selected"))
    s.show()
    qapp.processEvents()
    assert s._header.property("topmost") is False
