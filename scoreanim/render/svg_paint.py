"""How an SVG paint attribute becomes a Qt brush or pen.

One small translation layer, shared by the scene builder (which reads
the adapter's primitives) and the items it builds. Kept apart from
`render/items.py` because it is a different job: this module knows what
SVG means, the item knows how an element's appearance is composed.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen

DEFAULT_COLOR = QColor(Qt.GlobalColor.black)   # SVG initial 'color'/fill


def fill_tracks_color(fill: str | None) -> bool:
    """Does ink painted with this SVG fill follow the element's color?

    No fill at all means the SVG said nothing, so the ink is the default
    and it tracks. `fill="none"` means there is no fill to track.

    An explicit fill is normally a deliberate color choice and must not
    be overwritten — but **black is not a choice, it is the default
    written out**, and ink left untracked can never take the selection
    tint. Verovio does exactly that on `<dir>` texts: a census of four
    fixtures (testscore, broken_hairpin_and_slur_test, complex1,
    bigband1) found `fill="#000000"` on the expression direction and
    NOWHERE else — every other fill was absent or "none". So selecting
    "bucket mute" used to go from dimmed to black instead of orange,
    while every other text tinted correctly.
    """
    if fill is None:
        return True
    if fill == "none":
        return False
    return QColor(fill) == DEFAULT_COLOR


# SVG stroke defaults differ from QPen's: butt caps (Qt default is
# square, which would lengthen every staff line and stem by half a
# width), miter joins, miter limit 4.
_SVG_CAP = Qt.PenCapStyle.FlatCap
_SVG_JOIN = Qt.PenJoinStyle.MiterJoin
_SVG_MITER_LIMIT = 4.0


def svg_pen(color: QColor, width: float) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(_SVG_CAP)
    pen.setJoinStyle(_SVG_JOIN)
    pen.setMiterLimit(_SVG_MITER_LIMIT)
    return pen
