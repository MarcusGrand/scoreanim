"""What the volume response actually does on the real recording.

Decodes testdata/testscore.wav with the app's own PeakExtractor, then
prints the intensity and gain at every element and renders two frames
of the same moment — Amount 0 and Amount 1 — so the difference can be
looked at rather than argued about.

Both readings are printed side by side: the old attack reading (the
loudest bin at the onset) and the one the animation now uses (the
average over the element's own notated duration). The second column is
the answer to "how much gentler did it get".

    python spikes/volume_response.py

Writes spikes/out/volume_off.png and spikes/out/volume_on.png.
"""
from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEventLoop, QTimer                    # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402

from scoreanim.core.animation import (StyleRules,                # noqa: E402
                                      build_reveal_tracks,
                                      build_trigger_schedule,
                                      read_volume, resolve_durations,
                                      trigger_intensities,
                                      window_intensities)
from scoreanim.core.animation.intensity import gain_for          # noqa: E402
from scoreanim.core.engraving.types import EngravingParams       # noqa: E402
from scoreanim.core.engraving.verovio import (                   # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.project.stage_config import (                # noqa: E402
    default_stage_config, page_content_top)
from scoreanim.core.score.join import join_notes                 # noqa: E402
from scoreanim.core.score.model import build_score_model          # noqa: E402
from scoreanim.core.timing import TempoMap, parse_tempo_file     # noqa: E402
from scoreanim.render.export import (AnimationInputs,            # noqa: E402
                                     ExportFormat, ExportSpec,
                                     FrameRenderer)
from scoreanim.ui.peaks_worker import PeakExtractor              # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"
AUDIO = ROOT / "testdata" / "testscore.wav"
SIDECAR = ROOT / "testdata" / "testscore.tempo"
OUT = ROOT / "spikes" / "out"


def decode(app: QApplication):
    """Run the app's own decoder to completion on the event loop."""
    extractor = PeakExtractor()
    loop = QEventLoop()
    extractor.finished.connect(loop.quit)
    extractor.failed.connect(lambda msg: (print("decode failed:", msg),
                                          loop.quit()))
    QTimer.singleShot(0, lambda: extractor.start(AUDIO))
    loop.exec()
    return extractor.cache


def main() -> None:
    app = QApplication.instance() or QApplication([])
    OUT.mkdir(parents=True, exist_ok=True)

    peaks = decode(app)
    print(f"decoded {peaks.duration_seconds:.2f} s at {peaks.sample_rate} Hz, "
          f"{len(peaks.levels[0].rms)} bins at the finest level")

    engraved = VerovioEngravingProvider().load_detailed(SCORE,
                                                        EngravingParams())
    model = build_score_model(engraved.prepared, engraved.timeline)
    report = join_notes(model, engraved.note_records)
    joins = report.mapping
    durations = resolve_durations(engraved.layout, joins,
                                  engraved.note_durations, model.measures)
    schedule = build_trigger_schedule(engraved.layout, joins, model.measures,
                                      durations)
    setup = parse_tempo_file(SIDECAR.read_text(), model.measures)
    tempo = TempoMap(list(setup.events))
    offset = setup.offset_seconds

    from scoreanim.core.timing import resolve_seconds
    trig_s = resolve_seconds([t.beats for t in schedule.triggers], tempo, ())
    volume = read_volume({"amount": 1.0, "quiet": 0.5, "loud": 1.5})

    # one row per ELEMENT, the way the applier reads it: the attack at
    # its onset, and the average over its own notated length
    rows = []
    for trig, start in zip(schedule.triggers, trig_s):
        for eid in trig.element_ids:
            dur = durations.get(eid, 0.0)
            end = tempo.seconds_at(trig.beats + dur) if dur > 0.0 else start
            rows.append((eid, start, end, dur))
    attack = trigger_intensities(peaks, [s + offset for _, s, _, _ in rows])
    average = window_intensities(peaks, [(s + offset, e + offset)
                                         for _, s, e, _ in rows])

    print(f"\n{len(rows)} elements over {len(trig_s)} triggers, "
          f"offset {offset:.2f} s")
    print(f"{'audio s':>9} {'beats':>6}  {'attack':>7} {'average':>7}  "
          f"{'gain':>6}")
    for (eid, start, _, dur), was, now in zip(rows, attack, average):
        print(f"{start + offset:9.2f} {dur:6.2f}  {was:7.3f} {now:7.3f}  "
              f"{gain_for(now, volume):6.3f}  {eid}")
    timed = [(w, n) for (_, _, _, d), w, n in zip(rows, attack, average)
             if d > 0.0]
    print(f"\nattack  spread {min(attack):.3f} to {max(attack):.3f}, "
          f"mean {sum(attack) / len(attack):.3f}")
    print(f"average spread {min(average):.3f} to {max(average):.3f}, "
          f"mean {sum(average) / len(average):.3f}")
    if timed:
        print(f"of the {len(timed)} elements with a notated length, the "
              f"average reads {sum(n for _, n in timed) / sum(w for w, _ in timed):.2f}"
              f"× the attack")

    # the same frame, response off and on
    stage = default_stage_config(engraved.prepared,
                                 page_content_top(engraved.layout))
    score_end = max((m.start + m.quarter_length for m in model.measures),
                    default=0.0)
    tracks = tuple(build_reveal_tracks(engraved.layout, schedule, score_end))
    inputs = AnimationInputs(engraved.layout, stage, schedule, tracks)
    style = StyleRules(default_effect="pop")

    fps = 30
    end = max(trig_s) + offset + 2.0
    spec = ExportSpec(fps=fps, height=2160, start_seconds=0.0,
                      end_seconds=end, offset_seconds=offset,
                      format=ExportFormat.PNG_SEQUENCE, out_path=OUT)
    on = replace(style, volume={"amount": 1.0, "quiet": 0.5, "loud": 1.5})

    off_r = FrameRenderer(inputs, style, tempo, (), spec)
    on_r = FrameRenderer(inputs, on, tempo, (), spec, peaks=peaks)

    # the frame where the response makes the biggest difference across
    # the most ink — the one worth actually looking at
    best, best_score = 0, -1.0
    for frame in range(int(end * fps)):
        off_r.apply_frame(frame)
        on_r.apply_frame(frame)
        moved = [abs(on_r.scenes.items[eid].scale()
                     - off_r.scenes.items[eid].scale())
                 for eid in off_r.scenes.items
                 if off_r.scenes.items[eid].scale() != 1.0]
        score = sum(moved)
        if score > best_score:
            best, best_score = frame, score
    print(f"\nbiggest visible difference at frame {best} "
          f"(t = {best / fps:.2f} s)")

    for name, renderer in (("volume_off", off_r), ("volume_on", on_r)):
        renderer.render_frame(best).save(str(OUT / f"{name}.png"))
        scales = {eid: item.scale()
                  for eid, item in renderer.scenes.items.items()
                  if item.scale() != 1.0}
        print(f"  {name}: {len(scales)} elements mid-pop, "
              f"largest scale {max(scales.values(), default=1.0):.4f}")


if __name__ == "__main__":
    main()
