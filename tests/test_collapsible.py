"""CollapsibleSection (M1.2), offscreen: header toggle flips content
visibility, programmatic set_expanded stays in sync with the header, the
header band shows the chevron that says which way it is folded (A3), and
the band is the seam that keeps two open sections apart."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

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


def test_the_band_is_the_seam_between_two_sections(qapp) -> None:
    """Painted, not asserted from the QSS text: the header sits on a
    different ground from its body, with a 1px border line above and
    below it, so a dock of open sections reads as separate blocks.

    The theme goes on this widget rather than on the QApplication, so
    the test cannot colour anything else in the suite.
    """
    s = CollapsibleSection("Appearance && Effects")
    s.set_content(QLabel("body\nrows\nhere"))
    s.setPalette(build_palette())
    s.setStyleSheet(stylesheet())
    s.setAutoFillBackground(True)      # so the body's ground is painted
    s.resize(240, 120)
    s.show()
    qapp.processEvents()

    image = s.grab().toImage()
    x = s.width() // 2                 # clear of the chevron and the text
    header = s._header
    top, bottom = header.y(), header.y() + header.height() - 1

    def at(y: int) -> str:
        return image.pixelColor(x, y).name()

    assert at(top) == tokens.BORDER            # the line above
    assert at(top + 4) == tokens.WINDOW        # the band
    assert at(bottom) == tokens.BORDER         # the line below
    assert at(bottom + 6) == tokens.PANEL      # the body under it
