"""Phase 3 spike: Qt audio playhead precision (ARCHITECTURE.md known risk 3).

Question: is QMediaPlayer.position() good enough to be the master clock for
onset animation? "Good enough" (stated before measuring):

    effective clock error <= 20 ms (~1 frame @ 60 fps)  -> ideal
    effective clock error <= 33 ms (~2 frames)          -> acceptable
    (ITU-R BT.1359: a/v asynchrony detectability starts around 45 ms
     audio-lead / 125 ms audio-lag; clock error here shifts visuals both
     ways, so <= 33 ms sits below general detectability.)

Tiers, decided by this spike:
    tier 1: read player.position() raw each frame.
        PASS iff p95 distinct-value update gap <= 25 ms AND staircase
        residuals (sampled position vs linear fit) p95 <= 20 ms and
        max <= 33 ms AND zero backward jumps AND seeks settle <= 250 ms.
    tier 2: anchored extrapolation -- on every positionChanged store
        (position, perf_counter()); between anchors report
        anchor_pos + wall_elapsed, clamped monotone. Simulated OFFLINE
        here from the tier-1 trace (same data the wrapper would see).
        PASS iff simulated residuals p95 <= 20 ms and max <= 33 ms AND
        median correction at each re-anchor <= 15 ms.
    tier 2b: same anchors, but the clock is wall_now + mean(anchor_pos -
        anchor_wall) over the last ~1 s of anchors (offset averaging;
        audio and wall clocks run at the same rate to ~1e-5, measured
        as the fit slope, so a sliding mean is safe). Still a pure
        function of (recent authoritative positions, wall time) -- no
        accumulation. Same PASS thresholds as tier 2.
    tier 3: QAudioDecoder -> QAudioSink, position from processedUSecs.
        Only if 1 and 2 fail; real work -- stop and discuss first.

Test material: a synthesized 60 s click track (5 ms 1 kHz bursts every
500 ms at exact sample positions), as wav and as an ffmpeg-encoded mp3
twin, so wav-vs-mp3 differences (decoder delay, seek behavior) show up
against identical content. Note: absolute output latency (position()
leading the speakers by the sink buffer) is NOT measurable without a
loopback rig; any constant offset is absorbed by the tempo file's
`offset` knob, so it does not gate the tier choice. Playback is quiet
but audible (~2 min total).

Run: python spikes/audio_playhead.py
"""
from __future__ import annotations

import array
import math
import random
import statistics
import subprocess
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

OUT = Path(__file__).parent / "out"
RATE = 44100
DURATION_S = 60.0
CLICK_INTERVAL_S = 0.5
STEADY_MEASURE_S = 30.0
WARMUP_S = 2.0
SEEK_COUNT = 20

IDEAL_S = 0.020
ACCEPT_S = 0.033


def make_click_wav(path: Path) -> None:
    n = int(DURATION_S * RATE)
    samples = array.array("h", bytes(2 * n))
    burst = int(0.005 * RATE)
    for k in range(int(DURATION_S / CLICK_INTERVAL_S)):
        start = int(k * CLICK_INTERVAL_S * RATE)
        for i in range(burst):
            env = 1.0 - i / burst
            samples[start + i] = int(16000 * env * math.sin(2 * math.pi * 1000 * i / RATE))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())


def make_click_mp3(wav: Path, mp3: Path) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
             "-codec:a", "libmp3lame", "-qscale:a", "2", str(mp3)],
            check=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"  mp3 encode failed ({exc}); skipping mp3 leg")
        return False


@dataclass
class Trace:
    """Everything recorded during one file's measurement run."""
    samples: list[tuple[float, float]] = field(default_factory=list)   # (wall_s, pos_s)
    signal_anchors: list[tuple[float, float]] = field(default_factory=list)  # positionChanged
    seek_settles: list[float | None] = field(default_factory=list)
    seek_land_errors: list[float] = field(default_factory=list)
    paused_seek_delays: list[float | None] = field(default_factory=list)
    pause_drift_s: float = 0.0
    resume_jump_s: float = 0.0
    errors: list[str] = field(default_factory=list)


def spin(app: QCoreApplication, seconds: float) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        app.processEvents()


def spin_until(app: QCoreApplication, pred, timeout: float) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        app.processEvents()
        if pred():
            return True
    return False


