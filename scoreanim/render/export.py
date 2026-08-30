"""Deterministic frame export: FrameClock walk → transparent QImages.

Phase 6. The renderer owns a PRIVATE ScoreScenes + AnimationApplier pair
built from the SAME inputs as the live ones (AnimationInputs is what
_load_score derives), so the user's stage is never touched — but the
evaluation path is byte-for-byte the live one: frame n samples
t_audio = start + FrameClock.now_seconds() and hands
t_score = t_audio − offset to the applier's apply_at/refresh — the exact
mirror of PlaybackController's tick/seek split (ui/playback.py). Nothing
here re-implements trigger, window, or reveal logic; doing so would fork
the live/export path (CLAUDE.md rule 2's whole point) and is out of
bounds.

Frames render offscreen into QImage — no window, no view — with the
paper rect hidden: transparent background for overlay compositing
(ruling R1, 2026-07-12: always transparent; the floor-opacity ghost ink
exports as-is). Page turns are wherever current_page() says they are —
identical to live follow mode (ruling R2).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Mapping, Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter

from scoreanim.core.animation import (GlowScope, StyleRules,
                                      SystemRevealTrack,
                                      TriggerSchedule)
from scoreanim.core.audio import PeakCache
from scoreanim.core.engraving.canvas import canvas_view_rect
from scoreanim.core.engraving.systems import (SystemBand, SystemsFrame,
                                              system_bands, systems_frame)
from scoreanim.core.engraving.types import Layout
from scoreanim.core.project.document import LayoutOverride
from scoreanim.core.project.stage_config import (PresentationMode,
                                                 StageConfig, VideoCanvas)
from scoreanim.core.score.identity import ElementId
from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing import (FrameClock, SwingRegion, TempoMap,
                                   resolve_seconds)
from scoreanim.render.animate import AnimationApplier
from scoreanim.render.scene import (ScoreScenes, apply_overrides,
                                    apply_style_colors)


class ExportFormat(Enum):
    PRORES_4444 = auto()      # single .mov, alpha, via ffmpeg
    PNG_SEQUENCE = auto()     # one PNG per frame, no ffmpeg needed


@dataclass(frozen=True)
class AnimationInputs:
    """Everything _load_score derives that animation construction
    consumes — retained by the window so export builds its private
    scenes + applier from the SAME inputs as the live ones (identical
    geometry, identical triggers; no re-engrave)."""
    layout: Layout
    stage: StageConfig
    schedule: TriggerSchedule
    reveal_tracks: tuple[SystemRevealTrack, ...]
    # Which ink glows and whose halo it shares — derived from the layout
    # and the join, like everything else here (core/animation/
    # glow_scope.py). Defaulted so a synthetic caller can leave it out.
    glow: GlowScope = field(default_factory=GlowScope)


@dataclass(frozen=True)
class ExportSpec:
    """User intent for one export run. Times are AUDIO seconds: the
    exported video's t=0 is the recording's t=start (start=0 default →
    video 0 == recording 0), and the sidecar offset is applied inside
    the frame walk, never by the compositing user.

    Frame shape: with no `canvas` (the default, and every project before
    v12) it is the aspect of the frame the mode itself shows, taken from
    `height` — the whole page when paged, and the systems frame when in
    system mode (`systems_export_frame`, rework stage 4). With a
    `canvas` (2026-08-06) the frame is exactly canvas.width x
    canvas.height and `height` is ignored. Either way the shape holds
    for the whole run: one size for every frame, whatever the systems
    under it are.

    Both modes frame by the same pure rects the live stage frames:
    `canvas_view_rect` paged, `SystemsFrame.rect_for` in system mode. So
    preview and export agree by construction."""
    fps: int
    height: int                  # pixel height; width from the frame's aspect
    start_seconds: float
    end_seconds: float           # exclusive: frames sample [start, end)
    offset_seconds: float        # audio time of score beat 0 (sidecar)
    format: ExportFormat
    out_path: Path
    mode: PresentationMode = PresentationMode.PAGED
    canvas: VideoCanvas | None = None


def even_size(frame_w: float, frame_h: float,
              target_height: int) -> tuple[int, int]:
    """Output pixel size at the exported frame's own aspect, both
    dimensions floored to even (encoder requirement); the ≤1 px aspect
    residue letterboxes transparently under KeepAspectRatio.

    The frame is the page when paged and the systems frame in system
    mode (`systems_export_frame`), so the shape follows what the stage
    shows in that mode."""
    if frame_w <= 0 or frame_h <= 0 or target_height <= 0:
        raise ValueError(f"bad geometry {frame_w}x{frame_h} "
                         f"@ {target_height}")
    height = int(target_height) & ~1
    width = round(height * frame_w / frame_h) & ~1
    return max(width, 2), max(height, 2)


def systems_export_frame(layout: Layout, canvas: VideoCanvas | None
                         ) -> SystemsFrame | None:
    """The one frame systems mode shows, for this layout and canvas —
    the export half of stage 4 of docs/SYSTEMS_MODE_REWORK.md.

    Exactly the stage's own composition (ui/stage_frame.py::
    StageFraming.systems_frame): the load's constant frame from the pure
    `systems_frame`, reshaped to the video canvas when the document has
    one. Both inputs are load-level facts, so this is one frame for the
    whole run, which is what keeps every exported frame the same size.

    None when the layout has no systems to frame — the caller reads that
    as "nothing to do here, render pages"."""
    frame = systems_frame(system_bands(layout))
    if frame is None or canvas is None:
        return frame
    return frame.for_canvas(canvas.width, canvas.height)


def measure_span_seconds(measures: Sequence[MeasureInfo], first: int,
                         last: int, tempo_map: TempoMap,
                         swing: Sequence[SwingRegion],
                         offset_seconds: float) -> tuple[float, float]:
    """AUDIO-seconds range [start of measure `first`, end of measure
    `last`) — the dialog's measure input converted through the same
    swing-aware resolve_seconds seam as triggers, plus the sidecar
    offset. A pure input conversion: everything downstream of the
    (start, end) seconds is untouched by it."""
    by_number = {m.number: m for m in measures}
    if first not in by_number or last not in by_number:
        raise ValueError(f"unknown measure in span m{first}–m{last}")
    if last < first:
        raise ValueError(f"empty span m{first}–m{last}")
    start_beats = by_number[first].start
    end_beats = by_number[last].start + by_number[last].quarter_length
    start_s, end_s = resolve_seconds([start_beats, end_beats],
                                     tempo_map, swing)
    return start_s + offset_seconds, end_s + offset_seconds


def frame_count(start: float, end: float, fps: int) -> int:
    """ceil((end − start) × fps): frames sample frame-starts in
    [start, end), and a final partial frame period still needs a frame —
    an overlay one frame shorter than the audio conforms badly in an
    NLE. The epsilon keeps float noise in exact products (34.56 × 60)
    from adding a bogus frame at t >= end."""
    if end <= start:
        raise ValueError(f"empty export range [{start}, {end})")
    return max(1, math.ceil((end - start) * fps - 1e-6))


class FrameRenderer:
    """Walk t = start + n/fps and render each frame's page to a
    transparent QImage. Rasterization only — all state comes from the
    same AnimationApplier methods live playback calls."""

    def __init__(self, inputs: AnimationInputs, style: StyleRules,
                 tempo_map: TempoMap, swing: Sequence[SwingRegion],
                 spec: ExportSpec,
                 overrides: Mapping[ElementId, LayoutOverride] | None = None,
                 peaks: PeakCache | None = None) -> None:
        self._spec = spec
        self._clock = FrameClock(spec.fps)
        self._frames = frame_count(spec.start_seconds, spec.end_seconds,
                                   spec.fps)
        # Floor comes from the document (Phase 7.2): the same StyleRules
        # value the live path reads — no fork.
        self._scenes = ScoreScenes(inputs.layout, inputs.stage,
                                   ghost_opacity=style.floor_opacity)
        self._scenes.set_page_background_visible(False)
        apply_style_colors(self._scenes, style)
        # doc intent rides in like `style` does — a hidden tempo mark
        # stays hidden behind its overlay (Phase 9.2) AND a nudged
        # element keeps its delta (M3.2), so the frame cannot disagree
        # with the stage
        apply_overrides(self._scenes, overrides or {})
        self._applier = AnimationApplier(self._scenes.items, inputs.schedule,
                                         tempo_map, style,
                                         inputs.reveal_tracks,
                                         self._scenes.system_groups.values(),
                                         inputs.glow)
        self._applier.set_timing(tempo_map, swing)
        # the recording the volume response and the system pulse read, on
        # the same seam the stage uses — an exported video pops and
        # breathes exactly like the preview
        self._applier.set_audio(peaks, spec.offset_seconds)
        # ONE frame shape for the whole run, and it is the shape the
        # stage shows in this mode: the page when paged, the systems
        # frame in system mode (rework stage 4). The user's canvas gives
        # that frame its aspect when the document has one; without a
        # canvas the shape comes from spec.height.
        geo = inputs.layout.pages[0]
        self._page_geo = geo
        self._canvas = spec.canvas
        self._systems_frame: SystemsFrame | None = None
        self._band_by_system: dict[int, SystemBand] | None = None
        if spec.mode is PresentationMode.SYSTEM:
            frame = systems_export_frame(inputs.layout, spec.canvas)
            if frame is not None:
                self._systems_frame = frame
                self._band_by_system = {b.system: b
                                        for b in system_bands(inputs.layout)}
        if spec.canvas is not None:
            self._width, self._height = spec.canvas.width, spec.canvas.height
        elif self._systems_frame is not None:
            self._width, self._height = even_size(self._systems_frame.width,
                                                  self._systems_frame.height,
                                                  spec.height)
        else:
            self._width, self._height = even_size(geo.width, geo.height,
                                                  spec.height)
        self._last_frame: int | None = None

    @property
    def frame_count(self) -> int:
        return self._frames

    @property
    def size(self) -> tuple[int, int]:
        return self._width, self._height

    @property
    def scenes(self) -> ScoreScenes:
        return self._scenes

    def current_page(self) -> int:
        return self._applier.current_page()

    def current_system(self) -> int:
        return self._applier.current_system()

    def state_time(self, n: int) -> float:
        """Score time sampled by frame n — the playback.py _score_time
        mirror: audio t = start + n/fps, minus the sidecar offset."""
        self._clock.set_frame(n)
        return (self._spec.start_seconds + self._clock.now_seconds()
                - self._spec.offset_seconds)

    def apply_frame(self, n: int) -> None:
        """Put the private scene into frame n's state without
        rasterizing (the walk itself, shared by render_frame and the
        headless sync tests)."""
        t_score = self.state_time(n)
        if self._last_frame is not None and n == self._last_frame + 1:
            self._applier.apply_at(t_score)       # the live tick path
        else:
            self._applier.refresh(t_score)        # the live seek path
        self._last_frame = n

    def render_frame(self, n: int) -> QImage:
        self.apply_frame(n)
        if self._band_by_system is not None:
            return self._render_system_frame()
        scene = self._scenes.scene_for_page(self._applier.current_page())
        image = QImage(self._width, self._height,
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        # source: the whole page (no canvas), or the page region the
        # canvas frames — the SAME rect the live stage fits, so the
        # composite matches the preview by construction
        source = scene.sceneRect() if self._canvas is None \
            else self._canvas_src()
        scene.render(painter, QRectF(0, 0, self._width, self._height),
                     source, Qt.AspectRatioMode.KeepAspectRatio)
        painter.end()
        return image

    def _canvas_src(self, center_y: float | None = None) -> QRectF:
        page, c = self._page_geo, self._canvas
        r = canvas_view_rect(page.width, page.height, c.width, c.height,
                             center_y)
        return QRectF(r.x, r.y, r.w, r.h)

    def _render_system_frame(self) -> QImage:
        """One system in the load's constant systems frame — the same
        picture the stage shows at Fit (stage 4 of
        docs/SYSTEMS_MODE_REWORK.md).

        The frame is fixed for the whole run and the band is centred in
        it (`SystemsFrame.rect_for`), so a system switch moves the music
        behind the glass and never the glass. The cut lands on the frame
        current_system() changes — the same applier walk as live follow
        (ruling R2).

        Neighbours are kept out by HIDING them, not by clipping to a
        region: painted ink is bigger than the bbox union a band is cut
        from, so a region always leaked a little (render/scene.py::
        set_visible_system has the measurements). These scenes are
        private to the export, so the call is ours to make.

        With no canvas the image is the frame's own aspect, so the frame
        fills it but for the ≤1 px even-rounding residue, which
        letterboxes transparently under KeepAspectRatio exactly like
        paged mode."""
        band = self._band_by_system[self._applier.current_system()]
        self._scenes.set_visible_system(band.system)
        scene = self._scenes.scene_for_page(band.page)
        src = self.system_frame_rect(band.system)
        image = QImage(self._width, self._height,
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        scene.render(painter, QRectF(0, 0, self._width, self._height),
                     src, Qt.AspectRatioMode.KeepAspectRatio)
        painter.end()
        return image

    def system_frame_rect(self, system: int) -> QRectF:
        """Where the systems frame sits over the page for `system`, in
        page coordinates — this render's source rect.

        Public because it is the parity seam: the stage frames with the
        same rect out of the same `SystemsFrame.rect_for`, so a test can
        hold the two side by side instead of comparing pictures."""
        r = self._systems_frame.rect_for(self._band_by_system[system].rect)
        return QRectF(r.x, r.y, r.w, r.h)
