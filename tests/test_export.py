"""Phase 6 export: FrameRenderer on the real fixture with the REAL tempo
sidecar (offset 0.77), offscreen.

The load-bearing assertions:
- onset-frame sync at the start, middle, and end of the piece (a uniform
  error is an offset bug, a growing error is drift — the assertion
  message separates them);
- frame-walk (apply_at ticks) ≡ fresh refresh at the same t — the
  live tick/seek split, pinned for the export walk specifically;
- byte-identical determinism across independent walks, where one walks
  every frame and the other seeks straight to the sampled frames — so
  pixel equality also pins tick ≡ seek at the raster level;
- the page turn lands exactly on the live follow-mode frame (ruling R2);
- transparent background, ghost ink at floor, lit ink at full (pixels).
"""

import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from scoreanim.core.animation import (StyleRules,  # noqa: E402
                                      build_reveal_tracks,
                                      build_trigger_schedule)
from scoreanim.core.project.stage_config import (  # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.timing import (TempoMap, parse_tempo_file,  # noqa: E402
                                   resolve_seconds)
from scoreanim.render.encode import (EncodeError,  # noqa: E402
                                     PngSequenceSink, ProResFfmpegSink,
                                     find_ffmpeg)
from scoreanim.core.engraving.systems import (centered_fit,  # noqa: E402
                                              system_bands)
from scoreanim.core.project.stage_config import PresentationMode  # noqa: E402
from scoreanim.render.export import (AnimationInputs,  # noqa: E402
                                     ExportFormat, ExportSpec,
                                     FrameRenderer, even_size, frame_count,
                                     measure_span_seconds)

FPS = 60
HEIGHT = 360          # small frames keep the raster tests quick
SIDECAR = Path(__file__).resolve().parent.parent / "testdata" / \
    "testscore.tempo"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def schedule(engraved, join_mapping, score_model):
    return build_trigger_schedule(engraved.layout, join_mapping,
                                  score_model.measures)


@pytest.fixture(scope="module")
def inputs(engraved, schedule, score_model) -> AnimationInputs:
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    score_end = max((m.start + m.quarter_length
                     for m in score_model.measures), default=0.0)
    tracks = build_reveal_tracks(engraved.layout, schedule, score_end)
    return AnimationInputs(engraved.layout, stage, schedule, tuple(tracks))


@pytest.fixture(scope="module")
def tempo_setup(score_model):
    setup = parse_tempo_file(SIDECAR.read_text(), score_model.measures)
    assert setup.offset_seconds == pytest.approx(0.77)   # the real sidecar
    return setup


@pytest.fixture(scope="module")
def tempo_map(tempo_setup) -> TempoMap:
    return TempoMap(list(tempo_setup.events))


def make_renderer(inputs, tempo_map, offset, *, start=0.0, end,
                  fps=FPS, height=HEIGHT) -> FrameRenderer:
    spec = ExportSpec(fps=fps, height=height, start_seconds=start,
                      end_seconds=end, offset_seconds=offset,
                      format=ExportFormat.PNG_SEQUENCE,
                      out_path=Path("unused"))
    return FrameRenderer(inputs, StyleRules(), tempo_map, (), spec)


def _trigger_seconds(schedule, tempo_map) -> list[float]:
    return resolve_seconds([t.beats for t in schedule.triggers],
                           tempo_map, ())


def _audio_end(schedule, tempo_map, offset) -> float:
    return _trigger_seconds(schedule, tempo_map)[-1] + offset + 0.5


def _state(renderer) -> dict:
    """Full visual state: opacity per element plus every reveal child's
    clip edge."""
    out = {}
    for eid, item in renderer.scenes.items.items():
        clips = tuple(c.clip_right for c in item.reveal_children)
        out[eid] = (item.opacity(), clips)
    return out


# -- geometry helpers ----------------------------------------------------------


