"""D4 (L2): live-tick differential. ``apply_at`` over a dense forward
grid (with two backward scrub seeks) must leave the scene identical to
one fresh ``refresh`` at every measure-start checkpoint; on divergence,
the tick prefix is bisected to the first diverging tick.
"""

from __future__ import annotations

from scoreanim.core.animation import RevealMode, StyleRules
from scoreanim.core.timing import resolve_seconds
from scoreanim.tools.live_oracle.bundle import Finding, OracleBundle
from scoreanim.tools.live_oracle.scene import (_snapshot,
                                               build_scene_applier)


def _tick_times(bundle: OracleBundle) -> list[float]:
    """Dense forward grid (~4 ticks/beat) with two backward scrub seeks:
    at 40% jump back to 15% and replay, at 75% jump back to 55%."""
    n = max(2, int(bundle.score_end * 4))
    beats = [bundle.score_end * i / n for i in range(n + 1)]
    base = resolve_seconds(beats, bundle.tempo_map, ())
    i40, i15 = int(len(base) * 0.40), int(len(base) * 0.15)
    i75, i55 = int(len(base) * 0.75), int(len(base) * 0.55)
    return (base[:i40] + base[i15:i75] + base[i55:])


def _checkpoints(bundle: OracleBundle) -> set[float]:
    beats = sorted({m.start for m in bundle.model.measures})
    secs = resolve_seconds(beats, bundle.tempo_map, ())
    return {round(s, 9) for s in secs}


def check_d4(bundle: OracleBundle, mode: RevealMode,
             log: list[str]) -> list[Finding]:
    style = StyleRules(reveal_mode=mode)
    scenes_a, app_a = build_scene_applier(bundle, style)
    scenes_b, app_b = build_scene_applier(bundle, style)
    ticks = _tick_times(bundle)
    checkpoints = _checkpoints(bundle)
    checkpoints.add(round(ticks[-1], 9))

    diverged_at: int | None = None
    diff_ids: list[str] = []
    for i, t in enumerate(ticks):
        app_a.apply_at(t)
        if round(t, 9) not in checkpoints:
            continue
        snap_a = _snapshot(scenes_a)
        app_b.refresh(t)
        snap_b = _snapshot(scenes_b)
        if snap_a != snap_b:
            diverged_at = i
            diff_ids = [str(k) for k in snap_a
                        if snap_a[k] != snap_b.get(k)]
            break
    if diverged_at is None:
        return []

    # bisect the tick prefix to the first diverging tick: smallest m such
    # that replaying ticks[:m+1] differs from a fresh refresh at ticks[m]
    def prefix_diverges(m: int) -> list[str]:
        scenes_c, app_c = build_scene_applier(bundle, style)
        for t in ticks[:m + 1]:
            app_c.apply_at(t)
        app_b.refresh(ticks[m])
        snap_c, snap_b2 = _snapshot(scenes_c), _snapshot(scenes_b)
        return [str(k) for k in snap_c if snap_c[k] != snap_b2.get(k)]

    lo, hi = 0, diverged_at              # hi known-diverging
    while lo < hi:
        mid = (lo + hi) // 2
        if prefix_diverges(mid):
            hi = mid
        else:
            lo = mid + 1
    first_diff = prefix_diverges(lo) or diff_ids
    back = " (a backward-seek tick)" if lo > 0 \
        and ticks[lo] < ticks[lo - 1] else ""
    log.append(f"D4 ({mode.name}): first divergence at tick {lo} "
               f"t={ticks[lo]:.3f}s{back}, {len(first_diff)} item(s)")
    return [Finding(
        "D4", "sequence-divergence", eid,
        f"{mode.name}: apply_at ticking diverges from refresh at tick "
        f"{lo} (t={ticks[lo]:.3f}s{back})") for eid in first_diff[:50]]
