"""How big the stage is showing the page, as a percentage.

100 % is the FITTED size — what the Fit action gives you. There is no
natural size to measure against instead: a page is about 2095 x 2967 in
the engraving's own units (tenths of a millimetre), so an "actual size"
percentage would be a number about nothing. Fit is the size the user
can always get back to in one click, so it is the thing to be a
percentage of.

The fit scale is worked out here rather than remembered from the last
fit, because resizing the window changes it — a view left at twice fit
size is not twice fit size any more once the window grows.

Pure: numbers in, numbers out, no widget. `StageView` supplies its
viewport and the rect it fits; the arithmetic tests headless.
"""
from __future__ import annotations

# QGraphicsView.fitInView trims this many pixels off each edge of the
# viewport before it scales. Undocumented, so tests/test_zoom_overlay.py
# pins it against a real fit; the canvas path sets its scale directly
# and passes 0.
FIT_MARGIN = 2.0


def fit_scale(viewport_width: float, viewport_height: float,
              target_width: float, target_height: float,
              margin: float = FIT_MARGIN) -> float:
    """The view scale that just fits `target` inside the viewport, or
    0.0 when either rectangle has no area to fit."""
    width = viewport_width - 2.0 * margin
    height = viewport_height - 2.0 * margin
    if width <= 0.0 or height <= 0.0 \
            or target_width <= 0.0 or target_height <= 0.0:
        return 0.0
    return min(width / target_width, height / target_height)


def percent(scale: float, fitted: float) -> int:
    """`scale` as a whole percentage of the fitted scale; 0 when there
    is nothing on the stage to measure."""
    if fitted <= 0.0 or scale <= 0.0:
        return 0
    return round(scale / fitted * 100.0)


def percent_text(value: int) -> str:
    """What the readout says. Nothing on the stage reads as a dash —
    there is no size to report, and "0 %" would claim there is."""
    return f"{value}%" if value > 0 else "–"