def test_even_size_preserves_aspect_and_evenness() -> None:
    w, h = even_size(2096.0, 2967.0, 2160)
    assert (w, h) == (1526, 2160)
    assert w % 2 == 0 and h % 2 == 0
    assert abs(w / h - 2096.0 / 2967.0) < 2 / 2160   # ≤1 px residue
    with pytest.raises(ValueError):
        even_size(0, 100, 1080)


def test_frame_count_covers_the_full_span() -> None:
    assert frame_count(0.0, 34.56, 60) == 2074       # not 2075: float noise
    assert frame_count(0.0, 1.0, 30) == 30
    assert frame_count(0.0, 1.001, 30) == 31         # partial period → frame
    assert frame_count(10.0, 12.0, 24) == 48
    with pytest.raises(ValueError):
        frame_count(5.0, 5.0, 30)


def test_measure_span_converts_through_the_trigger_seam(
        score_model, tempo_map, tempo_setup) -> None:
    """The dialog's measure range is a pure input conversion: the same
    resolve_seconds seam as triggers, plus the sidecar offset."""
    offset = tempo_setup.offset_seconds
    measures = score_model.measures
    last = measures[-1].number

    start, end = measure_span_seconds(measures, 1, last, tempo_map, (),
                                      offset)
    assert start == pytest.approx(offset)            # m1 starts at beat 0
    score_end = max(m.start + m.quarter_length for m in measures)
    assert end == pytest.approx(
        resolve_seconds([score_end], tempo_map, ())[0] + offset)

    s5, e8 = measure_span_seconds(measures, 5, 8, tempo_map, (), offset)
    assert start < s5 < e8 < end                     # nested and monotone
    s6, _ = measure_span_seconds(measures, 6, 8, tempo_map, (), offset)
    _, e5 = measure_span_seconds(measures, 5, 5, tempo_map, (), offset)
    assert e5 == pytest.approx(s6)                   # m5 end == m6 start

    with pytest.raises(ValueError):
        measure_span_seconds(measures, 8, 5, tempo_map, (), offset)
    with pytest.raises(ValueError):
        measure_span_seconds(measures, 1, 999, tempo_map, (), offset)


# -- the sync contract ---------------------------------------------------------


