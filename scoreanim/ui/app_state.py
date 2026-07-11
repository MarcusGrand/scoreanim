"""AppState: the one hub the synchronized views observe (ARCHITECTURE §7).

Views (stage, waveform, tempo lane) never talk to each other — each holds
only this object, repaints on its signals, and mutates the document
exclusively through commands passed to execute/preview/commit. The
playback controller stays the transport/tick owner; MainWindow bridges
the two (time_changed → set_playhead, seek_requested → playback.seek).

Drag gestures preview-then-commit: ``preview(cmd)`` applies against the
COMMITTED document each time (so the pre-drag state anchors coordinate
conversions) and shows the result everywhere without touching the undo
stack; ``commit(cmd)`` pushes exactly one undo entry on release;
``cancel_preview`` snaps back.

File binding is not undoable (ruling 2026-07-11): ``reset_document``
(open score / open project) starts a fresh stack; ``bind_audio`` swaps
the audio ref outside the stack (it still marks the project dirty).
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING, Sequence

from PySide6.QtCore import QObject, Signal

from scoreanim.core.project import (Command, CommandError, FileRef,
                                    ProjectDoc, UndoStack)
from scoreanim.core.score.model import MeasureInfo

if TYPE_CHECKING:                # core/audio arrives with task 4.2
    from scoreanim.core.audio.peaks import PeakCache

_MIN_SPAN = 0.5                  # seconds; deepest zoom
_MIN_DURATION = 1.0              # axis extent before any audio is loaded

# One wheel notch (120 angle units ≈ 40 px) zooms ×1.1 — conventional
# Mac trackpad/browser feel: small per-step increment, smooth streams.
_ZOOM_PER_PIXEL = math.log(1.1) / 40.0
_PIXELS_PER_NOTCH = 40.0


def apply_wheel(axis: "TimeAxis", event, width_px: int) -> None:
    """Shared wheel/trackpad handling for the timeline views: vertical
    scroll zooms (anchored under the cursor), horizontal scroll pans.
    Trackpads report pixel-precise deltas at gesture rate, giving smooth
    continuous zoom; classic wheels fall back to angle notches."""
    if width_px <= 0:
        return
    pixel = event.pixelDelta()
    if not pixel.isNull():
        dx, dy = float(pixel.x()), float(pixel.y())
    else:
        dx = event.angleDelta().x() / 120.0 * _PIXELS_PER_NOTCH
        dy = event.angleDelta().y() / 120.0 * _PIXELS_PER_NOTCH
    if abs(dx) > abs(dy):
        axis.pan(-dx / width_px * axis.span)
    elif dy:
        anchor = axis.t_of(event.position().x(), width_px)
        axis.zoom(math.exp(dy * _ZOOM_PER_PIXEL), anchor)
    event.accept()


class TimeAxis(QObject):
    """Shared time axis (audio seconds): duration + visible [t0, t1].
    Both timeline views map t↔x through this object, so zooming or
    scrolling one moves the other by construction."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._duration = _MIN_DURATION
        self._t0 = 0.0
        self._t1 = _MIN_DURATION

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def t0(self) -> float:
        return self._t0

    @property
    def t1(self) -> float:
        return self._t1

    @property
    def span(self) -> float:
        return self._t1 - self._t0

    def set_duration(self, seconds: float) -> None:
        """New media extent. A new duration resets the window to the full
        range — durations arrive once per audio load."""
        seconds = max(seconds, _MIN_DURATION)
        if seconds == self._duration:
            return
        self._duration = seconds
        self._t0, self._t1 = 0.0, seconds
        self.changed.emit()

    def set_visible(self, t0: float, t1: float) -> None:
        span = min(max(t1 - t0, _MIN_SPAN), self._duration)
        t0 = min(max(t0, 0.0), self._duration - span)
        if (t0, t0 + span) != (self._t0, self._t1):
            self._t0, self._t1 = t0, t0 + span
            self.changed.emit()

    def zoom(self, factor: float, anchor_t: float) -> None:
        """factor > 1 zooms in; the time under the cursor stays put."""
        self.set_visible(anchor_t - (anchor_t - self._t0) / factor,
                         anchor_t + (self._t1 - anchor_t) / factor)

    def pan(self, dt: float) -> None:
        self.set_visible(self._t0 + dt, self._t1 + dt)

    def x_of(self, t: float, width_px: int) -> float:
        return (t - self._t0) / self.span * width_px

    def t_of(self, x: float, width_px: int) -> float:
        return self._t0 + x / width_px * self.span


