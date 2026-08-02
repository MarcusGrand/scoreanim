"""The path child a spanner reveals by growing a clip (Phase 5.2).

Split out of `render/items.py` on 2026-08-02, when that module went past
the size ceiling. Pure move, no behaviour change: this class never
touched anything else in items.py, and items.py only names it in a type
hint and one isinstance check.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QGraphicsPathItem


class RevealPathItem(QGraphicsPathItem):
    """A path child revealed by a growing clip rect (spanners, Phase 5.2).

    The clip is a right edge in the item's LOCAL coordinates, applied in
    paint() — no shape()/boundingRect() games, no scene re-indexing per
    move, repaint cost is this one path. The edge is clamped to the
    path's own bounds so a fully-hidden or fully-shown spanner is a
    cached no-op; ``None`` means unclipped (fully revealed).

    Construction starts at ``-inf`` (fully HIDDEN): a child whose
    (system, part) key never receives an edge fails safe as invisible
    ink over its floor-opacity ghost, instead of painting fully from
    t=0 (the FINDING-2 silent early-reveal, fixed 2026-07-22). The
    applier warns loudly about such curve-less keys."""

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self._clip_right: float | None = float("-inf")
        self._inverse = None                 # lazily inverted transform

    def invalidate_transform_cache(self) -> None:
        """Drop the cached inverse scene transform (M3.2).

        The cache is correct as long as nothing moves, which was true
        for every element before nudging existed. `ElementItem.set_offset`
        is the one caller; keeping the invalidation explicit rather than
        recomputing per call preserves what the cache is for — this
        runs on the applier's hot path, once per revealed child per
        tick."""
        self._inverse = None

    @property
    def clip_right(self) -> float | None:
        """Local-coords clip edge; None = fully revealed, -inf = the
        never-edged construction default (fully hidden)."""
        return self._clip_right

    @property
    def hidden(self) -> bool:
        return (self._clip_right is not None
                and self._clip_right <= super().boundingRect().left())

    def set_clip_right(self, scene_x: float) -> bool:
        if self._inverse is None:
            inv, ok = self.sceneTransform().inverted()
            if not ok:                        # degenerate transform
                return False
            self._inverse = inv
        local_x = self._inverse.map(QPointF(scene_x, 0.0)).x()
        br = super().boundingRect()
        clip: float | None = min(max(local_x, br.left()), br.right())
        if clip >= br.right():
            clip = None                       # fully revealed
        if clip == self._clip_right:
            return False
        self._clip_right = clip
        self.update()
        return True

    def paint(self, painter, option, widget=None) -> None:  # noqa: N802
        if self._clip_right is None:
            super().paint(painter, option, widget)
            return
        br = super().boundingRect()
        if self._clip_right <= br.left():
            return                            # fully hidden
        painter.save()
        painter.setClipRect(QRectF(br.left(), br.top(),
                                   self._clip_right - br.left(),
                                   br.height()),
                            Qt.ClipOperation.IntersectClip)
        super().paint(painter, option, widget)
        painter.restore()
