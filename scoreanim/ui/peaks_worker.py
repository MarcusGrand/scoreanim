"""Event-driven peak extraction: QAudioDecoder → PeakCacheBuilder.

No worker thread (spike 2026-07-11, spikes/NOTES.md Phase 4): the ffmpeg
backend decodes a 35 s file in ~0.03 s wall, delivering buffers through
the event loop; per-buffer numpy binning is far under a millisecond, so
extraction interleaves invisibly with the UI. ``progress`` is throttled;
consumers read ``cache`` (a snapshot — the waveform renders progressively
on long files).

The memoryview from QAudioBuffer.constData() dies with its buffer;
conversion always copies (astype) before the buffer goes away.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

from scoreanim.core.audio import PeakCache, PeakCacheBuilder, to_mono

_PROGRESS_EVERY_S = 0.25

# sample format → (numpy dtype, offset, scale) mapping onto [-1, 1]
_FORMATS = {
    QAudioFormat.SampleFormat.UInt8: (np.uint8, -128.0, 1 / 128.0),
    QAudioFormat.SampleFormat.Int16: (np.int16, 0.0, 1 / 32768.0),
    QAudioFormat.SampleFormat.Int32: (np.int32, 0.0, 1 / 2147483648.0),
    QAudioFormat.SampleFormat.Float: (np.float32, 0.0, 1.0),
}


class PeakExtractor(QObject):
    progress = Signal()          # throttled; read .cache
    finished = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._decoder: QAudioDecoder | None = None
        self._builder: PeakCacheBuilder | None = None
        self._cache: PeakCache | None = None
        self._last_emit = 0.0

    @property
    def cache(self) -> PeakCache | None:
        return self._cache

    def start(self, path: Path) -> None:
        self.stop()
        self._builder = None
        self._cache = None
        self._last_emit = 0.0
        decoder = QAudioDecoder(self)
        decoder.setSource(QUrl.fromLocalFile(str(path.resolve())))
        decoder.bufferReady.connect(self._on_ready)
        decoder.finished.connect(self._on_finished)
        decoder.error.connect(self._on_error)
        self._decoder = decoder
        decoder.start()

    def stop(self) -> None:
        # null first: QAudioDecoder.stop() re-emits finished synchronously,
        # and the nested handler must see the extractor already stopped
        decoder, self._decoder = self._decoder, None
        if decoder is not None:
            decoder.stop()
            decoder.deleteLater()

    # -- decoder events ---------------------------------------------------------

    def _on_ready(self) -> None:
        if self._decoder is None:
            return
        buf = self._decoder.read()
        fmt = buf.format()
        spec = _FORMATS.get(fmt.sampleFormat())
        if spec is None:
            self._fail(f"unsupported sample format {fmt.sampleFormat()}")
            return
        dtype, offset, scale = spec
        if self._builder is None:
            self._builder = PeakCacheBuilder(sample_rate=fmt.sampleRate())
        raw = np.frombuffer(buf.constData(), dtype=dtype)
        samples = (raw.astype(np.float32) + offset) * scale   # owned copy
        self._builder.add_samples(to_mono(samples, fmt.channelCount()))
        now = time.monotonic()
        if now - self._last_emit >= _PROGRESS_EVERY_S:
            self._last_emit = now
            self._cache = self._builder.snapshot()
            self.progress.emit()

    def _on_finished(self) -> None:
        if self._decoder is None:            # re-entrant stop already handled
            return
        if self._builder is not None:
            self._cache = self._builder.snapshot()
        self.stop()
        self.finished.emit()

    def _on_error(self, *_: object) -> None:
        if self._decoder is None:
            return
        self._fail(self._decoder.errorString())

    def _fail(self, message: str) -> None:
        self.stop()
        self._builder = None
        self._cache = None
        self.failed.emit(message)
