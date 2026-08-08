"""Stage commands: presentation mode, hide-empty-staves toggles, stage
texts, and tempo overlays."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from scoreanim.core.project.commands.base import (_HEX_COLOR, Command,
                                                  CommandError)
from scoreanim.core.project.document import LayoutOverride, ProjectDoc
from scoreanim.core.project.stage_config import (OVERLAY_PREFIX,
                                                 PresentationMode,
                                                 StageTextElement, VideoCanvas,
                                                 fit_texts, is_header_text)
from scoreanim.core.score.identity import ElementId


@dataclass(frozen=True)
class SetPresentationMode(Command):
    """Paged (default) vs system-at-a-time framing (Phase 7.4). Stage
    intent only — the Layout is identical in both modes."""
    mode: PresentationMode

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not isinstance(self.mode, PresentationMode):
            raise CommandError(f"bad presentation mode {self.mode!r}")
        return replace(doc, stage=replace(doc.stage, mode=self.mode))

    def describe(self) -> str:
        return "set presentation mode"


@dataclass(frozen=True)
class SetHideEmptyStaves(Command):
    """Hide staves that are empty for a whole system (Phase 10R).
    Intent only — the hidden layout re-derives at the engraving seam,
    like staff groups; the window re-engraves on the doc diff."""
    value: bool

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not isinstance(self.value, bool):
            raise CommandError(f"bad hide_empty_staves {self.value!r}")
        return replace(doc, hide_empty_staves=self.value)

    def describe(self) -> str:
        return "hide empty staves" if self.value else "show empty staves"


@dataclass(frozen=True)
class SetHideFirstSystem(Command):
    """Also hide empty staves on the FIRST system (2026-07-24) — off by
    default, since first-system-full is the engraving convention.
    Meaningful only while hide_empty_staves is on; same re-engrave seam."""
    value: bool

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if not isinstance(self.value, bool):
            raise CommandError(f"bad hide_first_system {self.value!r}")
        return replace(doc, hide_first_system=self.value)

    def describe(self) -> str:
        return ("hide empty staves on first system" if self.value
                else "show staves on first system")


# Encoder floor/ceiling for a canvas side: below 16 nothing is a video,
# above 8192 nothing plays it; even because yuva subsampling needs it.
_CANVAS_SIDE = range(16, 8193)
_SCALE_RANGE = (0.5, 3.0)
# Verovio's lyricSize saturates at 2.0–8.0 around a 4.5 default, so
# the UI range brackets what actually changes anything.
_LYRICS_RANGE = (0.5, 1.75)
# Verovio's staffLineWidth saturates at 0.1–0.3 around a 0.15 default.
_STAFF_LINE_RANGE = (0.7, 2.0)


def _validated_canvas(canvas: VideoCanvas) -> VideoCanvas:
    for side in (canvas.width, canvas.height):
        if not isinstance(side, int) or side not in _CANVAS_SIDE \
                or side % 2:
            raise CommandError(f"bad canvas side {side!r} "
                               f"(want an even 16–8192)")
    return canvas


@dataclass(frozen=True)
class SetVideoCanvas(Command):
    """The user's video frame (2026-08-06), or None for the page-aspect
    default. Fat apply: a preset click carries width and height in one
    undo entry. Stage intent only — never re-engraves."""
    canvas: VideoCanvas | None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        if self.canvas is not None:
            _validated_canvas(self.canvas)
        return replace(doc, stage=replace(doc.stage, canvas=self.canvas))

    def describe(self) -> str:
        return "set video canvas" if self.canvas is not None \
            else "clear video canvas"


@dataclass(frozen=True)
class SetScoreScale(Command):
    """The score's SIZE (2026-08-06, corrected the same day it was
    born a crop): the notation is engraved bigger or smaller on the
    same page — rastral size, an ENGRAVING input, so the window
    re-engraves on this diff (~0.6 s; the panel commits it via
    execute, never preview). Crowding within a system is the user's to
    solve with system breaks; a system too tall still repaginates and,
    at worst, scale-to-fit keeps the last word (rule 7)."""
    scale: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        lo, hi = _SCALE_RANGE
        if not isinstance(self.scale, (int, float)) \
                or not math.isfinite(self.scale) \
                or not lo <= self.scale <= hi:
            raise CommandError(f"bad score scale {self.scale!r} "
                               f"(want {lo}–{hi})")
        return replace(doc, engraving=replace(doc.engraving,
                                              scale=float(self.scale)))

    def describe(self) -> str:
        return "set score scale"


@dataclass(frozen=True)
class SetLyricsSize(Command):
    """The lyrics' own size, a factor of the engraver's default —
    lyrics crowd first when the score grows, so they get their own
    knob (2026-08-06). An engraving input like the score scale: same
    re-engrave diff, same debounced-preview panel field. Verovio
    clamps the underlying size to its own hard range, so factors past
    ~1.78 (or under ~0.44) saturate rather than raise."""
    factor: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        lo, hi = _LYRICS_RANGE
        if not isinstance(self.factor, (int, float)) \
                or not math.isfinite(self.factor) \
                or not lo <= self.factor <= hi:
            raise CommandError(f"bad lyrics size {self.factor!r} "
                               f"(want {lo}–{hi})")
        return replace(doc, engraving=replace(doc.engraving,
                                              lyric_size=float(self.factor)))

    def describe(self) -> str:
        return "set lyrics size"


@dataclass(frozen=True)
class SetStaffLineWidth(Command):
    """Staff line thickness, a factor of the engraver's default —
    heavier lines read better over video (2026-08-07). The third
    engraving knob, same contract as the score scale and the lyrics
    size: re-engrave diff, debounced-preview panel field, saturation
    at the engraver's own hard range."""
    factor: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        lo, hi = _STAFF_LINE_RANGE
        if not isinstance(self.factor, (int, float)) \
                or not math.isfinite(self.factor) \
                or not lo <= self.factor <= hi:
            raise CommandError(f"bad staff line width {self.factor!r} "
                               f"(want {lo}–{hi})")
        return replace(doc, engraving=replace(
            doc.engraving, staff_line_width=float(self.factor)))

    def describe(self) -> str:
        return "set staff line width"