def measure_file(app: QCoreApplication, path: Path) -> Trace:
    tr = Trace()
    player = QMediaPlayer()
    audio = QAudioOutput()
    audio.setVolume(0.05)
    player.setAudioOutput(audio)
    player.errorOccurred.connect(
        lambda err, msg: tr.errors.append(f"{err}: {msg}"))
    player.positionChanged.connect(
        lambda ms: tr.signal_anchors.append((time.perf_counter(), ms / 1000.0)))
    player.setSource(QUrl.fromLocalFile(str(path.resolve())))

    ok = spin_until(app, lambda: player.mediaStatus() in (
        QMediaPlayer.MediaStatus.LoadedMedia,
        QMediaPlayer.MediaStatus.BufferedMedia) or tr.errors, timeout=5.0)
    if not ok or tr.errors:
        tr.errors.append("media never loaded")
        return tr

    duration_s = player.duration() / 1000.0   # seek bounds from the file itself

    # --- steady playback: dense position sampling -------------------------
    player.play()
    spin(app, WARMUP_S)
    deadline = time.perf_counter() + min(STEADY_MEASURE_S,
                                         duration_s - WARMUP_S - 2.0)
    while time.perf_counter() < deadline:
        app.processEvents()
        tr.samples.append((time.perf_counter(), player.position() / 1000.0))

    # --- seeks while playing ----------------------------------------------
    rng = random.Random(42)
    for _ in range(SEEK_COUNT):
        target_s = rng.uniform(2.0, duration_s - 5.0)
        t0 = time.perf_counter()
        player.setPosition(int(target_s * 1000))

        def settled() -> bool:
            expect = target_s + (time.perf_counter() - t0)
            return abs(player.position() / 1000.0 - expect) <= ACCEPT_S

        if spin_until(app, settled, timeout=2.0):
            settle = time.perf_counter() - t0
            tr.seek_settles.append(settle)
            tr.seek_land_errors.append(
                player.position() / 1000.0 - (target_s + settle))
        else:
            tr.seek_settles.append(None)
        spin(app, 0.1)

    # --- seeks while paused -----------------------------------------------
    player.pause()
    spin(app, 0.2)
    for target_s in (duration_s * 0.1, duration_s * 0.5, duration_s * 0.8):
        t0 = time.perf_counter()
        player.setPosition(int(target_s * 1000))
        if spin_until(app, lambda: abs(player.position() / 1000.0 - target_s) <= 0.002,
                      timeout=2.0):
            tr.paused_seek_delays.append(time.perf_counter() - t0)
        else:
            tr.paused_seek_delays.append(None)

    # --- pause freeze / resume continuity ----------------------------------
    player.play()
    spin(app, 0.5)
    player.pause()
    spin(app, 0.2)                       # let the backend settle into pause
    frozen = [player.position() / 1000.0]
    deadline = time.perf_counter() + 1.0
    while time.perf_counter() < deadline:
        app.processEvents()
        frozen.append(player.position() / 1000.0)
    tr.pause_drift_s = max(frozen) - min(frozen)
    pos_at_pause = frozen[-1]
    t0 = time.perf_counter()
    player.play()
    spin(app, 0.5)
    expect = pos_at_pause + (time.perf_counter() - t0)
    tr.resume_jump_s = player.position() / 1000.0 - expect

    player.stop()
    player.setSource(QUrl())             # release the file
    spin(app, 0.1)
    return tr


@dataclass
class Analysis:
    update_gap_p50: float
    update_gap_p95: float
    update_gap_max: float
    slope: float
    backward_jumps: int
    t1_res_p50: float
    t1_res_p95: float
    t1_res_max: float
    signal_gap_p50: float
    signal_gap_p95: float
    t2_res_p50: float
    t2_res_p95: float
    t2_res_max: float
    t2_correction_p50: float
    t2b_res_p50: float
    t2b_res_p95: float
    t2b_res_max: float


