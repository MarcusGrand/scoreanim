"""D3 (L1): fresh-state oracle. Over a time grid (measure starts, and
trigger times ± epsilon), a fresh ``refresh(t)`` must match the pure
expectation from element_state (opacity) and reveal_x (clip edges) —
recomputed here independently of the applier's caches.
"""

from __future__ import annotations

from scoreanim.core.animation import (OPACITY, PRESETS, REVEALED_KINDS,
                                      RevealMode, StyleRules, build_presets,
                                      effect_for, element_state, reveal_x)
from scoreanim.core.timing import resolve_seconds
from scoreanim.tools.live_oracle.bundle import Finding, OracleBundle
from scoreanim.tools.live_oracle.scene import (_expected_clip,
                                               build_scene_applier)

_EPS_S = 1e-3                    # grid epsilon around events (seconds)
_GRID_CAP = 500                  # sampled-grid trigger points (logged)


def _trigger_seconds_by_eid(bundle: OracleBundle) -> dict:
    eids = list(bundle.schedule.beats_by_element)
    secs = resolve_seconds(
        [bundle.schedule.beats_by_element[e] for e in eids],
        bundle.tempo_map, ())
    return dict(zip(eids, secs))


def _effects_by_eid(bundle: OracleBundle, style: StyleRules) -> dict:
    """Effect resolution exactly as the applier resolves it — recomputed
    here so the oracle's expectation is independent of the applier's
    caches."""
    presets = {**PRESETS, **build_presets(style.floor_opacity)}
    ident_by_id = {el.identity.element_id: el.identity
                   for el in bundle.engraved.layout.elements}
    return {eid: effect_for(style.resolve(ident_by_id[eid]).effect, presets)
            for eid in bundle.schedule.beats_by_element
            if eid in ident_by_id}


def _time_grid(bundle: OracleBundle, grid: str,
               log: list[str]) -> list[float]:
    beats = sorted({m.start for m in bundle.model.measures})
    pts: list[float] = []
    for s in resolve_seconds(beats, bundle.tempo_map, ()):
        pts += [s - _EPS_S, s + _EPS_S]
    if grid != "measures":
        trig = resolve_seconds([t.beats for t in bundle.schedule.triggers],
                               bundle.tempo_map, ())
        if grid == "sampled" and len(trig) > _GRID_CAP:
            stride = -(-len(trig) // _GRID_CAP)
            log.append(f"D3 grid: sampling every {stride}th of "
                       f"{len(trig)} triggers (use --grid full for all)")
            trig = trig[::stride]
        for s in trig:
            pts += [s - _EPS_S, s + _EPS_S]
    return sorted({round(p, 6) for p in pts if p >= 0.0})


def check_d3(bundle: OracleBundle, mode: RevealMode, grid: str,
             log: list[str]) -> list[Finding]:
    style = StyleRules(reveal_mode=mode)
    scenes, applier = build_scene_applier(bundle, style)
    trig_s = _trigger_seconds_by_eid(bundle)
    effects = _effects_by_eid(bundle, style)

    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()   # (code, eid): first-t only
    for t in _time_grid(bundle, grid, log):
        applier.refresh(t)
        # opacity vs the pure kernel
        for eid, eff in effects.items():
            item = scenes.items.get(eid)
            if item is None:
                continue                 # D1's schedule-id-not-in-scene
            expected = element_state(trig_s[eid], eff, t).get(OPACITY)
            if expected is None:
                continue
            if abs(item.opacity() - expected) > 1e-6 \
                    and ("opacity", eid) not in seen:
                seen.add(("opacity", eid))
                findings.append(Finding(
                    "D3", "opacity-mismatch", eid,
                    f"t={t:.3f}s ({mode.name}): scene opacity "
                    f"{item.opacity():.4f} != expected {expected:.4f}"))
        # reveal clips vs reveal_x
        for eid, item in scenes.items.items():
            ident = item.identity
            if (ident is None or ident.kind not in REVEALED_KINDS
                    or item.system is None):
                continue
            curve = bundle.curve_by_key.get((item.system, ident.part))
            if curve is None:
                # FINDING-2 containment: a curve-less item never
                # receives an edge, so it must sit at the hidden
                # construction default at EVERY t
                for k, child in enumerate(item.reveal_children):
                    if not child.hidden and ("clip", eid) not in seen:
                        seen.add(("clip", eid))
                        findings.append(Finding(
                            "D3", "curveless-not-hidden", eid,
                            f"t={t:.3f}s ({mode.name}) child {k}: no "
                            f"reveal curve for (sys {item.system}, part "
                            f"{ident.part}) yet clip_right="
                            f"{child.clip_right} is not hidden — "
                            f"visible-from-t0 regression (FINDING-2)"))
                continue
            edge = reveal_x(curve, t, mode)
            for k, child in enumerate(item.reveal_children):
                exp_clip, exp_hidden = _expected_clip(child, edge)
                got = child.clip_right
                clip_ok = ((got is None and exp_clip is None)
                           or (got is not None and exp_clip is not None
                               and abs(got - exp_clip) <= 1e-4))
                if (not clip_ok or child.hidden != exp_hidden) \
                        and ("clip", eid) not in seen:
                    seen.add(("clip", eid))
                    findings.append(Finding(
                        "D3", "clip-mismatch", eid,
                        f"t={t:.3f}s ({mode.name}) child {k}: clip_right "
                        f"{got} != expected {exp_clip} "
                        f"(hidden {child.hidden} vs {exp_hidden})"))
    return findings