_TEXT_ANCHORS = frozenset({"start", "middle", "end"})


def _validated_stage_text(text: StageTextElement) -> StageTextElement:
    if not text.content.strip():
        raise CommandError("stage text content is blank")
    if text.anchor not in _TEXT_ANCHORS:
        raise CommandError(f"bad anchor {text.anchor!r} "
                           f"(want start/middle/end)")
    if not (math.isfinite(text.x) and math.isfinite(text.y)):
        raise CommandError(f"stage text position ({text.x!r}, {text.y!r}) "
                           f"not finite")
    if not (isinstance(text.font_size, (int, float))
            and math.isfinite(text.font_size) and text.font_size > 0):
        raise CommandError(f"bad font size {text.font_size!r}")
    if text.color is not None and not _HEX_COLOR.match(text.color):
        raise CommandError(f"bad color {text.color!r} (want #rrggbb)")
    return text


@dataclass(frozen=True)
class EditStageText(Command):
    """Content/position/style of one stage text (Phase 9.1). Never
    re-engraves — stage texts are overlay by construction. `band` is
    runtime data (the SetGlobalSwing.end_beat idiom: the doc stores
    intent only, the UI supplies the derived free space above the top
    staff from page_content_top). When given, the whole header block
    re-fits into it — down-only, sibling texts may rescale/move, all
    one undo step, matching the seed's baked-fit semantics. Overlay
    texts (stage:overlay:*) sit at their engraved position and never
    participate in the refit."""
    element_id: str
    text: StageTextElement           # full replacement (same id, same page)
    band: float | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        old = next((t for t in doc.stage.texts
                    if t.element_id == self.element_id), None)
        if old is None:
            raise CommandError(f"no stage text {self.element_id!r}")
        if self.text.element_id != self.element_id:
            raise CommandError("stage text id cannot change (it is the key)")
        if self.text.page != old.page:
            raise CommandError("stage text page cannot change")
        _validated_stage_text(self.text)
        texts = tuple(self.text if t.element_id == self.element_id else t
                      for t in doc.stage.texts)
        if self.band is not None:
            if not (isinstance(self.band, (int, float))
                    and math.isfinite(self.band) and self.band > 0):
                raise CommandError(f"bad band {self.band!r}")
            header = tuple(t for t in texts if is_header_text(t))
            fitted = dict(zip((t.element_id for t in header),
                              fit_texts(header, float(self.band))))
            texts = tuple(fitted.get(t.element_id, t) for t in texts)
        return replace(doc, stage=replace(doc.stage, texts=texts))

    def describe(self) -> str:
        return "edit stage text"


