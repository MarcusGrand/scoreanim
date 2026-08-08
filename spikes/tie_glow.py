"""What a tie looks like to us, before the glow is scoped to notes.

Two questions the glow scoping needs answered on real files:

1. Does a TIE element in the Layout carry an onset, a voice and a part —
   i.e. can a tie be joined to the note group it starts on, the way
   beams already are (schedule rule 3)? And what about the broken
   ``:seg`` halves at a system break, which carry no ScoreNote?
2. Do the ScoreNotes' tie words ('start'/'continue'/'stop') chain up
   into whole held notes, and how much longer is a chain than the
   single segment a notehead's duration reports today?

Run: .venv/bin/python spikes/tie_glow.py
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from scoreanim.core.animation.schedule import quantize_beats
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.score.identity import ElementKind
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.model import build_score_model

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ["testscore", "complex1", "complex3", "video_test"]


def report(name: str) -> None:
    path = ROOT / "testdata" / f"{name}.musicxml"
    provider = VerovioEngravingProvider()
    engraved = provider.load_detailed(path, EngravingParams(), strict=False)
    layout = engraved.layout
    model = build_score_model(engraved.prepared, engraved.timeline)
    mapping = join_notes(model, engraved.note_records).mapping

    ties = [el for el in layout.elements
            if el.identity.kind is ElementKind.TIE]
    segs = [el for el in ties if ":seg" in str(el.identity.element_id)]
    with_onset = [el for el in ties if el.identity.onset is not None]
    seg_with_onset = [el for el in segs if el.identity.onset is not None]
    with_voice = [el for el in ties if el.identity.voice is not None]

    print(f"\n=== {name} ===")
    print(f"ties: {len(ties)}  :seg halves: {len(segs)}")
    print(f"  with onset: {len(with_onset)}   :seg with onset: "
          f"{len(seg_with_onset)}")
    print(f"  with voice: {len(with_voice)}")
    print(f"  extents: {sum(1 for el in ties if el.identity.extent)}")

    # -- can a tie find a notehead group at its own (part, staff, voice, q)?
    heads_by_key: dict[tuple, list] = defaultdict(list)
    for el in layout.elements:
        ident = el.identity
        if ident.kind is ElementKind.NOTEHEAD and ident.onset is not None:
            heads_by_key[(ident.part, ident.staff, ident.voice,
                          quantize_beats(ident.onset))].append(el)
    hits = 0
    for el in ties:
        ident = el.identity
        if ident.onset is None:
            continue
        key = (ident.part, ident.staff, ident.voice,
               quantize_beats(ident.onset))
        if key in heads_by_key:
            hits += 1
    print(f"  ties whose group key finds noteheads: {hits}/{len(with_onset)}")

    # -- tie words on the joined notes -------------------------------------
    words = Counter(note.tie for note in mapping.values())
    print(f"  tie words on joined notes: {dict(words)}")

    # -- chains: pitch-matched, within one (part, staff, voice) ------------
    ident_by_id = {el.identity.element_id: el.identity
                   for el in layout.elements}
    durations = engraved.note_durations
    by_voice: dict[tuple, list] = defaultdict(list)
    for eid, note in mapping.items():
        ident = ident_by_id.get(eid)
        if ident is None or ident.onset is None or note.grace:
            continue
        by_voice[(ident.part, ident.staff, ident.voice)].append(
            (ident.onset, note.order, eid, note))

    chains: list[list] = []
    for key, rows in by_voice.items():
        rows.sort(key=lambda r: (r[0], r[1]))
        open_chain: dict[tuple, list] = {}
        for onset, _order, eid, note in rows:
            pitch = (note.pitch_step, note.pitch_alter, note.octave,
                     note.staff_loc)
            chain = open_chain.pop(pitch, None) \
                if note.tie in ("stop", "continue") else None
            if chain is None:
                chain = [(onset, eid)]
                chains.append(chain)
            else:
                chain.append((onset, eid))
            if note.tie in ("start", "continue"):
                open_chain[pitch] = chain

    multi = [c for c in chains if len(c) > 1]
    print(f"  note groups joined: {len(mapping)}  chains: {len(chains)}  "
          f"chains longer than one note: {len(multi)}")
    if multi:
        spans = []
        for chain in multi:
            first_onset, first_eid = chain[0]
            last_onset, last_eid = chain[-1]
            own = durations.get(first_eid, 0.0)
            whole = (last_onset - first_onset) + durations.get(last_eid, 0.0)
            spans.append((whole, own, len(chain)))
        spans.sort(reverse=True)
        print(f"  longest chain: {spans[0][0]:.2f} beats over "
              f"{spans[0][2]} noteheads, where the first notehead's own "
              f"duration is {spans[0][1]:.2f}")
        ratio = sum(w for w, _o, _n in spans) / sum(o for _w, o, _n in spans)
        print(f"  a chain is {ratio:.2f}x its first notehead's own duration "
              f"on average")


def main() -> None:
    for name in FIXTURES:
        report(name)


if __name__ == "__main__":
    main()
