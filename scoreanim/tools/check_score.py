"""Score-doctor: headless load-triage for any Dorico MusicXML (Phase 11.0).

Loads a score exactly as the app would (engrave → decompose → build the
ScoreModel → join), then prints either PASS with the census (elements,
pages, note records, warning counts, join completeness) or the exact
point where the load failed — never a traceback. This is the engine of
the "any Dorico file loads" goal: every new export becomes one-command
triage, and the loop (doctor → smallest fix → fixture) stays routine.

    python -m scoreanim.tools.check_score testdata/complex1.musicxml
    python -m scoreanim.tools.check_score testdata/          # batch a folder
    python -m scoreanim.tools.check_score --strict <file>    # fail-fast

--strict mirrors the pytest default: an unknown drawable SVG class raises
(coverage gaps stay loud) instead of degrading to a warned static element
(the app path, Phase 11.4). Exit status is non-zero if any score FAILs.
"""

from __future__ import annotations

import sys
import traceback
from collections import Counter
from pathlib import Path

from scoreanim.core.engraving.types import EngravingParams
from scoreanim.core.engraving.verovio import (EngravedScore,
                                              VerovioEngravingProvider)
from scoreanim.core.score.join import join_notes
from scoreanim.core.score.model import build_score_model


class _Report:
    """One score's triage result — PASS with a census or FAIL with the
    exact failure point (its stage and message), never a traceback."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.ok = False
        self.stage = ""
        self.message = ""
        self.elements = 0
        self.pages = 0
        self.note_records = 0
        self.model_notes = 0
        self.matched = 0
        self.warnings: Counter[str] = Counter()

    def fail(self, stage: str, exc: BaseException) -> "_Report":
        self.stage = stage
        self.message = f"{type(exc).__name__}: {exc}"
        return self

    def __str__(self) -> str:
        head = f"{self.path.name}"
        if not self.ok:
            return f"{head}\n  FAIL  [{self.stage}] {self.message}"
        wc = dict(sorted(self.warnings.items())) if self.warnings else "none"
        join = f"{self.matched}/{self.model_notes}"
        complete = "complete" if self.matched == self.model_notes \
            else f"{self.model_notes - self.matched} unmatched"
        return (f"{head}\n"
                f"  PASS  elements={self.elements} pages={self.pages} "
                f"notes={self.note_records} join={join} ({complete})\n"
                f"        warnings={wc}")


def check(path: Path, *, strict: bool) -> _Report:
    """Load one score through the full pipeline, reporting the exact
    stage of any failure. Returns a _Report; never raises."""
    report = _Report(path)
    provider = VerovioEngravingProvider()
    try:
        engraved: EngravedScore = provider.load_detailed(
            path, EngravingParams(), strict=strict)
    except Exception as exc:                                  # noqa: BLE001
        return report.fail("engrave/decompose", exc)

    report.elements = len(engraved.layout.elements)
    report.pages = len(engraved.layout.pages)
    report.note_records = len(engraved.note_records)
    report.warnings = Counter(w.code for w in engraved.warnings)

    try:
        model = build_score_model(engraved.prepared)
    except Exception as exc:                                  # noqa: BLE001
        return report.fail("score-model", exc)
    report.model_notes = len(model.notes)

    try:
        join = join_notes(model, engraved.note_records)
    except Exception as exc:                                  # noqa: BLE001
        return report.fail("join", exc)
    report.matched = len(join.matched)

    report.ok = True
    return report


def _targets(root: Path) -> list[Path]:
    if root.is_dir():
        return sorted(p for p in root.glob("*.musicxml"))
    return [root]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    strict = False
    if "--strict" in args:
        strict = True
        args.remove("--strict")
    if len(args) != 1:
        print(__doc__)
        return 2

    root = Path(args[0])
    if not root.exists():
        print(f"no such file or directory: {root}")
        return 2
    targets = _targets(root)
    if not targets:
        print(f"no .musicxml files in {root}")
        return 2

    failures = 0
    for path in targets:
        try:
            report = check(path, strict=strict)
        except BaseException:                                 # noqa: BLE001
            # check() is meant to be total; if it ever isn't, still name
            # the file instead of dumping a bare traceback for a batch.
            print(f"{path.name}\n  FAIL  [doctor] unexpected error:")
            traceback.print_exc()
            failures += 1
            continue
        print(report)
        if not report.ok:
            failures += 1

    if len(targets) > 1:
        print(f"\n{len(targets) - failures}/{len(targets)} PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
