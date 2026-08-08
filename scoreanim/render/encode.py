"""Frame sinks: QImage frames → ProRes 4444 .mov (ffmpeg) or PNG files.

ffmpeg is an external dependency, discovered at runtime (find_ffmpeg);
the PNG sequence sink needs only Qt and doubles as the no-ffmpeg path.
Frames STREAM to ffmpeg stdin as rawvideo — no disk intermediate.

Alpha discipline: frames arrive ARGB32_Premultiplied (QPainter's native
compositing format) and one convertToFormat per frame puts them in the
byte order ffmpeg's rgba rawvideo and PNG expect — R,G,B,A, whatever the
machine's endianness. Never pipe ARGB32 bytes (endianness trap).

That same convert is where the file's alpha convention is decided, and
it is a real choice rather than a detail (`AlphaMode`). A half-lit halo
pixel can carry the glow's own gold with an alpha of 70/255 beside it
(STRAIGHT), or that gold already multiplied down to a fifth of itself
(PREMULTIPLIED, "matted with black"). Both describe the same picture,
and an editor that reads one as the other is wrong by a factor of
1/alpha: read straight frames as premultiplied and every soft edge comes
out at full strength — a glow turns into a solid blob the moment there
is a clip underneath. Premiere assumes premultiplied and gives you no
switch (After Effects does), so that is the default here; straight stays
available for the tools that want it.

Blocking stdin writes are accepted backpressure: prores_ks encodes
faster than we rasterize, so stalls are rare and bounded. stderr is kept
tiny with -loglevel error and read only after wait() — reading it
mid-run would deadlock against a full pipe in the worst case.
"""
from __future__ import annotations

import shutil
import subprocess
from enum import Enum, auto
from pathlib import Path
from typing import Protocol

from PySide6.QtGui import QImage


class EncodeError(RuntimeError):
    pass


class AlphaMode(Enum):
    """How a frame's colour and its alpha are written down together.

    PREMULTIPLIED is what Premiere assumes, so it is the default (see
    the module docstring). STRAIGHT is the other convention, kept for
    the tools that read it."""
    PREMULTIPLIED = auto()      # RGB already multiplied by alpha
    STRAIGHT = auto()           # RGB as authored, alpha beside it


_FORMATS = {
    AlphaMode.PREMULTIPLIED: QImage.Format.Format_RGBA8888_Premultiplied,
    AlphaMode.STRAIGHT: QImage.Format.Format_RGBA8888,
}


def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _rgba_rows(image: QImage,
               alpha: AlphaMode) -> tuple[QImage, memoryview]:
    """RGBA bytes in the asked-for alpha convention. The memoryview dies
    with the returned QImage (same lifetime rule as
    QAudioBuffer.constData, spikes/NOTES Phase 4) — the caller must keep
    both in scope while writing.

    The matte is then RELABELLED as plain RGBA, which changes no byte at
    all — it only stops Qt from helpfully undoing it. Both consumers
    need that: `pixelColor` un-premultiplies on the way out whatever the
    format says, and Qt's PNG writer converts premultiplied data back to
    straight before saving, so a premultiplied label would quietly ship
    straight frames."""
    rgba = image.convertToFormat(_FORMATS[alpha])
    if alpha is AlphaMode.PREMULTIPLIED and not rgba.reinterpretAsFormat(
            QImage.Format.Format_RGBA8888):
        raise EncodeError("could not relabel the premultiplied frame")
    if rgba.bytesPerLine() != rgba.width() * 4:
        # RGBA8888 rows are inherently 4-byte aligned so this cannot
        # happen today; fail loudly rather than shear the video if a
        # format change ever introduces scanline padding.
        raise EncodeError(
            f"unexpected scanline padding: bytesPerLine "
            f"{rgba.bytesPerLine()} != width*4 {rgba.width() * 4}")
    return rgba, rgba.constBits()


class FrameSink(Protocol):
    def write(self, n: int, image: QImage) -> None: ...
    def finish(self) -> None: ...
    def abort(self) -> None: ...


class ProResFfmpegSink:
    """One .mov, ProRes 4444 (10-bit + alpha), via prores_ks — imports
    directly into every NLE."""

    def __init__(self, out_path: Path, width: int, height: int,
                 fps: int, ffmpeg: str,
                 alpha: AlphaMode = AlphaMode.PREMULTIPLIED) -> None:
        self._out = Path(out_path)
        self._alpha = alpha
        self._proc: subprocess.Popen | None = subprocess.Popen(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "rawvideo", "-pix_fmt", "rgba",
             "-video_size", f"{width}x{height}",
             "-framerate", str(fps), "-i", "pipe:0",
             "-c:v", "prores_ks", "-profile:v", "4444",
             "-pix_fmt", "yuva444p10le", "-vendor", "apl0",
             "-an", str(self._out)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE)

    def write(self, n: int, image: QImage) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        rgba, rows = _rgba_rows(image, self._alpha)
        try:
            self._proc.stdin.write(rows)
        except (BrokenPipeError, OSError):
            raise EncodeError(self._drain("ffmpeg died mid-encode"))

    def finish(self) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        self._proc.stdin.close()
        rc = self._proc.wait()
        if rc != 0:
            message = self._drain(f"ffmpeg exited {rc}")
            self._unlink_partial()
            raise EncodeError(message)
        self._proc = None

    def abort(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except OSError:
                pass
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        self._unlink_partial()

    def _drain(self, prefix: str) -> str:
        assert self._proc is not None
        self._proc.poll() or self._proc.wait()
        err = b""
        if self._proc.stderr is not None:
            err = self._proc.stderr.read()
        detail = err.decode(errors="replace").strip()
        return f"{prefix}{': ' + detail if detail else ''}"

    def _unlink_partial(self) -> None:
        self._out.unlink(missing_ok=True)


class PngSequenceSink:
    """One PNG per frame: <dir>/<stem>.00000.png … — the no-ffmpeg path;
    every editor imports an image sequence. Same alpha choice as the
    .mov, so a sequence composites like the movie it stands in for."""

    def __init__(self, out_dir: Path, stem: str,
                 alpha: AlphaMode = AlphaMode.PREMULTIPLIED) -> None:
        self._dir = Path(out_dir)
        self._stem = stem
        self._alpha = alpha
        self._dir.mkdir(parents=True, exist_ok=True)
        self._written: list[Path] = []

    def write(self, n: int, image: QImage) -> None:
        rgba, _ = _rgba_rows(image, self._alpha)
        path = self._dir / f"{self._stem}.{n:05d}.png"
        if not rgba.save(str(path), "PNG"):
            raise EncodeError(f"could not write {path}")
        self._written.append(path)

    def finish(self) -> None:
        pass

    def abort(self) -> None:
        for path in self._written:
            path.unlink(missing_ok=True)
        self._written.clear()