def test_onset_frames_match_start_middle_end(qapp, inputs, schedule,
                                             tempo_map, tempo_setup) -> None:
    """The no-drift/no-offset-bug proof. For triggers at the start,
    middle, and end of the piece, the first frame at full opacity must
    equal round((trigger_seconds + offset) * fps) within one frame.
    A uniform nonzero error means the offset was dropped/sign-flipped
    (0.77 s ≈ 46 frames at 60 fps); a growing error means drift."""
    offset = tempo_setup.offset_seconds
    seconds = _trigger_seconds(schedule, tempo_map)
    picks = [0, len(schedule.triggers) // 2, len(schedule.triggers) - 1]
    watched = {}                                     # eid → expected frame
    for i in picks:
        eid = next(e for e in schedule.triggers[i].element_ids
                   if e in inputs.schedule.beats_by_element)
        watched[eid] = round((seconds[i] + offset) * FPS)

    end = _audio_end(schedule, tempo_map, offset)
    renderer = make_renderer(inputs, tempo_map, offset, end=end)
    first_full = {}
    for n in range(renderer.frame_count):
        renderer.apply_frame(n)
        for eid in watched:
            if eid not in first_full and \
                    renderer.scenes.items[eid].opacity() >= 0.999:
                first_full[eid] = n

    errors = [first_full[eid] - expected
              for eid, expected in watched.items()]
    mean = sum(errors) / len(errors)
    spread = max(errors) - min(errors)
    assert all(abs(e) <= 1 for e in errors), (
        f"onset frames off: errors={errors} "
        f"(mean {mean:+.2f} ⇒ offset bug if ≉0; "
        f"spread {spread} ⇒ drift if >1)")


def test_range_export_frame_zero_is_a_seek(qapp, inputs, schedule,
                                           tempo_map, tempo_setup) -> None:
    """Frame 0 of a [10, …) range export is exactly the state of frame
    600 of a whole export at 60 fps — i.e. a live seek to 10.0."""
    offset = tempo_setup.offset_seconds
    end = _audio_end(schedule, tempo_map, offset)
    whole = make_renderer(inputs, tempo_map, offset, end=end)
    whole.apply_frame(600)                           # t_audio = 10.0
    ranged = make_renderer(inputs, tempo_map, offset, start=10.0, end=end)
    ranged.apply_frame(0)
    assert _state(ranged) == _state(whole)
    assert ranged.frame_count == frame_count(10.0, end, FPS)


def test_frame_walk_equals_fresh_refresh(qapp, inputs, schedule,
                                         tempo_map, tempo_setup) -> None:
    """The export tick path (sequential apply_at) lands in exactly the
    state a fresh refresh produces at the same t — the live
    statelessness pin, re-pinned for the frame walk."""
    offset = tempo_setup.offset_seconds
    end = _audio_end(schedule, tempo_map, offset)
    walker = make_renderer(inputs, tempo_map, offset, end=end)
    samples = {0, 100, walker.frame_count // 2, walker.frame_count - 1}
    snapshots = {}
    for n in range(walker.frame_count):
        walker.apply_frame(n)
        if n in samples:
            snapshots[n] = _state(walker)

    for n in sorted(samples):
        fresh = make_renderer(inputs, tempo_map, offset, end=end)
        fresh.apply_frame(n)                         # first call → refresh
        assert _state(fresh) == snapshots[n], f"frame {n}"


def test_page_turn_frame_matches_live_follow(qapp, inputs, schedule,
                                             tempo_map,
                                             tempo_setup) -> None:
    """The hard cut lands exactly where live follow mode flips: the
    first frame with t_score >= the new page's first trigger."""
    offset = tempo_setup.offset_seconds
    seconds = _trigger_seconds(schedule, tempo_map)
    i = next(i for i, t in enumerate(schedule.triggers) if t.page == 2)
    expected = math.ceil((seconds[i] + offset) * FPS - 1e-6)

    end = _audio_end(schedule, tempo_map, offset)
    renderer = make_renderer(inputs, tempo_map, offset, end=end)
    renderer.apply_frame(expected - 1)
    assert renderer.current_page() == 1
    renderer.apply_frame(expected)
    assert renderer.current_page() == 2


# -- pixels --------------------------------------------------------------------


def _max_alpha_in(image, x0: int, y0: int, x1: int, y1: int) -> int:
    return max(image.pixelColor(x, y).alpha()
               for x in range(x0, x1) for y in range(y0, y1))


def test_frames_are_transparent_with_ghost_then_lit_ink(
        qapp, inputs, schedule, tempo_map, tempo_setup) -> None:
    offset = tempo_setup.offset_seconds
    seconds = _trigger_seconds(schedule, tempo_map)
    end = _audio_end(schedule, tempo_map, offset)
    renderer = make_renderer(inputs, tempo_map, offset, end=end)
    w, h = renderer.size

    eid = next(e for e in schedule.triggers[0].element_ids
               if renderer.scenes.items[e].bbox is not None)
    item = renderer.scenes.items[eid]
    geo = inputs.layout.pages[0]
    scale = min(w / geo.width, h / geo.height)
    dx = (w - geo.width * scale) / 2
    dy = (h - geo.height * scale) / 2

    def bbox_px(image):
        b = item.bbox
        x0 = max(0, int(b.x() * scale + dx) - 1)
        y0 = max(0, int(b.y() * scale + dy) - 1)
        x1 = min(w, int((b.x() + b.width()) * scale + dx) + 2)
        y1 = min(h, int((b.y() + b.height()) * scale + dy) + 2)
        return _max_alpha_in(image, x0, y0, x1, y1)

    pre = renderer.render_frame(0)                   # t_score = −0.77: floor
    assert pre.pixelColor(0, 0).alpha() == 0         # transparent, no paper
    assert pre.pixelColor(w - 1, h - 1).alpha() == 0
    ghost = bbox_px(pre)
    assert 40 <= ghost <= 120, ghost                 # ≈ 0.3 × 255, antialiased

    onset_frame = math.ceil((seconds[0] + offset) * FPS - 1e-6)
    lit = bbox_px(renderer.render_frame(onset_frame))
    assert lit >= 200, lit


def test_two_walks_are_byte_identical(qapp, inputs, schedule, tempo_map,
                                      tempo_setup) -> None:
    """Determinism AND tick ≡ seek at the raster level: walker renders
    its samples mid-walk (apply_at path); seeker jumps straight to them
    (refresh path). Same bytes required."""
    offset = tempo_setup.offset_seconds
    end = _audio_end(schedule, tempo_map, offset)
    walker = make_renderer(inputs, tempo_map, offset, end=end)
    seeker = make_renderer(inputs, tempo_map, offset, end=end)
    samples = sorted({0, 240, walker.frame_count // 2,
                      walker.frame_count - 1})

    def digest(image) -> str:
        rgba = image.convertToFormat(image.Format.Format_RGBA8888)
        return hashlib.sha256(bytes(rgba.constBits())).hexdigest()

    walked = {}
    for n in range(walker.frame_count):
        if n in samples:
            walked[n] = digest(walker.render_frame(n))
        else:
            walker.apply_frame(n)

    for n in samples:
        assert digest(seeker.render_frame(n)) == walked[n], f"frame {n}"


# -- system-mode export (Phase 7.5) ---------------------------------------------


def make_system_renderer(inputs, tempo_map, offset, *, end, height,
                         fps=FPS) -> FrameRenderer:
    spec = ExportSpec(fps=fps, height=height,
                      mode=PresentationMode.SYSTEM,
                      start_seconds=0.0, end_seconds=end,
                      offset_seconds=offset,
                      format=ExportFormat.PNG_SEQUENCE,
                      out_path=Path("unused"))
    return FrameRenderer(inputs, StyleRules(), tempo_map, (), spec)


def test_paged_export_untouched_by_system_machinery(
        qapp, inputs, tempo_map, tempo_setup) -> None:
    """A spec built without the new fields runs the Phase 6 path: no
    band machinery constructed, size still page-aspect-locked. (The
    byte-level pin is every pre-existing test in this file passing
    unmodified, incl. test_two_walks_are_byte_identical.)"""
    renderer = make_renderer(inputs, tempo_map,
                             tempo_setup.offset_seconds, end=10.0)
    assert renderer._band_by_system is None
    geo = inputs.layout.pages[0]
    assert renderer.size == even_size(geo.width, geo.height, HEIGHT)


def test_system_canvas_is_page_aspect_from_height(
        qapp, inputs, tempo_map, tempo_setup) -> None:
    """Phase 10R ruling: the frame never changes shape between modes —
    system mode sizes its canvas exactly like paged mode (page aspect
    from the height field), and the SAME height gives IDENTICAL pixels
    in both modes (the user's export requirement: every frame the same
    aspect ratio / pixel size)."""
    offset = tempo_setup.offset_seconds
    system = make_system_renderer(inputs, tempo_map, offset, end=10.0,
                                  height=361)
    geo = inputs.layout.pages[0]
    assert system.size == even_size(geo.width, geo.height, 361)
    paged = make_renderer(inputs, tempo_map, offset, end=10.0)  # HEIGHT
    paged361 = make_system_renderer(inputs, tempo_map, offset, end=10.0,
                                    height=HEIGHT)
    assert paged.size == paged361.size    # systems == paged at same height


def test_system_export_frames_are_all_one_size(qapp, inputs, schedule,
                                               tempo_map, tempo_setup) -> None:
    """Every exported frame is byte-for-byte the same pixel dimensions,
    however the per-system band heights vary across the walk (the user's
    'canvas must not change size' requirement, pinned end-to-end)."""
    offset = tempo_setup.offset_seconds
    end = _audio_end(schedule, tempo_map, offset)
    renderer = make_system_renderer(inputs, tempo_map, offset, end=end,
                                    height=360)
    systems_seen = set()
    sizes = set()
    step = max(1, renderer.frame_count // 20)
    for n in range(0, renderer.frame_count, step):
        img = renderer.render_frame(n)
        sizes.add((img.width(), img.height()))
        systems_seen.add(renderer.current_system())
    assert len(systems_seen) >= 3         # the walk really crossed systems
    assert sizes == {renderer.size}       # one size throughout


def test_system_cut_frames_match_live_follow(qapp, inputs, schedule,
                                             tempo_map,
                                             tempo_setup) -> None:
    """The system hard cut lands exactly where live follow flips: the
    first frame with t_score >= the first trigger of each new system
    (the page-turn pin generalized, ruling R2)."""
    offset = tempo_setup.offset_seconds
    seconds = _trigger_seconds(schedule, tempo_map)
    end = _audio_end(schedule, tempo_map, offset)
    renderer = make_system_renderer(inputs, tempo_map, offset, end=end,
                                    height=360)
    for target in (2, 3, 4, 5):
        i = next(i for i, t in enumerate(schedule.triggers)
                 if t.system == target)
        expected = math.ceil((seconds[i] + offset) * FPS - 1e-6)
        renderer.apply_frame(expected - 1)
        assert renderer.current_system() == target - 1, target
        renderer.apply_frame(expected)
        assert renderer.current_system() == target, target


@pytest.mark.parametrize("height", [360, 500])
def test_system_frame_is_page_shaped_with_band_centered(
        qapp, inputs, schedule, tempo_map, tempo_setup, height) -> None:
    """Phase 10R framing: the canvas is page-shaped; the system's band
    renders at natural page width, VERTICALLY CENTERED; every sampled
    pixel outside the band's projected strip is fully transparent (clip:
    no neighbour bleed, no letterbox ink)."""
    offset = tempo_setup.offset_seconds
    seconds = _trigger_seconds(schedule, tempo_map)
    end = _audio_end(schedule, tempo_map, offset)
    renderer = make_system_renderer(inputs, tempo_map, offset, end=end,
                                    height=height)
    w, h = renderer.size
    geo = inputs.layout.pages[0]
    band = {b.system: b for b in system_bands(inputs.layout)}[1]
    fit = centered_fit(geo.width, geo.height, w, h)
    scale = fit.h / geo.height
    strip_top = fit.y + (geo.height - band.rect.h) / 2 * scale
    strip_bottom = strip_top + band.rect.h * scale
    # the band strip is vertically centered in the canvas
    assert (strip_top + strip_bottom) / 2 == pytest.approx(h / 2, abs=1.5)

    onset = math.ceil((seconds[0] + offset) * FPS - 1e-6)
    image = renderer.render_frame(onset)             # system 1, ink lit
    ink = 0
    for x in range(0, w, 4):
        for y in range(0, h, 4):
            alpha = image.pixelColor(x, y).alpha()
            inside = strip_top - 1 <= y <= strip_bottom + 1
            if not inside:
                assert alpha == 0, (x, y)
            elif alpha > 0:
                ink += 1
    assert ink > 10                                  # the band drew content


# -- encoder sinks -------------------------------------------------------------


def _test_frame(w: int = 64, h: int = 64):
    """Premultiplied frame with a transparent background and one
    half-transparent pure-red square — enough to catch a broken
    un-premultiply (which would ship dark red) or a lost alpha."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.fillRect(16, 16, 32, 32, QColor(255, 0, 0, 128))
    painter.end()
    return image


def test_png_sink_writes_straight_alpha(qapp, tmp_path) -> None:
    sink = PngSequenceSink(tmp_path, "clip")
    for n in range(3):
        sink.write(n, _test_frame())
    sink.finish()
    files = sorted(tmp_path.glob("clip.*.png"))
    assert [f.name for f in files] == [f"clip.{n:05d}.png" for n in range(3)]

    from PySide6.QtGui import QImage
    reloaded = QImage(str(files[0]))
    assert reloaded.pixelColor(0, 0).alpha() == 0
    inked = reloaded.pixelColor(32, 32)
    assert inked.alpha() == 128
    assert inked.red() >= 250                        # straight, not premul


def test_png_sink_abort_removes_files(qapp, tmp_path) -> None:
    sink = PngSequenceSink(tmp_path, "clip")
    sink.write(0, _test_frame())
    sink.abort()
    assert list(tmp_path.glob("*.png")) == []


needs_ffmpeg = pytest.mark.skipif(
    find_ffmpeg() is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed")


@needs_ffmpeg
def test_prores_sink_produces_alpha_mov(qapp, tmp_path) -> None:
    out = tmp_path / "clip.mov"
    sink = ProResFfmpegSink(out, 64, 64, 30, find_ffmpeg())
    for n in range(30):
        sink.write(n, _test_frame())
    sink.finish()

    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_streams", "-count_frames", str(out)],
        capture_output=True, check=True).stdout)
    stream = probe["streams"][0]
    assert stream["codec_name"] == "prores"
    # the encoder is fed yuva444p10le; ffmpeg 8's decoder reports the
    # 4444 profile at 12-bit — the load-bearing part is the alpha plane
    assert stream["pix_fmt"].startswith("yuva444p")
    assert (stream["width"], stream["height"]) == (64, 64)
    assert int(stream["nb_read_frames"]) == 30

    decode = subprocess.run(                        # playability proxy
        [find_ffmpeg(), "-v", "error", "-i", str(out), "-f", "null", "-"],
        capture_output=True)
    assert decode.returncode == 0, decode.stderr.decode()


@needs_ffmpeg
def test_prores_sink_abort_leaves_no_file(qapp, tmp_path) -> None:
    out = tmp_path / "clip.mov"
    sink = ProResFfmpegSink(out, 64, 64, 30, find_ffmpeg())
    sink.write(0, _test_frame())
    sink.abort()
    assert not out.exists()


@needs_ffmpeg
def test_prores_sink_bad_ffmpeg_surfaces_error(qapp, tmp_path) -> None:
    """A dying encoder raises EncodeError (with ffmpeg's stderr) instead
    of hanging: an unwritable output path kills ffmpeg at startup."""
    out = tmp_path / "no" / "such" / "dir" / "clip.mov"
    sink = ProResFfmpegSink(out, 64, 64, 30, find_ffmpeg())
    with pytest.raises(EncodeError):
        try:
            for n in range(200):
                sink.write(n, _test_frame())
            sink.finish()
        finally:
            sink.abort()
    assert not out.exists()


# -- hidden overrides in export scenes (Phase 9.2) ------------------------------

def test_export_scenes_apply_hidden_overrides(qapp, inputs, engraved,
                                              tempo_map, tempo_setup) -> None:
    """The private export scenes honor doc.layout_overrides.hidden AND
    materialize overlay stage texts — export follows the doc with no
    live-scene contact."""
    from dataclasses import replace

    from scoreanim.core.project import LayoutOverride
    from scoreanim.core.project.stage_config import seed_overlay_text
    from scoreanim.core.score.identity import ElementId

    (tempo,) = [el for el in engraved.layout.elements
                if el.text_class == "tempo"]
    eid = tempo.identity.element_id
    overlay = seed_overlay_text(tempo)
    overlaid_inputs = replace(
        inputs, stage=replace(inputs.stage,
                              texts=inputs.stage.texts + (overlay,)))
    spec = ExportSpec(fps=FPS, height=HEIGHT, start_seconds=0.0,
                      end_seconds=0.1,
                      offset_seconds=tempo_setup.offset_seconds,
                      format=ExportFormat.PNG_SEQUENCE,
                      out_path=Path("unused"))
    renderer = FrameRenderer(overlaid_inputs, StyleRules(), tempo_map, (),
                             spec, overrides={eid: LayoutOverride(hidden=True)})
    assert not renderer._scenes.items[eid].isVisible()
    assert renderer._scenes.items[ElementId(overlay.element_id)].isVisible()
