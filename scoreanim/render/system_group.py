"""One scene object per system: the parent that lets a whole system be
moved or scaled as a single thing.

Every element used to hang straight off its page scene, so nothing in
the scene meant "this system". Now each element whose system is known
sits under a `SystemGroupItem` for its (page, system); ink with no
system — stage texts, page furniture — stays where it was.

The group is deliberately inert. It sits at the origin, it paints
nothing, and until somebody calls `set_system_scale` it carries no
transform at all, so every child keeps exactly the scene coordinates it
had before there was a parent. Scene coordinates are page coordinates
(see render/scene.py), and the group does not change that.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF

from scoreanim.render.items import ElementItem, GroupItem


class SystemGroupItem(GroupItem):
    """All the ink of one (page, system) as one object.

    Non-painting and hit-transparent, both inherited from `GroupItem` —
    which is what keeps the group out of `scene.items(area)` and so out
    of selection's candidate list, exactly as the per-element parents
    have been since M2.3.
    """

    def __init__(self, page: int, system: int) -> None:
        super().__init__()
        self.page = page
        self.system = system
        self._ink: QRectF | None = None
        self._scale = 1.0
        self._reveal_kids: tuple[ElementItem, ...] = ()

    # -- the system's own ink ----------------------------------------------

    def freeze_ink_rect(self) -> None:
        """Measure the system's ink once, after every child is in, and
        keep it.

        Cached on purpose, not read per frame. It is measured from the
        ENGRAVED positions: the document's nudges (`apply_overrides`)
        and the animation both run after construction, and neither
        should be able to drag the point a whole system turns around.
        Group-local coordinates are page coordinates, because the group
        sits at the origin with no transform."""
        self._ink = self.childrenBoundingRect()
        # The members a scale has to do extra work for, found once here
        # for the same reason: their reveal paths are all added during
        # construction, before anything is parented, so this set is
        # final. It matters because a scale that moves every frame would
        # otherwise walk every element on the system to reach the handful
        # of spanners that need a new clip.
        self._reveal_kids = tuple(
            child for child in self.childItems()
            if isinstance(child, ElementItem) and child.reveal_children)

    @property
    def ink_rect(self) -> QRectF:
        """The frozen bounding rect of this system's ink, in page
        coordinates. Empty until `freeze_ink_rect` has run."""
        return QRectF(self._ink) if self._ink is not None else QRectF()

    @property
    def pivot(self) -> QPointF:
        """What a system-wide scale turns around: the centre of the
        system's own ink, not the page's centre and not the anchor of
        any one element."""
        return self.ink_rect.center()

    # -- the scale seam ----------------------------------------------------

    @property
    def system_scale(self) -> float:
        return self._scale

    def set_system_scale(self, scale: float) -> None:
        """Scale this whole system about the centre of its own ink.

        1.0 is exactly identity: Qt builds the transform as
        translate(pivot) · scale(1) · translate(-pivot), whose
        translations cancel exactly, so a system at 1.0 renders
        bit-identically to one that was never scaled at all.

        Scaling changes every descendant's scene transform, which is
        what a reveal clip's cached inverse depends on — the same trap
        a nudge sprang at M3.2. The children that have a clip re-derive
        it here; the rest need nothing, since Qt carries the transform
        for them."""
        if scale == self._scale:
            return
        self._scale = scale
        self.setTransformOriginPoint(self.pivot)
        self.setScale(scale)
        for child in self._reveal_kids:
            child.refresh_reveal_clip()
