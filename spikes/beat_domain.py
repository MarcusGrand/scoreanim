"""Beat-domain census: adapter (engraved timemap) measure accounting vs
music21's, per testdata fixture (FINDING-1 fix T1.0, 2026-07-22).

For every fixture this prints, per measure ordinal where the two sides
disagree: the engraved start/span (timemap qstamps, derived exactly as
provider._engrave_prepared derives measure_start/measure_duration —
measure_by_id guard, setdefault, sorted-delta durations) against
music21's measure.offset / barDuration. Plus: every timemap measureOn id
the measure_by_id guard DROPS (expected: only Verovio's playback-
expansion clones, ids ending "-rend<k>"), and any MEI ordinal missing a
timemap start (expected: none — the loud invariant T1.1 installs).

Run:  python spikes/beat_domain.py [testdata/<file>.musicxml ...]
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import music21 as m21
import verovio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoreanim.core.engraving.verovio import mei_index
from scoreanim.core.score.musicxml_prep import prepare

TOL = 1e-6


def census(path: Path) -> None:
    prep = prepare(path)

    # -- engraved side: mirror provider._engrave_prepared exactly ----------
    tk = verovio.toolkit()
    tk.setOptions({"xmlIdSeed": 1})
    if not tk.loadData(prep.canonical_xml):
        print(f"{path.name}: Verovio load FAILED")
        return
    mei = mei_index._parse_mei(tk.getMEI())
    timemap = tk.renderToTimemap({"includeMeasures": True,
                                  "includeRests": True})
    measure_start: dict[int, float] = {}
    dropped: list[tuple[float, str]] = []
    for entry in timemap:
        q = float(entry["qstamp"])
        m_id = entry.get("measureOn")
        if not m_id:
            continue
        if m_id in mei.measure_by_id:
            measure_start.setdefault(mei.measure_by_id[m_id], q)
        else:
            dropped.append((q, m_id))
    score_end = max(float(e["qstamp"]) for e in timemap)
    starts = sorted(measure_start.items(), key=lambda kv: kv[1])
    measure_duration = {
        n: (starts[i + 1][1] if i + 1 < len(starts) else score_end) - q
        for i, (n, q) in enumerate(starts)
    }
    n_mei = len(set(mei.measure_by_id.values()))
    missing = [n for n in range(1, n_mei + 1) if n not in measure_start]

    # -- model side: what build_score_model reads ---------------------------
    score = m21.converter.parse(prep.canonical_xml, format="musicxml")
    p0 = list(score.parts)[0]
    m21_measures = list(p0.getElementsByClass(m21.stream.Measure))

    print(f"\n== {path.name}: {n_mei} MEI measures, "
          f"{len(m21_measures)} music21 measures, "
          f"{len(dropped)} dropped measureOn ids, "
          f"missing ordinals: {missing or 'none'}")
    for q, m_id in dropped:
        tag = "expansion clone" if "-rend" in m_id else "UNEXPECTED"
        print(f"   dropped measureOn {m_id!r} at q{q:g} ({tag})")

    shear = 0.0                    # running engraved-minus-model offset
    for k, mm in enumerate(m21_measures, start=1):
        e_start = measure_start.get(k)
        e_dur = measure_duration.get(k)
        m_start = float(mm.offset)
        m_dur = float(Fraction(mm.barDuration.quarterLength))
        if e_start is None:
            continue
        d_start = e_start - m_start
        d_dur = (e_dur - m_dur) if e_dur is not None else 0.0
        if abs(d_start - shear) > TOL or abs(d_dur) > TOL:
            print(f"   m{k} (printed {mm.number!r}): engraved "
                  f"[{e_start:g}, +{e_dur:g}] vs model "
                  f"[{m_start:g}, +{m_dur:g}]  start-delta {d_start:+g} "
                  f"span-delta {d_dur:+g}")
            shear = d_start


def main(argv: list[str]) -> None:
    paths = ([Path(a) for a in argv]
             or sorted(Path("testdata").glob("*.musicxml")))
    for p in paths:
        census(p)


if __name__ == "__main__":
    main(sys.argv[1:])