def pctl(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def analyze(tr: Trace) -> Analysis:
    samples = tr.samples
    # distinct-value change points of the polled position
    changes = [samples[0]]
    backward = 0
    for w, p in samples[1:]:
        if p != changes[-1][1]:
            if p < changes[-1][1]:
                backward += 1
            changes.append((w, p))
    gaps = [b[0] - a[0] for a, b in zip(changes, changes[1:])]

    # least-squares fit pos = a + b*wall over change points = "true" audio time
    ws = [w for w, _ in changes]
    ps = [p for _, p in changes]
    wm, pm = statistics.fmean(ws), statistics.fmean(ps)
    denom = sum((w - wm) ** 2 for w in ws)
    slope = sum((w - wm) * (p - pm) for w, p in changes) / denom
    intercept = pm - slope * wm
    fit = lambda w: intercept + slope * w  # noqa: E731

    t1_res = [abs(p - fit(w)) for w, p in samples]

    # tier-2 simulation over the same window, anchored on positionChanged
    t_min, t_max = samples[0][0], samples[-1][0]
    anchors = [(w, p) for w, p in tr.signal_anchors if t_min <= w <= t_max]
    sig_gaps = [b[0] - a[0] for a, b in zip(anchors, anchors[1:])]
    t2_res: list[float] = []
    corrections: list[float] = []
    ai = 0
    est_prev = None
    for w, _ in samples:
        while ai + 1 < len(anchors) and anchors[ai + 1][0] <= w:
            aw, ap = anchors[ai], anchors[ai + 1]
            corrections.append(abs((aw[1] + (ap[0] - aw[0])) - ap[1]))
            ai += 1
        if not anchors:
            break
        aw, apos = anchors[ai]
        est = apos + (w - aw)
        if est_prev is not None:
            est = max(est, est_prev)     # monotone clamp
        est_prev = est
        t2_res.append(abs(est - fit(w)))

    # tier-2b simulation: sliding mean of (anchor_pos - anchor_wall)
    t2b_res: list[float] = []
    bi = 0
    estb_prev = None
    window: list[float] = []             # offsets of anchors currently <= w
    for w, _ in samples:
        while bi < len(anchors) and anchors[bi][0] <= w:
            window.append(anchors[bi][1] - anchors[bi][0])
            bi += 1
        if not window:
            continue
        recent = window[-12:]            # ~1.2 s at 100 ms cadence
        estb = w + statistics.fmean(recent)
        if estb_prev is not None:
            estb = max(estb, estb_prev)  # monotone clamp
        estb_prev = estb
        t2b_res.append(abs(estb - fit(w)))

    return Analysis(
        update_gap_p50=pctl(gaps, 0.50), update_gap_p95=pctl(gaps, 0.95),
        update_gap_max=max(gaps), slope=slope, backward_jumps=backward,
        t1_res_p50=pctl(t1_res, 0.50), t1_res_p95=pctl(t1_res, 0.95),
        t1_res_max=max(t1_res),
        signal_gap_p50=pctl(sig_gaps, 0.50), signal_gap_p95=pctl(sig_gaps, 0.95),
        t2_res_p50=pctl(t2_res, 0.50), t2_res_p95=pctl(t2_res, 0.95),
        t2_res_max=max(t2_res) if t2_res else float("nan"),
        t2_correction_p50=pctl(corrections, 0.50),
        t2b_res_p50=pctl(t2b_res, 0.50), t2b_res_p95=pctl(t2b_res, 0.95),
        t2b_res_max=max(t2b_res) if t2b_res else float("nan"),
    )


def verdicts(a: Analysis, tr: Trace) -> tuple[bool, bool, bool, list[str]]:
    notes: list[str] = []
    settles = [s for s in tr.seek_settles if s is not None]
    seeks_ok = len(settles) == len(tr.seek_settles) and max(settles) <= 0.250
    if not seeks_ok:
        failed = tr.seek_settles.count(None)
        notes.append(f"seeks: {failed} timed out, max settle "
                     f"{max(settles) * 1000:.0f} ms" if settles else "all seeks timed out")
    tier1 = (a.update_gap_p95 <= 0.025 and a.t1_res_p95 <= IDEAL_S
             and a.t1_res_max <= ACCEPT_S and a.backward_jumps == 0 and seeks_ok)
    tier2 = (a.t2_res_p95 <= IDEAL_S and a.t2_res_max <= ACCEPT_S
             and a.t2_correction_p50 <= 0.015 and seeks_ok)
    tier2b = (a.t2b_res_p95 <= IDEAL_S and a.t2b_res_max <= ACCEPT_S and seeks_ok)
    if tr.pause_drift_s > 0.002:
        notes.append(f"position moved {tr.pause_drift_s * 1000:.1f} ms while paused")
    if abs(tr.resume_jump_s) > ACCEPT_S:
        notes.append(f"resume jump {tr.resume_jump_s * 1000:+.0f} ms")
    return tier1, tier2, tier2b, notes


def report(name: str, a: Analysis, tr: Trace) -> tuple[bool, bool]:
    ms = lambda v: f"{v * 1000:7.1f}"  # noqa: E731
    print(f"\n=== {name} ===")
    print(f"  position() update gap ms   p50 {ms(a.update_gap_p50)}  "
          f"p95 {ms(a.update_gap_p95)}  max {ms(a.update_gap_max)}")
    print(f"  positionChanged gap ms     p50 {ms(a.signal_gap_p50)}  "
          f"p95 {ms(a.signal_gap_p95)}")
    print(f"  fit slope (audio s / wall s)   {a.slope:.6f}   "
          f"backward jumps {a.backward_jumps}")
    print(f"  tier-1 residual ms         p50 {ms(a.t1_res_p50)}  "
          f"p95 {ms(a.t1_res_p95)}  max {ms(a.t1_res_max)}")
    print(f"  tier-2 residual ms         p50 {ms(a.t2_res_p50)}  "
          f"p95 {ms(a.t2_res_p95)}  max {ms(a.t2_res_max)}   "
          f"re-anchor correction p50 {ms(a.t2_correction_p50)}")
    print(f"  tier-2b residual ms        p50 {ms(a.t2b_res_p50)}  "
          f"p95 {ms(a.t2b_res_p95)}  max {ms(a.t2b_res_max)}")
    settles = [s for s in tr.seek_settles if s is not None]
    print(f"  seeks playing: {len(settles)}/{len(tr.seek_settles)} settled, "
          f"ms p50 {ms(pctl(settles, 0.5))} max {ms(max(settles))}"
          if settles else "  seeks playing: NONE settled")
    if settles:
        print(f"  seek landing error ms      p50 "
              f"{ms(pctl([abs(e) for e in tr.seek_land_errors], 0.5))}")
    pd = [d for d in tr.paused_seek_delays if d is not None]
    print(f"  seeks paused: {len(pd)}/{len(tr.paused_seek_delays)} exact, "
          f"delay ms max {ms(max(pd))}" if pd else "  seeks paused: NONE reflected")
    print(f"  paused drift {tr.pause_drift_s * 1000:.2f} ms   "
          f"resume jump {tr.resume_jump_s * 1000:+.1f} ms")
    t1, t2, t2b, notes = verdicts(a, tr)
    for n in notes:
        print(f"  note: {n}")
    print(f"  TIER 1 {'PASS' if t1 else 'FAIL'}   TIER 2 {'PASS' if t2 else 'FAIL'}"
          f"   TIER 2b {'PASS' if t2b else 'FAIL'}")
    return t1, t2, t2b


def main() -> int:
    OUT.mkdir(exist_ok=True)
    wav = OUT / "click.wav"
    mp3 = OUT / "click.mp3"
    if not wav.exists():
        make_click_wav(wav)
    have_mp3 = mp3.exists() or make_click_mp3(wav, mp3)

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    results: dict[str, tuple[bool, bool, bool]] = {}
    for name, path in [("wav", wav)] + ([("mp3", mp3)] if have_mp3 else []):
        tr = measure_file(app, path)
        if tr.errors or len(tr.samples) < 1000:
            print(f"\n=== {name} === MEASUREMENT FAILED: {tr.errors}")
            results[name] = (False, False, False)
            continue
        results[name] = report(name, analyze(tr), tr)

    all_t1 = all(t1 for t1, _, _ in results.values())
    all_t2 = all(t2 for _, t2, _ in results.values())
    all_t2b = all(t2b for _, _, t2b in results.values())
    verdict = "1" if all_t1 else "2" if all_t2 else "2b" if all_t2b else "3"
    print(f"\nVERDICT: tier {verdict}"
          + ("  (raw position() each frame)" if verdict == "1" else
             "  (last-anchor extrapolation on positionChanged)" if verdict == "2" else
             "  (sliding-mean-offset extrapolation on positionChanged)"
             if verdict == "2b" else
             "  (QAudioSink path -- STOP and discuss before building)"))
    print("note: absolute output latency (position vs speakers) not measurable "
          "without loopback; constant offsets are absorbed by the tempo file's "
          "`offset`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
