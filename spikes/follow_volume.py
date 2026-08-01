"""What a note following the recording actually reads, frame by frame.

The question the plateau shape rests on: does the live reading MOVE
across a long note, and does it move smoothly enough that the ink will
not shake? So for the longest notes in testscore this prints the
reading at every frame of their length, next to the one average the
note would otherwise have had for its whole life.

    python spikes/follow_volume.py

Prints only — nothing is written.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEventLoop, QTimer                    # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402

from scoreanim.core.animation import (build_trigger_schedule,    # noqa: E402
                                      gain_for, intensity_at,
                                      peak_reference, read_volume,
                                      resolve_durations,
                                      window_intensities)
from scoreanim.core.animation.intensity import (SMOOTHING_S,     # noqa: E402
                                                _smoothing_level)
from scoreanim.core.engraving.types import EngravingParams       # noqa: E402
from scoreanim.core.engraving.verovio import (                   # noqa: E402
    VerovioEngravingProvider)
from scoreanim.core.score.join import join_notes                 # noqa: E402
from scoreanim.core.score.model import build_score_model         # noqa: E402
from scoreanim.core.timing import (TempoMap, parse_tempo_file,   # noqa: E402
                                   resolve_seconds)
from scoreanim.ui.peaks_worker import PeakExtractor              # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "testdata" / "testscore.musicxml"
AUDIO = ROOT / "testdata" / "testscore.wav"
SIDECAR = ROOT / "testdata" / "testscore.tempo"

FPS = 30
LONGEST = 4                 # how many of the longest notes to print


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
    peaks = decode(app)
    level = _smoothing_level(peaks)
    bin_s = level.samples_per_bin / peaks.sample_rate
    reference = peak_reference(peaks)
    print(f"decoded {peaks.duration_seconds:.2f} s at {peaks.sample_rate} Hz")
    print(f"the live reading uses level {peaks.levels.index(level)} of "
          f"{len(peaks.levels)}: {bin_s * 1000:.1f} ms per bin "
          f"(asked for {SMOOTHING_S * 1000:.0f} ms), reference "
          f"{reference:.4f}")

    engraved = VerovioEngravingProvider().load_detailed(SCORE,
                                                        EngravingParams())
    model = build_score_model(engraved.prepared, engraved.timeline)
    joins = join_notes(model, engraved.note_records).mapping
    durations = resolve_durations(engraved.layout, joins,
                                  engraved.note_durations, model.measures)
    schedule = build_trigger_schedule(engraved.layout, joins, model.measures,
                                      durations)
    setup = parse_tempo_file(SIDECAR.read_text(), model.measures)
    tempo = TempoMap(list(setup.events))
    offset = setup.offset_seconds
    trig_s = resolve_seconds([t.beats for t in schedule.triggers], tempo, ())
    volume = read_volume({"amount": 1.0, "quiet": 0.5, "loud": 1.5})

    # every element that has a notated length, longest first
    notes = []
    for trig, start in zip(schedule.triggers, trig_s):
        for eid in trig.element_ids:
            dur = durations.get(eid, 0.0)
            if dur > 0.0:
                end = tempo.seconds_at(trig.beats + dur)
                notes.append((dur, start, end, eid))
    notes.sort(key=lambda n: (-n[0], n[1]))

    print(f"\n{len(notes)} elements carry a notated length; the "
          f"{LONGEST} longest, frame by frame at {FPS} fps:")
    for dur, start, end, eid in notes[:LONGEST]:
        average, = window_intensities(peaks, [(start + offset, end + offset)])
        print(f"\n  {eid}  {dur:g} beats, {end - start:.2f} s from "
              f"{start + offset:.2f} s")
        print(f"  its one average would be {average:.3f} "
              f"(gain {gain_for(average, volume):.3f})")
        print(f"  {'t':>7} {'live':>6} {'gain':>6}  {'step':>6}")
        prev = None
        biggest = 0.0
        n = 0
        while start + n / FPS < end:
            t = start + n / FPS
            live = intensity_at(peaks, t + offset, reference)
            step = 0.0 if prev is None else live - prev
            biggest = max(biggest, abs(step))
            print(f"  {t + offset:7.2f} {live:6.3f} "
                  f"{gain_for(live, volume):6.3f}  {step:+6.3f}")
            prev = live
            n += 1
        print(f"  biggest jump between two frames: {biggest:.3f} "
              f"({biggest * (volume.loud - volume.quiet) * volume.amount:.3f} "
              f"of gain)")


if __name__ == "__main__":
    main()
