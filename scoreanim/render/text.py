"""TextPrimitive / stage-text → QGraphicsSimpleTextItem rows.

Replicates the proven SVG redraw semantics (tools/bbox_overlay.py): runs
flow inline left-to-right, the whole row hangs on the (x, y) anchor point
per text-anchor (start/middle/end), y is the baseline, whitespace inside
runs is preserved, and the fallback text face is Times/serif. Run fills:
None tracks the element color (SVG default black); explicit fills (e.g.
the gray lyricist) are fixed.
"""

from __future__ import annotations

from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QTransform
from PySide6.QtWidgets import QGraphicsSimpleTextItem

from scoreanim.core.engraving.types import TextPrimitive, TextRun
from scoreanim.core.project.stage_config import StageTextElement
from scoreanim.render.items import DEFAULT_COLOR, ElementItem
from scoreanim.render.qpath import to_qtransform

_FALLBACK_FAMILIES = ["Times New Roman", "Times", "Georgia"]


def _font(family: str | None, size: float,
          bold: bool, italic: bool) -> QFont:
    font = QFont()
    font.setFamilies([family] + _FALLBACK_FAMILIES if family
                     else _FALLBACK_FAMILIES)
    font.setStyleHint(QFont.StyleHint.Serif)
    # SVG px sizes; fractional sizes only matter at page-unit scale where
    # sub-unit rounding is invisible (1 unit = 0.1 mm).
    font.setPixelSize(max(1, round(size)))
    font.setBold(bold)
    font.setItalic(italic)
    return font


def add_text_rows(parent: ElementItem, primitive: TextPrimitive) -> None:
    """Attach one TextPrimitive's runs to parent, transformed to page
    units. Each run becomes a QGraphicsSimpleTextItem positioned so its
    baseline sits on primitive.y and the runs flow from the anchored x."""
    fonts = [_font(r.font_family, r.font_size,
                   r.font_weight == "bold", r.font_style == "italic")
             for r in primitive.runs]
    metrics = [QFontMetricsF(f) for f in fonts]
    advances = [m.horizontalAdvance(r.content)
                for m, r in zip(metrics, primitive.runs)]
    total = sum(advances)
    x0 = {"start": primitive.x,
          "middle": primitive.x - total / 2,
          "end": primitive.x - total}[primitive.anchor]

    tf = to_qtransform(primitive.transform)
    x = x0
    for run, font, metric, advance in zip(primitive.runs, fonts, metrics,
                                          advances):
        item = _run_item(run.content, font, run.fill)
        # place at (x, baseline − ascent) in the primitive's LOCAL space,
        # then map to page units: with Qt's row-vector convention A * B
        # applies A first, so the local translation precedes tf.
        local = QTransform.fromTranslate(x, primitive.y - metric.ascent())
        item.setTransform(local * tf, combine=False)
        parent.add_text_child(item, fill_tracks=run.fill is None)
        x += advance


def add_stage_text(parent: ElementItem, text: StageTextElement) -> None:
    """One stage text element (single run, page-unit coordinates)."""
    font = _font(None, text.font_size, text.bold, text.italic)
    metric = QFontMetricsF(font)
    advance = metric.horizontalAdvance(text.content)
    x0 = {"start": text.x,
          "middle": text.x - advance / 2,
          "end": text.x - advance}[text.anchor]
    item = _run_item(text.content, font, text.color)
    item.setPos(x0, text.y - metric.ascent())
    parent.add_text_child(item, fill_tracks=text.color is None)


def _run_item(content: str, font: QFont,
              fill: str | None) -> QGraphicsSimpleTextItem:
    item = QGraphicsSimpleTextItem(content)
    item.setFont(font)
    item.setBrush(QBrush(QColor(fill) if fill else DEFAULT_COLOR))
    return item