@dataclass(frozen=True)
class AddTempoOverlay(Command):
    """Replace an engraved TEXT with a stage text: hide the engraved
    element — the first consumer of LayoutOverride.hidden — and add its
    replacement, one intent, ONE undo step. Never re-engraves.

    Named for its first caller (Phase 9.2, tempo marks) but never
    restricted to them: the doc has no layout, so this cannot verify
    what `element_id` is, and the UI guarantees it (the part_order trust
    model). M3.1 relies on exactly that — a system text or rehearsal
    mark takes this path unchanged, which is what "the tempo-overlay
    mechanism generalized" turned out to cost.

    Editing an existing overlay is EditStageText on the overlay id."""
    element_id: ElementId            # the ENGRAVED element to hide
    text: StageTextElement           # id must be OVERLAY_PREFIX + element_id

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        expected = OVERLAY_PREFIX + str(self.element_id)
        if self.text.element_id != expected:
            raise CommandError(f"overlay text id {self.text.element_id!r} "
                               f"must be {expected!r}")
        if any(t.element_id == expected for t in doc.stage.texts):
            raise CommandError(f"element {self.element_id} is already "
                               f"overlaid")
        _validated_stage_text(self.text)
        overrides = dict(doc.layout_overrides)
        overrides[self.element_id] = replace(
            overrides.get(self.element_id, LayoutOverride()), hidden=True)
        return replace(doc, layout_overrides=overrides,
                       stage=replace(doc.stage,
                                     texts=doc.stage.texts + (self.text,)))

    def describe(self) -> str:
        # M3.1 generalized the mechanism to any engraved TEXT (system
        # texts, rehearsal marks), so the Edit-menu phrase can no longer
        # say "tempo mark" — it would be wrong for most uses of it now.
        return "replace text"


@dataclass(frozen=True)
class RemoveTempoOverlay(Command):
    """Restore the engraved original: drop the overlay text and clear
    the hidden flag — the override entry disappears entirely when it is
    back at the default (the SetElementStyle sparse-doc idiom)."""
    element_id: ElementId            # the ENGRAVED element

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        overlay_id = OVERLAY_PREFIX + str(self.element_id)
        if not any(t.element_id == overlay_id for t in doc.stage.texts):
            raise CommandError(f"element {self.element_id} is not overlaid")
        texts = tuple(t for t in doc.stage.texts
                      if t.element_id != overlay_id)
        overrides = dict(doc.layout_overrides)
        restored = replace(overrides.get(self.element_id, LayoutOverride()),
                           hidden=False)
        if restored == LayoutOverride():
            overrides.pop(self.element_id, None)
        else:
            overrides[self.element_id] = restored     # keeps its dx/dy
        return replace(doc, layout_overrides=overrides,
                       stage=replace(doc.stage, texts=texts))

    def describe(self) -> str:
        return "restore text"
