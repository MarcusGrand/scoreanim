"""Report formatting and the CLI entry point (doctor-style: never a
traceback; exit 1 on findings, 2 on usage errors). See the package
docstring for usage.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from scoreanim.core.animation import RevealMode
from scoreanim.tools.live_oracle.bundle import (Finding, OracleBundle,
                                                build_bundle)
from scoreanim.tools.live_oracle.d1_curves import check_d1
from scoreanim.tools.live_oracle.d2_triggers import check_d2
from scoreanim.tools.live_oracle.d3_state import check_d3
from scoreanim.tools.live_oracle.d4_ticks import check_d4
from scoreanim.tools.live_oracle.d5_purity import check_d5

_SHOW = 10                       # element ids listed per finding group


def _print_report(path: Path, bundle: OracleBundle,
                  findings: Sequence[Finding], log: Iterable[str],
                  checks: Sequence[str]) -> None:
    warn = defaultdict(int)
    for w in bundle.engraved.warnings:
        warn[w.code] += 1
    print(f"{path.name}")
    print(f"  census  elements={len(bundle.engraved.layout.elements)} "
          f"triggers={len(bundle.schedule.triggers)} "
          f"tracks={len(bundle.tracks)} "
          f"join={len(bundle.join.matched)}/{len(bundle.model.notes)} "
          f"warnings={dict(sorted(warn.items())) or 'none'}")
    for line in log:
        print(f"  note    {line}")
    by_check: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_check[f.check].append(f)
    for check in checks:
        fs = by_check.get(check.upper(), [])
        if not fs:
            print(f"  {check.upper()}      PASS")
            continue
        by_code: dict[str, list[Finding]] = defaultdict(list)
        for f in fs:
            by_code[f.code].append(f)
        print(f"  {check.upper()}      FAIL  {len(fs)} finding(s)")
        for code, group in sorted(by_code.items()):
            print(f"    [{code}] x{len(group)}")
            for f in group[:_SHOW]:
                eid = f"{f.element_id}  " if f.element_id else ""
                print(f"      {eid}{f.detail}")
            if len(group) > _SHOW:
                print(f"      ... +{len(group) - _SHOW} more")


def run_checks(bundle: OracleBundle, checks: Sequence[str],
               modes: Sequence[RevealMode], grid: str,
               log: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    if "d1" in checks:
        findings += check_d1(bundle, log)
    if "d2" in checks:
        findings += check_d2(bundle)
    if "d3" in checks:
        for mode in modes:
            findings += check_d3(bundle, mode, grid, log)
    if "d4" in checks:
        for mode in modes:
            findings += check_d4(bundle, mode, log)
    if "d5" in checks:
        findings += check_d5(bundle, log)
    return findings


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    def _opt(name: str, default: str | None = None) -> str | None:
        if name in args:
            i = args.index(name)
            args.pop(i)
            return args.pop(i)
        return default

    hide = "--no-hide" not in args
    if not hide:
        args.remove("--no-hide")
    strict = "--strict" in args
    if strict:
        args.remove("--strict")
    mode_arg = _opt("--mode", "both")
    grid = _opt("--grid", "sampled")
    checks = (_opt("--checks", "d1,d2,d3,d4,d5") or "").lower().split(",")
    if len(args) != 1 or mode_arg not in ("stepped", "continuous", "both") \
            or grid not in ("sampled", "measures", "full"):
        import scoreanim.tools.live_oracle as pkg
        print(pkg.__doc__)
        return 2
    modes = {"stepped": [RevealMode.STEPPED],
             "continuous": [RevealMode.CONTINUOUS],
             "both": [RevealMode.STEPPED, RevealMode.CONTINUOUS]}[mode_arg]

    root = Path(args[0])
    if not root.exists():
        print(f"no such file or directory: {root}")
        return 2
    targets = sorted(root.glob("*.musicxml")) if root.is_dir() else [root]
    if not targets:
        print(f"no .musicxml files in {root}")
        return 2

    failures = 0
    for path in targets:
        log: list[str] = []
        try:
            bundle = build_bundle(path, hide_empty_staves=hide,
                                  strict=strict)
        except Exception as exc:                          # noqa: BLE001
            print(f"{path.name}\n  FAIL  [build] "
                  f"{type(exc).__name__}: {exc}")
            failures += 1
            continue
        findings = run_checks(bundle, checks, modes, grid, log)
        _print_report(path, bundle, findings, log, checks)
        if findings:
            failures += 1

    if len(targets) > 1:
        print(f"\n{len(targets) - failures}/{len(targets)} clean")
    return 1 if failures else 0
