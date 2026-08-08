"""The chunked export run: renderer → sink, on the GUI thread.

Each batch renders frames until a ~40 ms wall budget is spent, then
re-arms with QTimer.singleShot(0, …) so the event loop breathes between
batches (the dialog repaints, Cancel arrives) and a batch can never
re-enter a running batch. This matches the codebase's deliberate
no-QThread style (PeakExtractor is event-loop-driven the same way).

The dialog builds the renderer and the sink from its form and hands
them here. This module owns the walk, the ETA, and the cancel/abort
routing; it reports back through two callbacks:

- on_progress(frame, total, status_text) after every batch
- on_done(ok, message) exactly once, when the run stops for any reason
"""
from __future__ import annotations

import time
from collections import deque
from typing import Callable

from PySide6.QtCore import QTimer

from scoreanim.render.encode import EncodeError, FrameSink
from scoreanim.render.export import FrameRenderer

_BATCH_BUDGET_S = 0.040


class ExportRun:
    """One export walk. start() arms it; cancel() stops it at the next
    batch boundary and the sink removes its partial output."""

    def __init__(self, renderer: FrameRenderer, sink: FrameSink,
                 on_progress: Callable[[int, int, str], None],
                 on_done: Callable[[bool, str], None]) -> None:
        self._renderer = renderer
        self._sink = sink
        self._on_progress = on_progress
        self._on_done = on_done
        self._frame = 0
        self._recent: deque[tuple[int, float]] = deque(maxlen=50)
        self._cancel_requested = False
        self._running = False

    @property
    def frame_count(self) -> int:
        return self._renderer.frame_count

    def start(self) -> None:
        self._running = True
        self._cancel_requested = False
        QTimer.singleShot(0, self._render_batch)

    def cancel(self) -> None:
        self._cancel_requested = True

    def _render_batch(self) -> None:
        if not self._running:
            return
        if self._cancel_requested:
            self._sink.abort()
            self._done(False, "export cancelled — partial output removed")
            return
        t0 = time.perf_counter()
        total = self._renderer.frame_count
        try:
            while (self._frame < total
                   and time.perf_counter() - t0 < _BATCH_BUDGET_S):
                image = self._renderer.render_frame(self._frame)
                self._sink.write(self._frame, image)
                self._frame += 1
        except EncodeError as exc:
            self._sink.abort()
            self._done(False, f"export failed: {exc}")
            return
        self._recent.append((self._frame, time.perf_counter()))
        self._on_progress(self._frame, total, self._eta_text(total))
        if self._frame >= total:
            try:
                self._sink.finish()
            except EncodeError as exc:
                self._done(False, f"export failed: {exc}")
                return
            self._done(True, "")
            return
        QTimer.singleShot(0, self._render_batch)

    def _done(self, ok: bool, message: str) -> None:
        self._running = False
        self._on_done(ok, message)

    def _eta_text(self, total: int) -> str:
        if len(self._recent) < 2:
            return "exporting…"
        (f0, t0), (f1, t1) = self._recent[0], self._recent[-1]
        if t1 <= t0 or f1 <= f0:
            return "exporting…"
        rate = (f1 - f0) / (t1 - t0)
        remaining = (total - self._frame) / rate
        return (f"frame {self._frame}/{total} · {rate:.0f} fps · "
                f"~{remaining:.0f} s left")
