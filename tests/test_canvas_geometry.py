"""canvas_view_rect: the pure seam between the live canvas preview and
the canvas export. Headless — no Qt anywhere near this. (The score's
SIZE is not here: that is EngravingParams.scale, an engraving input —
the frame always shows the whole page.)"""
import pytest

from scoreanim.core.engraving.canvas import canvas_view_rect
from scoreanim.core.engraving.systems import centered_fit

PAGE = (2100.0, 2970.0)          # A4-ish page units (1/10 mm)


def test_rect_has_the_canvas_aspect() -> None:
    rect = canvas_view_rect(*PAGE, 1080, 1920)
    assert rect.w / rect.h == pytest.approx(1080 / 1920)


def test_the_whole_page_is_in_frame() -> None:
    """The page fits the frame, so the view rect covers the page with
    letterbox slack on the short axis only."""
    rect = canvas_view_rect(*PAGE, 1080, 1920)
    page_w, page_h = PAGE
    assert rect.x <= 0 and rect.x + rect.w >= page_w
    assert rect.y <= 0 and rect.y + rect.h >= page_h
    # the limiting axis touches exactly (no slack both ways)
    assert (rect.w == pytest.approx(page_w)
            or rect.h == pytest.approx(page_h))


def test_inverse_of_centered_fit() -> None:
    """Mapping the page through the view rect into the frame lands it
    exactly where centered_fit says a fitted page lands — the two
    functions describe one composite from opposite ends."""
    page_w, page_h = PAGE
    canvas_w, canvas_h = 1920.0, 1080.0
    rect = canvas_view_rect(page_w, page_h, canvas_w, canvas_h)
    ppu = canvas_w / rect.w                    # frame pixels per page unit
    fit = centered_fit(page_w, page_h, canvas_w, canvas_h)
    assert (0 - rect.x) * ppu == pytest.approx(fit.x)
    assert (0 - rect.y) * ppu == pytest.approx(fit.y)
    assert page_w * ppu == pytest.approx(fit.w)
    assert page_h * ppu == pytest.approx(fit.h)


def test_centered_on_the_page() -> None:
    rect = canvas_view_rect(*PAGE, 1080, 1920)
    assert rect.center.x == pytest.approx(PAGE[0] / 2)
    assert rect.center.y == pytest.approx(PAGE[1] / 2)


def test_center_y_moves_only_the_vertical_center() -> None:
    plain = canvas_view_rect(*PAGE, 1080, 1920)
    banded = canvas_view_rect(*PAGE, 1080, 1920, center_y=700.0)
    assert banded.center.y == pytest.approx(700.0)
    assert banded.center.x == pytest.approx(plain.center.x)
    assert (banded.w, banded.h) == (plain.w, plain.h)


@pytest.mark.parametrize("args", [
    (0, 2970, 1080, 1920),
    (2100, 0, 1080, 1920),
    (2100, 2970, 0, 1920),
    (2100, 2970, 1080, -1),
])
def test_bad_inputs_raise(args) -> None:
    with pytest.raises(ValueError):
        canvas_view_rect(*args)
