"""What the glow's scope actually covers on real files.

Prints, per fixture: how much of the page used to glow against how much
glows now, which kinds went dark, how many pieces of ink share another
note's halo, and how much longer a tied chain burns than the single
notehead the duration map reports.

Run: PYTHONPATH=. .venv/bin/python spikes/glow_scope.py
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from scoreanim.core.animation import resolve_durations
from scoreanim.core.animation.glow_scope import GLOWING_KINDS, glow_scope
from scoreanim.core.animation.schedule import is_animated
from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import VerovioEngravingProvider
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.model import build_score_model

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ["testscore", "complex1", "complex3", "video_test", "bigband1"]


def report(name: str) -> None:
    path = ROOT / "testdata" / f"{name}.musicxml"
    provider = VerovioEngravingProvider()
    engraved = provider.load_detailed(path, EngravingParams(), strict=False)
    layout = engraved.layout
    model = build_score_model(engraved.prepared, engraved.timeline)
    mapping = join_notes(model, engraved.note_records).mapping
    durations = resolve_durations(layout, mapping, engraved.note_durations,
                                  model.measures)
    scope = glow_scope(layout, mapping, durations)

    before = [el for el in layout.elements if is_animated(el.identity)]
    after = [el for el in layout.elements
             if el.identity.kind in GLOWING_KINDS]
    went_dark = Counter(el.identity.kind.name for el in before
                        if el.identity.kind not in GLOWING_KINDS)

    followers = scope.followers()
    shared = Counter(
        next(el.identity.kind.name for el in layout.elements
             if el.identity.element_id == eid)
        for eid in scope.owner)

    print(f"\n=== {name} ===")
    print(f"  elements: {len(layout.elements)}  "
          f"lit before: {len(before)}  lit now: {len(after)}  "
          f"({100 * len(after) / max(1, len(before)):.0f}% of before)")
    print(f"  kinds that went dark: {dict(went_dark.most_common(8))}")
    print(f"  ink sharing another note's halo: {len(scope.owner)} "
          f"{dict(shared.most_common())}")
    print(f"  noteheads leading a shared halo: {len(followers)}")
    if scope.span:
        own = [durations.get(eid, 0.0) for eid in scope.span]
        longest = max(scope.span.items(), key=lambda kv: kv[1])
        print(f"  tie chains that burn longer: {len(scope.span)}  "
              f"longest {longest[1]:.2f} beats against the "
              f"{durations.get(longest[0], 0.0):.2f} its own notehead "
              f"reports")
        print(f"  a chain burns {sum(scope.span.values()) / max(1e-9, sum(own)):.2f}x "
              f"its leader's own duration on average")


def main() -> None:
    for name in FIXTURES:
        report(name)


if __name__ == "__main__":
    main()
