"""Spike: QAudioDecoder behavior for waveform peak extraction (PHASES 4.1).

Questions (before building ui/peaks_worker.py on it):
1. What sample formats/layouts does the ffmpeg backend deliver for our
   wav and mp3? (QAudioFormat.sampleFormat, channelCount, sampleRate)
2. Buffer cadence: how many buffers, how many frames each, wall time for
   a full decode — is per-buffer numpy work event-loop friendly?
3. Does decoded total duration match QMediaPlayer's reported duration?
4. Does decoding work while a QMediaPlayer holds the same file open
   (the app decodes for peaks while the transport is loaded)?

Run: QT_QPA_PLATFORM=offscreen python spikes/decode_audio.py
Findings recorded in spikes/NOTES.md (Phase 4 section).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtMultimedia import QAudioDecoder, QMediaPlayer

FILES = [Path("testdata/testscore.wav"), Path("testdata/testscore.mp3")]


def decode(path: Path, app: QCoreApplication,
           concurrent_player: QMediaPlayer | None = None) -> None:
    dec = QAudioDecoder()
    dec.setSource(QUrl.fromLocalFile(str(path.resolve())))

    buffers: list[tuple[int, int]] = []      # (frameCount, byteCount)
    formats: set[str] = set()
    frames = 0
    t0 = time.perf_counter()

    def on_ready() -> None:
        nonlocal frames
        buf = dec.read()
        fmt = buf.format()
        formats.add(f"{fmt.sampleFormat().name}/{fmt.channelCount()}ch/"
                    f"{fmt.sampleRate()}Hz")
        buffers.append((buf.frameCount(), buf.byteCount()))
        frames += buf.frameCount()

    def on_error(*_: object) -> None:
        print(f"  ERROR: {dec.error()} {dec.errorString()}")
        app.quit()

    dec.bufferReady.connect(on_ready)
    dec.finished.connect(app.quit)
    dec.error.connect(on_error)
    dec.start()
    app.exec()

    wall = time.perf_counter() - t0
    rate = int(formats and next(iter(formats)).split("/")[2].rstrip("Hz") or 0)
    dur = frames / rate if rate else 0.0
    sizes = sorted(f for f, _ in buffers)
    concurrent = (f" (concurrent with QMediaPlayer "
                  f"{concurrent_player.mediaStatus().name})"
                  if concurrent_player else "")
    print(f"  formats: {sorted(formats)}")
    print(f"  buffers: {len(buffers)} · frames/buffer min {sizes[0]} "
          f"median {sizes[len(sizes) // 2]} max {sizes[-1]}")
    print(f"  decoded {frames} frames = {dur:.3f}s in {wall:.2f}s wall"
          f"{concurrent}")
    print(f"  decoder-reported duration: {dec.duration()} ms")


def main() -> int:
    app = QCoreApplication(sys.argv)
    for path in FILES:
        print(f"\n{path.name}: plain decode")
        decode(path, app)

    # same file simultaneously open in a QMediaPlayer (the app's reality)
    path = FILES[0]
    player = QMediaPlayer()
    player.setSource(QUrl.fromLocalFile(str(path.resolve())))
    print(f"\n{path.name}: decode while QMediaPlayer holds the file")
    decode(path, app, concurrent_player=player)
    print(f"  player duration: {player.duration()} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
