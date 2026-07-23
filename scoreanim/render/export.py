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
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Mapping, Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter

from scoreanim.core.animation import (StyleRules, SystemRevealTrack,
                                      TriggerSchedule)
from scoreanim.core.engraving.systems import centered_fit, system_bands
from scoreanim.core.engraving.types import Layout
from scoreanim.core.project.document import LayoutOverride
from scoreanim.core.project.stage_config import PresentationMode, StageConfig
from scoreanim.core.score.identity import ElementId
from scoreanim.core.score.model import MeasureInfo
from scoreanim.core.timing import (FrameClock, SwingRegion, TempoMap,
                                   resolve_seconds)
from scoreanim.render.animate import AnimationApplier
from scoreanim.render.scene import (ScoreScenes, apply_hidden_overrides,
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


@dataclass(frozen=True)
class ExportSpec:
    """User intent for one export run. Times are AUDIO seconds: the
    exported video's t=0 is the recording's t=start (start=0 default →
    video 0 == recording 0), and the sidecar offset is applied inside
    the frame walk, never by the compositing user.

    System mode (Phase 7.5, framing revised Phase 10R): the canvas is
    the PAGE's own aspect from `height`, exactly like paged mode — the
    frame never changes shape between modes; the current system renders
    at natural page width, vertically centered, everything outside its
    band transparent."""
    fps: int
    height: int                  # pixel height; width from the page aspect
    start_seconds: float
    end_seconds: float           # exclusive: frames sample [start, end)
    offset_seconds: float        # audio time of score beat 0 (sidecar)
    format: ExportFormat
    out_path: Path
    mode: PresentationMode = PresentationMode.PAGED


def even_size(page_w: float, page_h: float,
              target_height: int) -> tuple[int, int]:
    """Output pixel size at the page's own aspect, both dimensions
    floored to even (encoder requirement); the ≤1 px aspect residue
    letterboxes transparently under KeepAspectRatio."""
    if page_w <= 0 or page_h <= 0 or target_height <= 0:
        raise ValueError(f"bad geometry {page_w}x{page_h} @ {target_height}")
    height = int(target_height) & ~1
    width = round(height * page_w / page_h) & ~1
    return max(width, 2), max(height, 2)


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
                 overrides: Mapping[ElementId, LayoutOverride] | None = None
                 ) -> None:
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
        # doc intent rides in like `style` does (Phase 9.2: a hidden
        # tempo mark stays hidden behind its overlay in the export)
        apply_hidden_overrides(self._scenes, overrides or {})
        self._applier = AnimationApplier(self._scenes.items, inputs.schedule,
                                         tempo_map, style,
                                         inputs.reveal_tracks)
        self._applier.set_timing(tempo_map, swing)
        # both modes share the page-aspect canvas (Phase 10R ruling:
        # the frame never changes shape); system mode only adds bands
        geo = inputs.layout.pages[0]
        self._page_geo = geo
        self._width, self._height = even_size(geo.width, geo.height,
                                              spec.height)
        if spec.mode is PresentationMode.SYSTEM:
            self._band_by_system = {b.system: b
                                    for b in system_bands(inputs.layout)}
        else:
            self._band_by_system = None
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
        scene.render(painter, QRectF(0, 0, self._width, self._height),
                     scene.sceneRect(),
                     Qt.AspectRatioMode.KeepAspectRatio)
        painter.end()
        return image

    def _render_system_frame(self) -> QImage:
        """A page-sized window centered vertically on the current
        system's band, rendered onto the page-aspect canvas (Phase 10R
        ruling: the frame keeps the layout's shape; the system occupies
        the middle at natural page width). The cut lands on the frame
        current_system() changes — the same applier walk as live follow
        (ruling R2). The explicit clip to the band's projected sub-rect
        is the bleed guarantee: neighboring systems inside the window
        can never paint."""
        band = self._band_by_system[self._applier.current_system()]
        scene = self._scenes.scene_for_page(band.page)
        page = self._page_geo
        src = QRectF(0.0, band.rect.y + band.rect.h / 2 - page.height / 2,
                     page.width, page.height)
        # the fitted target of the page-sized window (its ≤1 px even-
        # rounding residue letterboxes exactly like paged mode)
        fit = centered_fit(page.width, page.height,
                           self._width, self._height)
        scale = fit.h / page.height
        clip = QRectF(fit.x, fit.y + (band.rect.y - src.top()) * scale,
                      fit.w, band.rect.h * scale)
        image = QImage(self._width, self._height,
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setClipRect(clip)
        scene.render(painter, QRectF(fit.x, fit.y, fit.w, fit.h), src,
                     Qt.AspectRatioMode.KeepAspectRatio)
        painter.end()
        return image