class AppState(QObject):
    document_changed = Signal()          # committed edit, preview, undo, reset
    playhead_changed = Signal(float)     # audio seconds
    peaks_changed = Signal()
    seek_requested = Signal(float)       # views emit intent; window executes
    status = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.axis = TimeAxis(self)
        self._committed = ProjectDoc()
        self._preview: ProjectDoc | None = None
        self._stack = UndoStack()
        self._bind_dirty = False
        self._measures: tuple[MeasureInfo, ...] = ()
        self._peaks: "PeakCache | None" = None
        self._playhead = 0.0

    # -- document ---------------------------------------------------------------

    @property
    def doc(self) -> ProjectDoc:
        return self._preview if self._preview is not None else self._committed

    def reset_document(self, doc: ProjectDoc) -> None:
        """Open score / open project: new document, fresh undo stack."""
        self._committed = doc
        self._preview = None
        self._stack = UndoStack()
        self._bind_dirty = False
        self.document_changed.emit()

    def bind_audio(self, ref: FileRef | None) -> None:
        """Audio binding, outside the undo stack (ruling 2026-07-11)."""
        self._committed = replace(self._committed, audio=ref)
        self._bind_dirty = True
        self.document_changed.emit()

    def execute(self, command: Command) -> bool:
        """One-shot edit. Returns False (with a status message) when the
        command rejects its input."""
        try:
            self._committed = self._stack.execute(command, self._committed)
        except CommandError as exc:
            self.status.emit(str(exc))
            return False
        self._preview = None
        self.document_changed.emit()
        return True

    def preview(self, command: Command) -> None:
        """Drag in progress: show the result, touch nothing. Applied to
        the committed doc every time; invalid intermediate states are
        silently ignored (the view clamps)."""
        try:
            self._preview = command.apply(self._committed)
        except CommandError:
            return
        self.document_changed.emit()

    def commit(self, command: Command) -> None:
        """Drag release: exactly one undo entry for the whole gesture."""
        self._preview = None
        self.execute(command)

    def cancel_preview(self) -> None:
        if self._preview is not None:
            self._preview = None
            self.document_changed.emit()

    # -- undo -------------------------------------------------------------------

    def undo(self) -> None:
        if self._stack.can_undo:
            self._preview = None
            self._committed = self._stack.undo()
            self.document_changed.emit()

    def redo(self) -> None:
        if self._stack.can_redo:
            self._preview = None
            self._committed = self._stack.redo()
            self.document_changed.emit()

    @property
    def can_undo(self) -> bool:
        return self._stack.can_undo

    @property
    def can_redo(self) -> bool:
        return self._stack.can_redo

    def undo_text(self) -> str | None:
        return self._stack.undo_text()

    def redo_text(self) -> str | None:
        return self._stack.redo_text()

    @property
    def is_dirty(self) -> bool:
        return self._stack.is_dirty or self._bind_dirty

    def mark_saved(self) -> None:
        self._stack.mark_saved()
        self._bind_dirty = False
        self.document_changed.emit()     # title-bar star refresh

    # -- runtime (derived, never persisted) --------------------------------------

    @property
    def measures(self) -> tuple[MeasureInfo, ...]:
        return self._measures

    def set_measures(self, measures: Sequence[MeasureInfo]) -> None:
        self._measures = tuple(measures)

    @property
    def peaks(self) -> "PeakCache | None":
        return self._peaks

    def set_peaks(self, cache: "PeakCache | None") -> None:
        self._peaks = cache
        self.peaks_changed.emit()

    @property
    def playhead(self) -> float:
        return self._playhead

    def set_playhead(self, audio_seconds: float) -> None:
        self._playhead = audio_seconds
        self.playhead_changed.emit(audio_seconds)

    def request_seek(self, audio_seconds: float) -> None:
        self.seek_requested.emit(audio_seconds)
